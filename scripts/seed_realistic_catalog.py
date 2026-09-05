import sqlite3
import random
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "databases" / "inventory.db"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.executescript("""
        DROP TABLE IF EXISTS cart_items;
        DROP TABLE IF EXISTS product_variants;
        DROP TABLE IF EXISTS products;
        DROP TABLE IF EXISTS categories;
        DROP TABLE IF EXISTS products_fts;
        DROP TABLE IF EXISTS products_fts_data;
        DROP TABLE IF EXISTS products_fts_idx;
        DROP TABLE IF EXISTS products_fts_content;
        DROP TABLE IF EXISTS products_fts_docsize;
        DROP TABLE IF EXISTS products_fts_config;

        CREATE TABLE categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            slug TEXT NOT NULL UNIQUE,
            description TEXT
        );

        CREATE TABLE products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            brand TEXT NOT NULL,
            category_tree TEXT,
            description TEXT NOT NULL,
            base_price REAL NOT NULL,
            rating REAL DEFAULT 4.5,
            tags TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (category_id) REFERENCES categories (id) ON DELETE CASCADE
        );

        CREATE TABLE product_variants (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id INTEGER NOT NULL,
            sku TEXT NOT NULL UNIQUE,
            color TEXT,
            size TEXT,
            style_or_spec TEXT,
            price REAL NOT NULL,
            stock_quantity INTEGER NOT NULL DEFAULT 50,
            image_url TEXT,
            FOREIGN KEY (product_id) REFERENCES products (id) ON DELETE CASCADE
        );

        CREATE TABLE cart_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            product_id INTEGER NOT NULL,
            variant_id INTEGER NOT NULL,
            quantity INTEGER NOT NULL DEFAULT 1,
            added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (product_id) REFERENCES products (id) ON DELETE CASCADE,
            FOREIGN KEY (variant_id) REFERENCES product_variants (id) ON DELETE CASCADE
        );

        CREATE VIRTUAL TABLE products_fts USING fts5(
            product_id UNINDEXED,
            title,
            brand,
            category_name,
            category_tree,
            description,
            tags
        );
    """)
    conn.commit()
    return conn

# -- RAW CATALOG DATA --

CATEGORIES = [
    ("Mobiles & Accessories", "mobiles-accessories", "Smartphones and mobile accessories"),
    ("Computers", "computers", "Laptops, desktops, and computer peripherals"),
    ("Electronics & Gadgets", "electronics-gadgets", "Audio, wearables, and electronic gadgets"),
    ("Clothing", "clothing", "Men's and Women's topwear and bottomwear"),
    ("Footwear", "footwear", "Running shoes, sneakers, and sports footwear")
]

