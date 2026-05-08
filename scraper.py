import psycopg2
import os
import time
import hashlib
import requests
from datetime import datetime
 
DATABASE_URL = os.environ.get("DATABASE_URL")
 
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
    """)
    conn.commit()
    cur.close()
    conn.close()
    print("✅ Tables OK")
 
def make_id(s):
    return hashlib.md5(s.encode()).hexdigest()
 
def save_listing(listing):
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO listings (id, title, neighborhood, city, rooms, floor, sqm, price, source, url, description)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (id) DO UPDATE SET
                price = EXCLUDED.price,
                updated_at = NOW(),
                is_active = TRUE
        """, (
            listing["id"], listing["title"], listing["neighborhood"],
            listing["city"], listing["rooms"], listing["floor"],
            listing["sqm"], listing["price"], listing["source"],
            listing["url"], listing["description"]
        ))
        conn.commit()
        cur.close()
        conn.close()
        return True
    except Exception as e:
        print(f"❌ Save error: {e}")
        return False
 
def scrape_yad2():
    print("🔍 Scraping Yad2...")
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "he-IL,he;q=0.9,en-US;q=0.8",
        "Referer": "https://www.yad2.co.il/realestate/rent",
    }
    url = "https://gw.yad2.co.il/feed-search-legacy/realestate/rent"
    params = {
        "city": "5000",
        "priceOnly": "1",
        "forceLdLoad": "true"
    }
    try:
        r = requests.get(url, headers=headers, params=params, timeout=20)
        print(f"Yad2 status: {r.status_code}")
        data = r.json()
        items = data.get("data", {}).get("feed", {}).get("feed_items", [])
        count = 0
        for item in items:
            if item.get("type") == "ad":
                try:
                    l = {
                        "id": make_id("yad2-" + str(item.get("id", ""))),
                        "title": item.get("title", "Appartement à Tel Aviv"),
                        "neighborhood": item.get("neighborhood", {}).get("text", "Tel Aviv") if isinstance(item.get("neighborhood"), dict) else str(item.get("neighborhood", "Tel Aviv")),
                        "city": "Tel Aviv",
                        "rooms": float(item.get("rooms", 0) or 0),
                        "floor": int(item.get("floor", 0) or 0),
                        "sqm": int(item.get("square_meters", 0) or 0),
                        "price": int(item.get("price", 0) or 0),
                        "source": "Yad2",
                        "url": "https://www.yad2.co.il/item/" + str(item.get("id", "")),
                        "description": str(item.get("info_text", ""))
                    }
                    if save_listing(l):
                        count += 1
                except Exception as e:
                    print(f"Item error: {e}")
                    continue
        print(f"✅ Yad2: {count} annonces")
    except Exception as e:
        print(f"❌ Yad2 error: {e}")
 
def scrape_madlan():
    print("🔍 Scraping Madlan...")
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        "Accept": "application/json",
        "Referer": "https://www.madlan.co.il/",
        "Origin": "https://www.madlan.co.il"
    }
    url = "https://www.madlan.co.il/api2/listings/search"
    params = {"q": "תל אביב", "dealType": "rent", "pageNum": 1, "pageSize": 40}
    try:
        r = requests.get(url, headers=headers, params=params, timeout=20)
        print(f"Madlan status: {r.status_code}")
        data = r.json()
        items = data.get("listings", [])
        count = 0
        for item in items:
            try:
                l = {
                    "id": make_id("madlan-" + str(item.get("id", ""))),
                    "title": item.get("title", "Appartement à Tel Aviv"),
                    "neighborhood": item.get("neighborhood", "Tel Aviv"),
                    "city": "Tel Aviv",
                    "rooms": float(item.get("rooms", 0) or 0),
                    "floor": int(item.get("floor", 0) or 0),
                    "sqm": int(item.get("squareMeters", 0) or 0),
                    "price": int(item.get("price", 0) or 0),
                    "source": "Madlan",
                    "url": "https://www.madlan.co.il/listing/" + str(item.get("id", "")),
                    "description": item.get("description", "")
                }
                if save_listing(l):
                    count += 1
            except Exception as e:
                continue
        print(f"✅ Madlan: {count} annonces")
    except Exception as e:
        print(f"❌ Madlan error: {e}")
 
def add_test_listings():
    print("📝 Ajout annonces de test...")
    test = [
        {"id": make_id("test-1"), "title": "Bright 3-room with terrace", "neighborhood": "Neve Tzedek", "city": "Tel Aviv", "rooms": 3.0, "floor": 2, "sqm": 78, "price": 9500, "source": "Yad2", "url": "https://www.yad2.co.il", "description": "Beautiful apartment"},
        {"id": make_id("test-2"), "title": "Renovated 2-room, charming block", "neighborhood": "Florentin", "city": "Tel Aviv", "rooms": 2.0, "floor": 3, "sqm": 52, "price": 5900, "source": "Madlan", "url": "https://www.madlan.co.il", "description": "Renovated"},
        {"id": make_id("test-3"), "title": "Penthouse studio, city views", "neighborhood": "Rothschild", "city": "Tel Aviv", "rooms": 1.0, "floor": 8, "sqm": 38, "price": 7200, "source": "Yad2", "url": "https://www.yad2.co.il", "description": "Amazing views"},
        {"id": make_id("test-4"), "title": "Spacious 4-room near the beach", "neighborhood": "Gordon", "city": "Tel Aviv", "rooms": 4.0, "floor": 4, "sqm": 105, "price": 13500, "source": "Homeless", "url": "https://www.homeless.co.il", "description": "Near beach"},
        {"id": make_id("test-5"), "title": "Authentic 2-room, high ceilings", "neighborhood": "Kerem HaTeimanim", "city": "Tel Aviv", "rooms": 2.0, "floor": 1, "sqm": 60, "price": 6400, "source": "Komo", "url": "https://www.komo.co.il", "description": "High ceilings"},
        {"id": make_id("test-6"), "title": "Modern 3-room, fully furnished", "neighborhood": "Lev Tel Aviv", "city": "Tel Aviv", "rooms": 3.0, "floor": 5, "sqm": 88, "price": 11200, "source": "Yad2", "url": "https://www.yad2.co.il", "description": "Furnished"},
    ]
    count = 0
    for l in test:
        if save_listing(l):
            count += 1
    print(f"✅ {count} annonces de test ajoutées")
 
def run():
    print(f"\n🚀 Scraping démarré {datetime.now().strftime('%H:%M:%S')}")
    create_tables()
    add_test_listings()  # Toujours garder des annonces de test
    scrape_yad2()
    scrape_madlan()
    print(f"✅ Terminé {datetime.now().strftime('%H:%M:%S')}\n")
 
if __name__ == "__main__":
    while True:
        run()
        print("⏳ Prochain scraping dans 20 minutes...")
        time.sleep(20 * 60)
