from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
import psycopg2
import psycopg2.extras
import os
from typing import Optional

app = FastAPI()

# Permet au frontend de parler au backend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

DATABASE_URL = os.environ.get("DATABASE_URL")

def get_db():
    return psycopg2.connect(DATABASE_URL)

@app.on_event("startup")
async def startup():
    create_tables()

@app.get("/")
def root():
    return {"status": "Baita API is running 🏠"}

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
    
    # Total count
    count_query = "SELECT COUNT(*) FROM listings WHERE is_active = TRUE"
    cur.execute(count_query)
    total = cur.fetchone()["count"]
    
    cur.close()
    conn.close()
    
    return {
        "total": total,
        "listings": [dict(l) for l in listings]
    }

@app.get("/stats")
def get_stats():
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    
    cur.execute("SELECT COUNT(*) as total FROM listings WHERE is_active = TRUE")
    total = cur.fetchone()["total"]
    
    cur.execute("SELECT COUNT(DISTINCT source) as sources FROM listings")
    sources = cur.fetchone()["sources"]
    
    cur.execute("""
        SELECT neighborhood, COUNT(*) as count 
        FROM listings 
        WHERE is_active = TRUE AND created_at >= NOW() - INTERVAL '24 hours'
        GROUP BY neighborhood 
        ORDER BY count DESC 
        LIMIT 3
    """)
    trending = cur.fetchall()
    
    cur.close()
    conn.close()
    
    return {
        "total_listings": total,
        "total_sources": sources,
        "trending": [dict(t) for t in trending]
    }