# (category, title, brand, price, rating, desc_specs, variants)
# variants = [(color, size/spec, price_modifier)]
PRODUCTS = [
    # MOBILES
    ("Mobiles & Accessories", "Apple iPhone 15", "Apple", 69999, 4.8, "Battery: 3349 mAh | Processor: A16 Bionic | RAM: 6GB | Camera: 48MP OIS | Display: 6.1-inch Super Retina XDR OLED", [("Black", "128GB", 0), ("Blue", "128GB", 0), ("Black", "256GB", 10000)]),
    ("Mobiles & Accessories", "Apple iPhone 15 Pro", "Apple", 124999, 4.9, "Battery: 3274 mAh | Processor: A17 Pro | RAM: 8GB | Camera: 48MP OIS + 3x Telephoto | Display: 120Hz ProMotion OLED", [("Natural Titanium", "256GB", 0), ("Black Titanium", "256GB", 0)]),
    ("Mobiles & Accessories", "Samsung Galaxy S24 Ultra", "Samsung", 129999, 4.9, "Battery: 5000 mAh | Processor: Snapdragon 8 Gen 3 | RAM: 12GB | Camera: 200MP + 5x Optical | Display: 120Hz AMOLED S-Pen", [("Titanium Gray", "256GB", 0), ("Titanium Black", "512GB", 10000)]),
    ("Mobiles & Accessories", "Samsung Galaxy S23 FE", "Samsung", 42999, 4.3, "Battery: 4500 mAh | Processor: Exynos 2200 | RAM: 8GB | Camera: 50MP OIS | Display: 120Hz AMOLED", [("Mint", "128GB", 0), ("Graphite", "128GB", 0)]),
    ("Mobiles & Accessories", "Samsung Galaxy M55", "Samsung", 26999, 4.2, "Battery: 5000 mAh | Processor: Snapdragon 7 Gen 1 | RAM: 8GB | Camera: 50MP OIS | Display: 120Hz Super AMOLED+", [("Light Green", "128GB", 0), ("Black", "256GB", 2000)]),
    ("Mobiles & Accessories", "OnePlus 12", "OnePlus", 64999, 4.7, "Battery: 5400 mAh | Processor: Snapdragon 8 Gen 3 | RAM: 12GB | Camera: 50MP Hasselblad | Display: 120Hz ProXDR 2K", [("Flowy Emerald", "256GB", 0), ("Silky Black", "256GB", 0)]),
    ("Mobiles & Accessories", "OnePlus 12R", "OnePlus", 39999, 4.6, "Battery: 5500 mAh | Processor: Snapdragon 8 Gen 2 | RAM: 8GB | Charging: 100W SuperVOOC | Display: 120Hz AMOLED", [("Iron Gray", "128GB", 0), ("Cool Blue", "256GB", 3000)]),
    ("Mobiles & Accessories", "OnePlus Nord CE 4", "OnePlus", 24999, 4.5, "Battery: 5500 mAh | Processor: Snapdragon 7 Gen 3 | RAM: 8GB | Charging: 100W SuperVOOC | Display: 120Hz Fluid AMOLED", [("Celadon Marble", "128GB", 0), ("Dark Chrome", "256GB", 2000)]),
    ("Mobiles & Accessories", "iQOO Neo 9 Pro", "iQOO", 36999, 4.6, "Battery: 5160 mAh | Processor: Snapdragon 8 Gen 2 | RAM: 8GB | Charging: 120W FlashCharge | Display: 144Hz AMOLED Gaming", [("Fiery Red", "256GB", 0), ("Conqueror Black", "256GB", 0)]),
    ("Mobiles & Accessories", "Poco X6 Pro", "Poco", 25999, 4.4, "Battery: 5000 mAh | Processor: Dimensity 8300 Ultra | RAM: 8GB | Charging: 67W Turbo | Display: 120Hz 1.5K AMOLED", [("Yellow", "256GB", 0), ("Black", "256GB", 0)]),
    ("Mobiles & Accessories", "Realme GT 6T", "Realme", 30999, 4.5, "Battery: 5500 mAh | Processor: Snapdragon 7+ Gen 3 | RAM: 8GB | Charging: 120W SuperVOOC | Display: 120Hz 8T LTPO AMOLED", [("Fluid Silver", "128GB", 0), ("Razor Green", "256GB", 2000)]),
    ("Mobiles & Accessories", "Vivo V30 Pro", "Vivo", 41999, 4.5, "Battery: 5000 mAh | Processor: Dimensity 8200 | RAM: 8GB | Camera: 50MP Zeiss Quad | Display: 120Hz 3D Curved AMOLED", [("Andaman Blue", "256GB", 0), ("Classic Black", "256GB", 0)]),
    ("Mobiles & Accessories", "Nothing Phone (2a)", "Nothing", 23999, 4.4, "Battery: 5000 mAh | Processor: Dimensity 7200 Pro | RAM: 8GB | Camera: 50MP Dual | Display: 120Hz AMOLED Glyph Interface", [("Black", "128GB", 0), ("White", "128GB", 0)]),
    ("Mobiles & Accessories", "Motorola Edge 50 Pro", "Motorola", 31999, 4.5, "Battery: 4500 mAh | Processor: Snapdragon 7 Gen 3 | RAM: 8GB | Charging: 125W TurboPower | Display: 144Hz pOLED", [("Luxe Lavender", "256GB", 0), ("Black Beauty", "256GB", 0)]),
    ("Mobiles & Accessories", "Google Pixel 8a", "Google", 52999, 4.5, "Battery: 4492 mAh | Processor: Tensor G3 | RAM: 8GB | Camera: 64MP OIS Pixel AI | Display: 120Hz OLED", [("Obsidian", "128GB", 0), ("Bay", "128GB", 0)]),

    # COMPUTERS (Laptops)
    ("Computers", "Apple MacBook Air M2", "Apple", 89990, 4.8, "CPU: Apple M2 | GPU: 8-Core | RAM: 8GB | SSD: 256GB | Battery: 52.6 Whr | Display: 13.6-inch Liquid Retina", [("Midnight", "256GB", 0), ("Starlight", "256GB", 0)]),
    ("Computers", "Apple MacBook Pro M3", "Apple", 169990, 4.9, "CPU: Apple M3 | GPU: 10-Core | RAM: 8GB | SSD: 512GB | Battery: 70 Whr | Display: 14.2-inch Liquid Retina XDR", [("Space Black", "512GB", 0), ("Silver", "512GB", 0)]),
    ("Computers", "Lenovo LOQ 15 Gaming", "Lenovo", 74990, 4.6, "CPU: Intel i5-13450HX | GPU: RTX 4050 6GB (95W TGP) | RAM: 16GB DDR5 | SSD: 512GB | Battery: 60 Whr | Display: 144Hz FHD", [("Storm Grey", "16GB RAM", 0)]),
    ("Computers", "Lenovo Legion Pro 5i", "Lenovo", 134990, 4.8, "CPU: Intel i7-14650HX | GPU: RTX 4060 8GB (140W TGP) | RAM: 16GB DDR5 | SSD: 1TB | Battery: 80 Whr | Display: 165Hz WQXGA", [("Onyx Grey", "1TB SSD", 0)]),
    ("Computers", "Asus TUF Gaming A15", "Asus", 69990, 4.5, "CPU: AMD Ryzen 7 7735HS | GPU: RTX 3050 4GB (75W TGP) | RAM: 16GB DDR5 | SSD: 512GB | Battery: 90 Whr | Display: 144Hz FHD", [("Jaeger Gray", "512GB SSD", 0)]),
    ("Computers", "Asus ROG Zephyrus G14", "Asus", 149990, 4.7, "CPU: AMD Ryzen 9 8945HS | GPU: RTX 4060 8GB (90W TGP) | RAM: 16GB LPDDR5X | SSD: 1TB | Battery: 73 Whr | Display: 120Hz 3K OLED", [("Eclipse Gray", "1TB SSD", 0)]),
    ("Computers", "HP Victus 15", "HP", 59990, 4.3, "CPU: Intel i5-13420H | GPU: RTX 3050 6GB (75W TGP) | RAM: 16GB DDR4 | SSD: 512GB | Battery: 70 Whr | Display: 144Hz FHD", [("Mica Silver", "16GB RAM", 0)]),
    ("Computers", "HP Omen 16", "HP", 109990, 4.6, "CPU: AMD Ryzen 7 7840HS | GPU: RTX 4060 8GB (140W TGP) | RAM: 16GB DDR5 | SSD: 1TB | Battery: 83 Whr | Display: 165Hz FHD", [("Shadow Black", "1TB SSD", 0)]),
    ("Computers", "Acer Nitro V Gaming", "Acer", 72990, 4.5, "CPU: Intel i5-13420H | GPU: RTX 4050 6GB (75W TGP) | RAM: 16GB DDR5 | SSD: 512GB | Battery: 57 Whr | Display: 144Hz FHD", [("Black", "512GB SSD", 0)]),
    ("Computers", "Acer Predator Helios Neo 16", "Acer", 114990, 4.7, "CPU: Intel i7-13700HX | GPU: RTX 4060 8GB (140W TGP) | RAM: 16GB DDR5 | SSD: 1TB | Battery: 90 Whr | Display: 165Hz WQXGA", [("Abyssal Black", "1TB SSD", 0)]),
    ("Computers", "Dell G15 5530", "Dell", 82990, 4.4, "CPU: Intel i5-13450HX | GPU: RTX 3050 6GB (95W TGP) | RAM: 16GB DDR5 | SSD: 512GB | Battery: 86 Whr | Display: 120Hz FHD", [("Dark Shadow Gray", "512GB SSD", 0)]),
    ("Computers", "Dell XPS 13", "Dell", 129990, 4.6, "CPU: Intel Core Ultra 7 155H | GPU: Intel Arc | RAM: 16GB LPDDR5x | SSD: 512GB | Battery: 55 Whr | Display: 13.4-inch FHD+ InfinityEdge", [("Platinum", "512GB SSD", 0)]),
    ("Computers", "MSI Cyborg 15", "MSI", 65990, 4.3, "CPU: Intel i5-12450H | GPU: RTX 4050 6GB (45W TGP) | RAM: 16GB DDR5 | SSD: 512GB | Battery: 53.5 Whr | Display: 144Hz FHD", [("Translucent Black", "16GB RAM", 0)]),
    ("Computers", "IdeaPad Slim 3", "Lenovo", 39990, 4.3, "CPU: Intel i3-1215U | GPU: Intel UHD | RAM: 8GB DDR4 | SSD: 512GB | Battery: 47 Whr | Display: 15.6-inch FHD", [("Arctic Grey", "8GB RAM", 0)]),

    # ELECTRONICS & GADGETS
    ("Electronics & Gadgets", "Sony WH-1000XM5 ANC Headphones", "Sony", 26990, 4.8, "Active Noise Cancellation: Industry Leading | Battery: 30 hours | Weight: 250g | Feature: Speak-to-chat, Multipoint", [("Black", "Standard", 0), ("Silver", "Standard", 0)]),
    ("Electronics & Gadgets", "Apple AirPods Pro (2nd Gen)", "Apple", 24900, 4.8, "Active Noise Cancellation: 2x stronger | Battery: 6 hours (30h with case) | Feature: MagSafe USB-C, Spatial Audio", [("White", "USB-C", 0)]),
    ("Electronics & Gadgets", "boAt Nirvana Ion ANC Earbuds", "boAt", 2499, 4.2, "Active Noise Cancellation: 32dB | Battery: 120 hours total | Driver: 10mm dual | Feature: Multipoint, ENx Tech", [("Ivory White", "Standard", 0), ("Charcoal Black", "Standard", 0)]),
    ("Electronics & Gadgets", "Nothing Ear (a) Wireless Earbuds", "Nothing", 7999, 4.5, "Active Noise Cancellation: 45dB Smart ANC | Battery: 9.5 hours (42.5h with case) | Driver: 11mm Custom | Feature: ChatGPT integrated", [("Yellow", "Standard", 0), ("White", "Standard", 0)]),
    ("Electronics & Gadgets", "CMF by Nothing Buds Pro", "CMF", 2999, 4.3, "Active Noise Cancellation: 45dB | Battery: 11 hours (39h with case) | Feature: Ultra Bass Tech, Wind Noise Reduction", [("Orange", "Standard", 0), ("Dark Grey", "Standard", 0)]),
    ("Electronics & Gadgets", "Logitech MX Master 3S Wireless Mouse", "Logitech", 9999, 4.8, "Sensor: 8000 DPI Darkfield | Battery: 70 days | Feature: Quiet clicks, MagSpeed wheel, Multi-device", [("Graphite", "Standard", 0), ("Pale Grey", "Standard", 0)]),
    ("Electronics & Gadgets", "Logitech G Pro X Superlight", "Logitech", 11999, 4.7, "Sensor: HERO 25K | Weight: <63g | Battery: 70 hours | Feature: Zero-additive PTFE feet, Esports ready", [("Black", "Standard", 0), ("White", "Standard", 0)]),
    ("Electronics & Gadgets", "Keychron K8 Pro Mechanical Keyboard", "Keychron", 9499, 4.6, "Switches: Gateron G Pro Red/Brown | Layout: TKL | Feature: QMK/VIA support, Hot-swappable, Bluetooth", [("Black", "Brown Switch", 0), ("Black", "Red Switch", 0)]),
    ("Electronics & Gadgets", "Anker 735 Nano II 65W GaN Charger", "Anker", 3999, 4.7, "Output: 65W Max | Ports: 2x USB-C, 1x USB-A | Feature: GaN II Tech, Compact design", [("Black", "65W", 0)]),
    ("Electronics & Gadgets", "Samsung T7 1TB Portable SSD", "Samsung", 8499, 4.8, "Capacity: 1TB | Speed: 1050 MB/s Read, 1000 MB/s Write | Interface: USB 3.2 Gen 2 | Feature: AES 256-bit encryption", [("Titan Gray", "1TB", 0), ("Indigo Blue", "1TB", 0)]),

    # CLOTHING
    ("Clothing", "Nike Dri-FIT UV Miler Training Tee", "Nike", 1795, 4.6, "Fabric: 100% Polyester Dri-FIT | Fit: Regular | Feature: Sweat-wicking, UV Protection, Reflective details", [("Black", "M", 0), ("Black", "L", 0), ("White", "M", 0), ("White", "L", 0)]),
    ("Clothing", "Under Armour Tech 2.0 Short Sleeve Tee", "Under Armour", 1499, 4.5, "Fabric: UA Tech (ultra-soft) | Fit: Loose, oversized | Feature: Quick-dry, Anti-odor technology", [("Carbon Heather", "M", 0), ("Carbon Heather", "L", 0), ("Royal Blue", "M", 0)]),
    ("Clothing", "Gymshark Crest Oversized T-Shirt", "Gymshark", 2499, 4.7, "Fabric: 95% Cotton, 5% Elastane | Fit: Oversized drop shoulder | Feature: Pump cover, Heavyweight premium cotton", [("Black", "M", 0), ("Black", "L", 0), ("Light Grey", "M", 0)]),
    ("Clothing", "Levi's 501 Original Fit Men's Jeans", "Levi's", 3299, 4.6, "Fabric: 100% Cotton Denim | Fit: Straight, Mid Rise | Feature: Button fly, Classic 5-pocket styling", [("Dark Indigo", "32", 0), ("Dark Indigo", "34", 0), ("Light Blue", "32", 0)]),
    ("Clothing", "H&M Relaxed Fit Heavyweight Hoodie", "H&M", 1999, 4.4, "Fabric: Cotton blend fleece | Fit: Relaxed | Feature: Kangaroo pocket, Drop shoulders, Ribbed cuffs", [("Greige", "M", 0), ("Greige", "L", 0), ("Black", "M", 0)]),

    # FOOTWEAR
    ("Footwear", "Nike Air Zoom Pegasus 40", "Nike", 10495, 4.7, "Type: Daily Running | Midsole: Nike React + Zoom Air units | Drop: 10mm | Feature: Highly responsive, breathable mesh", [("Black/White", "8", 0), ("Black/White", "9", 0), ("Black/White", "10", 0)]),
    ("Footwear", "Asics Gel-Kayano 30", "Asics", 14999, 4.8, "Type: Stability Running | Midsole: FF BLAST PLUS ECO | Drop: 10mm | Feature: PureGEL technology, 4D GUIDANCE SYSTEM for marathon support", [("Midnight/White", "9", 0), ("Midnight/White", "10", 0)]),
    ("Footwear", "Puma Deviate Nitro 2", "Puma", 12999, 4.6, "Type: Carbon Plate Running | Midsole: NITRO Elite foam | Feature: PWRPLATE for propulsion, PUMAGRIP outsole", [("Fire Orchid", "8", 0), ("Fire Orchid", "9", 0)]),
    ("Footwear", "Adidas Ultraboost Light", "Adidas", 15999, 4.7, "Type: Max Cushion Running | Midsole: Light BOOST (30% lighter) | Drop: 10mm | Feature: LEP 2.0 system, Primeknit+ forged upper", [("Core Black", "9", 0), ("Core Black", "10", 0)]),
]

