import sqlite3
import uuid
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

USER_DB_PATH = Path(__file__).resolve().parent / "users.db"
INVENTORY_DB_PATH = Path(__file__).resolve().parent / "inventory.db"

def get_real_products(limit=10):
    """Fetches real products and their variants directly from inventory.db."""
    if not INVENTORY_DB_PATH.exists():
        print(f"Error: {INVENTORY_DB_PATH} not found.")
        return []

    conn = sqlite3.connect(INVENTORY_DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # Grab a random selection of real variants
    cursor.execute("""
        SELECT p.id as product_id, p.title, v.id as variant_id, 
               v.sku, v.color, v.size, v.price
        FROM products p
        JOIN product_variants v ON p.id = v.product_id
        ORDER BY RANDOM()
        LIMIT ?
    """, (limit,))
    
    products = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return products

def generate_past_date(days_ago_min, days_ago_max):
    """Generates a random timezone-aware past datetime."""
    days_ago = random.randint(days_ago_min, days_ago_max)
    past_date = datetime.now(timezone.utc) - timedelta(days=days_ago)
    return past_date

def seed_order_history():
    if not USER_DB_PATH.exists():
        print(f"Error: {USER_DB_PATH} not found. Run 'user_service.py' first.")
        return

    # 1. Get real products from inventory.db
    real_products = get_real_products(10)
    if not real_products:
        return

    # 2. Connect to users.db
    conn = sqlite3.connect(USER_DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Fetch all users and their default addresses
    cursor.execute("""
        SELECT u.id as user_id, u.name, a.id as address_id 
        FROM users u
        JOIN user_addresses a ON u.id = a.user_id AND a.is_default = 1
        ORDER BY u.id ASC
    """)
    users = cursor.fetchall()

    if not users:
        print("No users found. Please run seed_users.py first.")
        conn.close()
        return

    # Leave the last 2 users as "New Users" without order history
    active_users = users[:-2] 
    new_users = users[-2:]

    orders_created = 0

    for user in active_users:
        # Give each active user 1 to 3 past orders
        num_orders = random.randint(1, 3)
        
        for _ in range(num_orders):
            # Pick 1-2 real items for this order
            items_to_buy = random.sample(real_products, random.randint(1, 2))
            
            subtotal = sum(item["price"] for item in items_to_buy)
            tax = round(subtotal * 0.08, 2)
            grand_total = round(subtotal + tax, 2)
            
            past_date = generate_past_date(5, 120)
            date_str = past_date.strftime('%Y-%m-%d %H:%M:%S')
            
            order_num = f"ORD-{past_date.strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"
            session_id = f"past_sess_{uuid.uuid4().hex[:8]}"

            # 1. Insert Order
            cursor.execute("""
                INSERT INTO orders (
                    order_number, user_id, session_id, shipping_address_id,
                    subtotal, tax, grand_total, order_status, payment_status,
                    razorpay_order_id, razorpay_payment_id, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                order_num, user["user_id"], session_id, user["address_id"],
                subtotal, tax, grand_total, 'delivered', 'paid',
                f"order_rzp_{uuid.uuid4().hex[:10]}", f"pay_{uuid.uuid4().hex[:14]}",
                date_str, date_str
            ))
            
            order_id = cursor.lastrowid

            # 2. Insert Order Items
            for item in items_to_buy:
                cursor.execute("""
                    INSERT INTO order_items (
                        order_id, product_id, variant_id, sku, title,
                        color, size, unit_price, quantity, total_price
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    order_id, item["product_id"], item["variant_id"], item["sku"],
                    item["title"], item.get("color", ""), item.get("size", ""),
                    item["price"], 1, item["price"]
                ))
            
            orders_created += 1

    conn.commit()
    conn.close()

    print(f"✓ Created {orders_created} past orders using REAL inventory data.")
    print(f"✓ Left {len(new_users)} users completely new (No history): {', '.join([u['name'] for u in new_users])}")

if __name__ == "__main__":
    print("Generating perfect-match order history...")
    seed_order_history()