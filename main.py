from fastapi import FastAPI, Query, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
import psycopg2
import psycopg2.extras
import os
from typing import Optional
from pydantic import BaseModel
import hashlib
import time

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
            created_at TIMESTAMP DEFAULT NOW()
        );
    """)
    conn.commit()
    cur.close()
    conn.close()

@app.on_event("startup")
async def startup():
    try:
        create_tables()
        print("✅ Base de données connectée")
    except Exception as e:
        print(f"⚠️ DB error: {e}")

@app.get("/")
def root():
    return {"status": "Baita API is running 🏠"}

# ─── LISTINGS ───────────────────────────────────────────

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
        query = "SELECT * FROM listings WHERE is_active = TRUE"
        params = []
        if neighborhood:
            query += " AND neighborhood ILIKE %s"
            params.append(f"%{neighborhood}%")
        if min_price:
            query += " AND price >= %s"
            params.append(min_price)
        if max_price:
            query += " AND price <= %s"
            params.append(max_price)
        if rooms:
            query += " AND rooms = %s"
            params.append(rooms)
        if source:
            query += " AND source = %s"
            params.append(source)
        if new_today:
            query += " AND created_at >= NOW() - INTERVAL '24 hours'"
        if sort == "newest":
            query += " ORDER BY created_at DESC"
        elif sort == "price_asc":
            query += " ORDER BY price ASC"
        elif sort == "price_desc":
            query += " ORDER BY price DESC"
        query += " LIMIT %s OFFSET %s"
        params.extend([limit, offset])
        cur.execute(query, params)
        listings = cur.fetchall()
        cur.execute("SELECT COUNT(*) as c FROM listings WHERE is_active = TRUE")
        total = cur.fetchone()["c"]
        cur.close()
        conn.close()
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
            SELECT neighborhood, COUNT(*) as count
            FROM listings WHERE is_active = TRUE
            AND created_at >= NOW() - INTERVAL '24 hours'
            GROUP BY neighborhood ORDER BY count DESC LIMIT 3
        """)
        trending = cur.fetchall()
        cur.close()
        conn.close()
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
              listing.rooms, listing.floor, listing.sqm, listing.price,
              "Baita", "#",
              listing.description + (f" | Contact: {listing.contact_name} {listing.contact_phone}" if listing.contact_name else "")))
        conn.commit()
        cur.close()
        conn.close()
        return {"success": True, "id": lid}
    except Exception as e:
        return {"success": False, "error": str(e)}

# ─── USERS ───────────────────────────────────────────────

class NewUser(BaseModel):
    full_name: str
    email: str
    whatsapp: str
    age: int = 0
    role: str = "seeker"
    neighborhoods: list = []
    password: str = ""

@app.post("/users/register")
def register_user(user: NewUser):
    try:
        uid = hashlib.md5(f"{user.email}-{time.time()}".encode()).hexdigest()
        pwd_hash = hashlib.sha256(user.password.encode()).hexdigest()
        neighborhoods_str = ",".join(user.neighborhoods)
        conn = get_db()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO users (id, full_name, email, whatsapp, age, role, neighborhoods, password_hash)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (email) DO UPDATE SET
                full_name = EXCLUDED.full_name,
                whatsapp = EXCLUDED.whatsapp,
                age = EXCLUDED.age,
                role = EXCLUDED.role,
                neighborhoods = EXCLUDED.neighborhoods
        """, (uid, user.full_name, user.email, user.whatsapp,
              user.age, user.role, neighborhoods_str, pwd_hash))
        conn.commit()
        cur.close()
        conn.close()
        return {"success": True, "id": uid}
    except Exception as e:
        return {"success": False, "error": str(e)}

# ─── ADMIN ───────────────────────────────────────────────

@app.get("/admin/stats")
def admin_stats(secret: str = Query(...)):
    if secret != ADMIN_SECRET:
        raise HTTPException(status_code=403, detail="Forbidden")
    try:
        conn = get_db()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("SELECT COUNT(*) as total FROM users")
        total_users = cur.fetchone()["total"]
        cur.execute("SELECT COUNT(*) as total FROM users WHERE role = 'host'")
        hosts = cur.fetchone()["total"]
        cur.execute("SELECT COUNT(*) as total FROM users WHERE role = 'seeker'")
        seekers = cur.fetchone()["total"]
        cur.execute("SELECT COUNT(*) as total FROM listings WHERE is_active = TRUE")
        total_listings = cur.fetchone()["total"]
        cur.execute("SELECT COUNT(*) as total FROM users WHERE created_at >= NOW() - INTERVAL '24 hours'")
        new_today = cur.fetchone()["total"]
        cur.close()
        conn.close()
        return {
            "total_users": total_users,
            "hosts": hosts,
            "seekers": seekers,
            "total_listings": total_listings,
            "new_users_today": new_today
        }
    except Exception as e:
        return {"error": str(e)}

@app.get("/admin/users")
def admin_users(secret: str = Query(...), limit: int = 50, offset: int = 0):
    if secret != ADMIN_SECRET:
        raise HTTPException(status_code=403, detail="Forbidden")
    try:
        conn = get_db()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("""
            SELECT id, full_name, email, whatsapp, age, role, neighborhoods, created_at
            FROM users ORDER BY created_at DESC LIMIT %s OFFSET %s
        """, (limit, offset))
        users = cur.fetchall()
        cur.close()
        conn.close()
        return {"users": [dict(u) for u in users]}
    except Exception as e:
        return {"users": [], "error": str(e)}

@app.get("/admin/listings")
def admin_listings(secret: str = Query(...), limit: int = 50, offset: int = 0):
    if secret != ADMIN_SECRET:
        raise HTTPException(status_code=403, detail="Forbidden")
    try:
        conn = get_db()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("""
            SELECT * FROM listings ORDER BY created_at DESC LIMIT %s OFFSET %s
        """, (limit, offset))
        listings = cur.fetchall()
        cur.close()
        conn.close()
        return {"listings": [dict(l) for l in listings]}
    except Exception as e:
        return {"listings": [], "error": str(e)}
