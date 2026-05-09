from fastapi import FastAPI, Query, HTTPException, Header, Depends
from fastapi.middleware.cors import CORSMiddleware
import psycopg2
import psycopg2.extras
import os
from typing import Optional
from pydantic import BaseModel
import hashlib
import time
import secrets

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

DATABASE_URL = os.environ.get("DATABASE_URL")
ADMIN_SECRET = os.environ.get("ADMIN_SECRET", "baita-admin-2026")

def get_db():
    return psycopg2.connect(DATABASE_URL)

def create_tables():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS listings (
            id TEXT PRIMARY KEY,
            title TEXT,
            neighborhood TEXT,
            city TEXT,
            rooms FLOAT,
            floor INTEGER,
            sqm INTEGER,
            price INTEGER,
            source TEXT,
            url TEXT,
            description TEXT,
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW(),
            is_active BOOLEAN DEFAULT TRUE
        );
        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY,
            full_name TEXT,
            email TEXT UNIQUE,
            whatsapp TEXT,
            age INTEGER,
            role TEXT,
            neighborhoods TEXT,
            password_hash TEXT,
            avatar_url TEXT,
            session_token TEXT,
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW()
        );
    """)
    conn.commit()
    cur.close()
    conn.close()

@app.on_event("startup")
async def startup():
    try:
        create_tables()
        print("DB connected")
    except Exception as e:
        print(f"DB error: {e}")

def hash_pwd(pwd):
    return hashlib.sha256(pwd.encode()).hexdigest()

def get_user_by_token(token):
    if not token:
        return None
    try:
        conn = get_db()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("SELECT * FROM users WHERE session_token = %s", (token,))
        user = cur.fetchone()
        cur.close()
        conn.close()
        return dict(user) if user else None
    except:
        return None

# ── ROOT ──────────────────────────────────────────────
@app.get("/")
def root():
    return {"status": "Baita API running"}

# ── LISTINGS ─────────────────────────────────────────
@app.get("/listings")
def get_listings(
    neighborhood: Optional[str] = None,
    min_price: Optional[int] = None,
    max_price: Optional[int] = None,
    rooms: Optional[float] = None,
    source: Optional[str] = None,
    new_today: Optional[bool] = False,
    sort: Optional[str] = "newest",
    limit: int = 20,
    offset: int = 0
):
    try:
        conn = get_db()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        q = "SELECT * FROM listings WHERE is_active = TRUE"
        p = []
        if neighborhood: q += " AND neighborhood ILIKE %s"; p.append(f"%{neighborhood}%")
        if min_price: q += " AND price >= %s"; p.append(min_price)
        if max_price: q += " AND price <= %s"; p.append(max_price)
        if rooms: q += " AND rooms = %s"; p.append(rooms)
        if source: q += " AND source = %s"; p.append(source)
        if new_today: q += " AND created_at >= NOW() - INTERVAL '24 hours'"
        if sort == "newest": q += " ORDER BY created_at DESC"
        elif sort == "price_asc": q += " ORDER BY price ASC"
        elif sort == "price_desc": q += " ORDER BY price DESC"
        q += " LIMIT %s OFFSET %s"; p.extend([limit, offset])
        cur.execute(q, p)
        listings = cur.fetchall()
        cur.execute("SELECT COUNT(*) as c FROM listings WHERE is_active = TRUE")
        total = cur.fetchone()["c"]
        cur.close(); conn.close()
        return {"total": total, "listings": [dict(l) for l in listings]}
    except Exception as e:
        return {"total": 0, "listings": [], "error": str(e)}

@app.get("/stats")
def get_stats():
    try:
        conn = get_db()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("SELECT COUNT(*) as total FROM listings WHERE is_active = TRUE")
        total = cur.fetchone()["total"]
        cur.execute("SELECT COUNT(DISTINCT source) as sources FROM listings")
        sources = cur.fetchone()["sources"]
        cur.execute("""
            SELECT neighborhood, COUNT(*) as count FROM listings
            WHERE is_active = TRUE AND created_at >= NOW() - INTERVAL '24 hours'
            GROUP BY neighborhood ORDER BY count DESC LIMIT 3
        """)
        trending = cur.fetchall()
        cur.close(); conn.close()
        return {"total_listings": total, "total_sources": sources, "trending": [dict(t) for t in trending]}
    except Exception as e:
        return {"total_listings": 0, "total_sources": 0, "trending": []}

class NewListing(BaseModel):
    title: str
    neighborhood: str
    price: int
    rooms: float = 0
    sqm: int = 0
    floor: int = 0
    description: str = ""
    contact_name: str = ""
    contact_phone: str = ""

@app.post("/listings/post")
def post_listing(listing: NewListing):
    try:
        lid = hashlib.md5(f"baita-{listing.title}-{time.time()}".encode()).hexdigest()
        conn = get_db()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO listings (id, title, neighborhood, city, rooms, floor, sqm, price, source, url, description)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (lid, listing.title, listing.neighborhood, "Tel Aviv",
              listing.rooms, listing.floor, listing.sqm, listing.price, "Baita", "#",
              listing.description + (f" | {listing.contact_name} {listing.contact_phone}" if listing.contact_name else "")))
        conn.commit(); cur.close(); conn.close()
        return {"success": True, "id": lid}
    except Exception as e:
        return {"success": False, "error": str(e)}

# ── AUTH ──────────────────────────────────────────────
class NewUser(BaseModel):
    full_name: str
    email: str
    whatsapp: str
    age: int = 0
    role: str = "seeker"
    neighborhoods: list = []
    password: str = ""
    avatar_url: str = ""

@app.post("/users/register")
def register(user: NewUser):
    try:
        uid = hashlib.md5(f"{user.email}-{time.time()}".encode()).hexdigest()
        pwd_hash = hash_pwd(user.password)
        token = secrets.token_urlsafe(32)
        nbhd = ",".join(user.neighborhoods)
        conn = get_db()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO users (id, full_name, email, whatsapp, age, role, neighborhoods, password_hash, avatar_url, session_token)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (email) DO UPDATE SET
                full_name = EXCLUDED.full_name,
                whatsapp = EXCLUDED.whatsapp,
                age = EXCLUDED.age,
                role = EXCLUDED.role,
                neighborhoods = EXCLUDED.neighborhoods,
                password_hash = EXCLUDED.password_hash,
                avatar_url = EXCLUDED.avatar_url,
                session_token = EXCLUDED.session_token,
                updated_at = NOW()
            RETURNING id, session_token
        """, (uid, user.full_name, user.email, user.whatsapp,
              user.age, user.role, nbhd, pwd_hash, user.avatar_url, token))
        row = cur.fetchone()
        conn.commit(); cur.close(); conn.close()
        return {"success": True, "token": token, "user_id": row[0]}
    except Exception as e:
        return {"success": False, "error": str(e)}

