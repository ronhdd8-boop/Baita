import requests
from bs4 import BeautifulSoup
import psycopg2
import os
import time
import hashlib
import json
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
    print("✅ Tables créées")

def make_id(url):
    return hashlib.md5(url.encode()).hexdigest()

def save_listing(listing):
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

def scrape_yad2():
    print("🔍 Scraping Yad2...")
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        "Accept-Language": "he-IL,he;q=0.9,en;q=0.8",
    }
    
    # Yad2 API endpoint for Tel Aviv long-term rentals
    url = "https://gw.yad2.co.il/feed-search-legacy/realestate/rent"
    params = {
        "city": "5000",  # Tel Aviv
        "priceOnly": "1",
        "forceLdLoad": "true"
    }
    
    try:
        response = requests.get(url, headers=headers, params=params, timeout=15)
        data = response.json()
        items = data.get("data", {}).get("feed", {}).get("feed_items", [])
        
        count = 0
        for item in items:
            if item.get("type") == "ad":
                try:
                    listing = {
                        "id": make_id("yad2-" + str(item.get("id", ""))),
                        "title": item.get("title", "Appartement à Tel Aviv"),
                        "neighborhood": item.get("neighborhood", {}).get("text", "Tel Aviv"),
                        "city": "Tel Aviv",
                        "rooms": float(item.get("rooms", 0)),
                        "floor": int(item.get("floor", 0)),
                        "sqm": int(item.get("square_meters", 0)),
                        "price": int(item.get("price", 0)),
                        "source": "Yad2",
                        "url": "https://www.yad2.co.il/item/" + str(item.get("id", "")),
                        "description": item.get("info_text", "")
                    }
                    save_listing(listing)
                    count += 1
                except Exception as e:
                    continue
        
        print(f"✅ Yad2: {count} annonces sauvegardées")
    except Exception as e:
        print(f"❌ Erreur Yad2: {e}")

def scrape_madlan():
    print("🔍 Scraping Madlan...")
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        "Accept": "application/json",
        "Referer": "https://www.madlan.co.il/"
    }
    
    url = "https://www.madlan.co.il/api2/listings/search"
    params = {
        "q": "תל אביב",
        "dealType": "rent",
        "pageNum": 1,
        "pageSize": 50
    }
    
    try:
        response = requests.get(url, headers=headers, params=params, timeout=15)
        data = response.json()
        items = data.get("listings", [])
        
        count = 0
        for item in items:
            try:
                listing = {
                    "id": make_id("madlan-" + str(item.get("id", ""))),
                    "title": item.get("title", "Appartement à Tel Aviv"),
                    "neighborhood": item.get("neighborhood", "Tel Aviv"),
                    "city": "Tel Aviv",
                    "rooms": float(item.get("rooms", 0)),
                    "floor": int(item.get("floor", 0)),
                    "sqm": int(item.get("squareMeters", 0)),
                    "price": int(item.get("price", 0)),
                    "source": "Madlan",
                    "url": "https://www.madlan.co.il/listing/" + str(item.get("id", "")),
                    "description": item.get("description", "")
                }
                save_listing(listing)
                count += 1
            except Exception as e:
                continue
        
        print(f"✅ Madlan: {count} annonces sauvegardées")
    except Exception as e:
        print(f"❌ Erreur Madlan: {e}")

def run():
    print(f"\n🚀 Scraping démarré à {datetime.now().strftime('%H:%M:%S')}")
    create_tables()
    scrape_yad2()
    scrape_madlan()
    print(f"✅ Scraping terminé à {datetime.now().strftime('%H:%M:%S')}\n")

if __name__ == "__main__":
    # Tourne en boucle toutes les 20 minutes
    while True:
        run()
        print("⏳ Prochain scraping dans 20 minutes...")
        time.sleep(20 * 60)