def run():
    print("Initializing Database and clearing old data...")
    conn = init_db()
    cursor = conn.cursor()

    print("Inserting Categories...")
    cat_map = {}
    for cat_name, slug, desc in CATEGORIES:
        cursor.execute(
            "INSERT INTO categories (name, slug, description) VALUES (?, ?, ?)",
            (cat_name, slug, desc)
        )
        cat_map[cat_name] = cursor.lastrowid

    print("Inserting Products and Variants...")
    total_variants = 0
    for category_name, title, brand, base_price, rating, specs, variants in PRODUCTS:
        cat_id = cat_map[category_name]
        
        # Tags for FTS (combining brand and specs)
        tags = f"{brand} {category_name.split()[0]} {specs.replace('|', ' ')}"
        
        cursor.execute("""
            INSERT INTO products 
            (category_id, title, brand, category_tree, description, base_price, rating, tags)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (cat_id, title, brand, category_name, specs, base_price, rating, tags))
        
        product_id = cursor.lastrowid

        for color, size, modifier in variants:
            sku = f"SKU-{product_id}-{color[:3].upper()}-{size.replace(' ', '').upper()}-{random.randint(1000, 9999)}"
            price = base_price + modifier
            
            cursor.execute("""
                INSERT INTO product_variants
                (product_id, sku, color, size, style_or_spec, price, stock_quantity)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (product_id, sku, color, size, f"{color} - {size}", price, random.randint(15, 100)))
            total_variants += 1

    print("Populating FTS5 index...")
    cursor.execute("""
        INSERT INTO products_fts (product_id, title, brand, category_name, category_tree, description, tags)
        SELECT p.id, p.title, p.brand, c.name, p.category_tree, p.description, p.tags
        FROM products p
        JOIN categories c ON p.category_id = c.id
    """)

    conn.commit()
    conn.close()

    print(f"\\n✅ Seed Complete!")
    print(f"Products seeded: {len(PRODUCTS)}")
    print(f"Total SKU Variants: {total_variants}")
    print("FTS5 index successfully built for all technical specifications.")

if __name__ == "__main__":
    run()