class LoginData(BaseModel):
    email: str
    password: str

@app.post("/users/login")
def login(data: LoginData):
    try:
        conn = get_db()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("SELECT * FROM users WHERE email = %s AND password_hash = %s",
                    (data.email, hash_pwd(data.password)))
        user = cur.fetchone()
        if not user:
            cur.close(); conn.close()
            return {"success": False, "error": "Invalid email or password"}
        token = secrets.token_urlsafe(32)
        cur2 = conn.cursor()
        cur2.execute("UPDATE users SET session_token = %s, updated_at = NOW() WHERE id = %s",
                     (token, user["id"]))
        conn.commit(); cur.close(); cur2.close(); conn.close()
        return {"success": True, "token": token, "user": {
            "id": user["id"], "full_name": user["full_name"],
            "email": user["email"], "role": user["role"],
            "whatsapp": user["whatsapp"], "age": user["age"],
            "neighborhoods": user["neighborhoods"],
            "avatar_url": user["avatar_url"]
        }}
    except Exception as e:
        return {"success": False, "error": str(e)}

@app.get("/users/me")
def get_me(authorization: Optional[str] = Header(None)):
    token = authorization.replace("Bearer ", "") if authorization else None
    user = get_user_by_token(token)
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")
    user.pop("password_hash", None)
    user.pop("session_token", None)
    return {"user": user}

class UpdateUser(BaseModel):
    full_name: Optional[str] = None
    whatsapp: Optional[str] = None
    age: Optional[int] = None
    neighborhoods: Optional[list] = None
    avatar_url: Optional[str] = None

@app.put("/users/me")
def update_me(data: UpdateUser, authorization: Optional[str] = Header(None)):
    token = authorization.replace("Bearer ", "") if authorization else None
    user = get_user_by_token(token)
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")
    try:
        fields = []
        vals = []
        if data.full_name: fields.append("full_name = %s"); vals.append(data.full_name)
        if data.whatsapp: fields.append("whatsapp = %s"); vals.append(data.whatsapp)
        if data.age: fields.append("age = %s"); vals.append(data.age)
        if data.neighborhoods is not None: fields.append("neighborhoods = %s"); vals.append(",".join(data.neighborhoods))
        if data.avatar_url: fields.append("avatar_url = %s"); vals.append(data.avatar_url)
        if not fields:
            return {"success": True}
        fields.append("updated_at = NOW()")
        vals.append(user["id"])
        conn = get_db()
        cur = conn.cursor()
        cur.execute(f"UPDATE users SET {', '.join(fields)} WHERE id = %s", vals)
        conn.commit(); cur.close(); conn.close()
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}

@app.post("/users/logout")
def logout(authorization: Optional[str] = Header(None)):
    token = authorization.replace("Bearer ", "") if authorization else None
    if token:
        try:
            conn = get_db()
            cur = conn.cursor()
            cur.execute("UPDATE users SET session_token = NULL WHERE session_token = %s", (token,))
            conn.commit(); cur.close(); conn.close()
        except: pass
    return {"success": True}

# ── ADMIN ─────────────────────────────────────────────
@app.get("/admin/stats")
def admin_stats(secret: str = Query(...)):
    if secret != ADMIN_SECRET:
        raise HTTPException(status_code=403, detail="Forbidden")
    try:
        conn = get_db()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("SELECT COUNT(*) as total FROM users")
        total_users = cur.fetchone()["total"]
        cur.execute("SELECT COUNT(*) as h FROM users WHERE role = 'host'")
        hosts = cur.fetchone()["h"]
        cur.execute("SELECT COUNT(*) as s FROM users WHERE role = 'seeker'")
        seekers = cur.fetchone()["s"]
        cur.execute("SELECT COUNT(*) as total FROM listings WHERE is_active = TRUE")
        total_listings = cur.fetchone()["total"]
        cur.execute("SELECT COUNT(*) as n FROM users WHERE created_at >= NOW() - INTERVAL '24 hours'")
        new_today = cur.fetchone()["n"]
        cur.close(); conn.close()
        return {"total_users": total_users, "hosts": hosts, "seekers": seekers,
                "total_listings": total_listings, "new_users_today": new_today}
    except Exception as e:
        return {"error": str(e)}

@app.get("/admin/users")
def admin_users(secret: str = Query(...), limit: int = 100, offset: int = 0):
    if secret != ADMIN_SECRET:
        raise HTTPException(status_code=403, detail="Forbidden")
    try:
        conn = get_db()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("""
            SELECT id, full_name, email, whatsapp, age, role, neighborhoods, avatar_url, created_at
            FROM users ORDER BY created_at DESC LIMIT %s OFFSET %s
        """, (limit, offset))
        users = cur.fetchall()
        cur.close(); conn.close()
        return {"users": [dict(u) for u in users]}
    except Exception as e:
        return {"users": [], "error": str(e)}

@app.get("/admin/listings")
def admin_listings(secret: str = Query(...), limit: int = 100, offset: int = 0):
    if secret != ADMIN_SECRET:
        raise HTTPException(status_code=403, detail="Forbidden")
    try:
        conn = get_db()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("SELECT * FROM listings ORDER BY created_at DESC LIMIT %s OFFSET %s", (limit, offset))
        listings = cur.fetchall()
        cur.close(); conn.close()
        return {"listings": [dict(l) for l in listings]}
    except Exception as e:
        return {"listings": [], "error": str(e)}
