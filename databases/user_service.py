import sqlite3
import json
import uuid
from pathlib import Path
from datetime import datetime, timezone

USER_DB_PATH = Path(__file__).resolve().parent / "users.db"

def get_user_db():
    """Returns a connection to the user database with foreign keys enabled."""
    conn = sqlite3.connect(USER_DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn

def init_user_db():
    """Initializes schema and seed mock users for testing conversational flows."""
    conn = get_user_db()
    cursor = conn.cursor()

    cursor.executescript("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        email TEXT UNIQUE NOT NULL,
        phone TEXT UNIQUE NOT NULL,
        default_currency TEXT DEFAULT 'INR',
        spend_limit_per_tx REAL DEFAULT 5000.00,
        daily_spend_limit REAL DEFAULT 15000.00,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS user_addresses (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        label TEXT DEFAULT 'Home',
        recipient_name TEXT NOT NULL,
        phone TEXT NOT NULL,
        street_address TEXT NOT NULL,
        city TEXT NOT NULL,
        state TEXT NOT NULL,
        postal_code TEXT NOT NULL,
        is_default BOOLEAN DEFAULT 0,
        FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS user_payment_mandates (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        mandate_type TEXT NOT NULL,
        provider TEXT DEFAULT 'Razorpay',
        mandate_token TEXT UNIQUE NOT NULL,
        max_amount_per_tx REAL NOT NULL,
        is_active BOOLEAN DEFAULT 1,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS orders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        order_number TEXT UNIQUE NOT NULL,
        user_id INTEGER NOT NULL,
        session_id TEXT NOT NULL,
        shipping_address_id INTEGER NOT NULL,
        subtotal REAL NOT NULL,
        tax REAL NOT NULL,
        discount REAL DEFAULT 0.00,
        grand_total REAL NOT NULL,
        currency TEXT DEFAULT 'INR',
        order_status TEXT DEFAULT 'pending',
        razorpay_order_id TEXT,
        razorpay_payment_link_id TEXT,
        razorpay_payment_id TEXT,
        razorpay_signature TEXT,
        payment_status TEXT DEFAULT 'unpaid',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE,
        FOREIGN KEY (shipping_address_id) REFERENCES user_addresses (id)
    );

    CREATE TABLE IF NOT EXISTS order_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        order_id INTEGER NOT NULL,
        product_id INTEGER NOT NULL,
        variant_id INTEGER NOT NULL,
        sku TEXT NOT NULL,
        title TEXT NOT NULL,
        color TEXT,
        size TEXT,
        unit_price REAL NOT NULL,
        quantity INTEGER NOT NULL,
        total_price REAL NOT NULL,
        FOREIGN KEY (order_id) REFERENCES orders (id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS agent_audit_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        session_id TEXT NOT NULL,
        action_type TEXT NOT NULL,
        reasoning TEXT,
        payload_json TEXT,
        is_gated BOOLEAN DEFAULT 0,
        user_confirmed BOOLEAN DEFAULT 0,
        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE SET NULL
    );
    """)

    # Seed mock user if table is empty
    cursor.execute("SELECT COUNT(*) as count FROM users;")
    if cursor.fetchone()["count"] == 0:
        cursor.execute("""
            INSERT INTO users (name, email, phone, spend_limit_per_tx, daily_spend_limit)
            VALUES ('Ankush Kumar', 'ankush@example.com', '+919876543210', 4000.00, 12000.00)
        """)
        u_id = cursor.lastrowid

        cursor.execute("""
            INSERT INTO user_addresses (user_id, label, recipient_name, phone, street_address, city, state, postal_code, is_default)
            VALUES (?, 'Hostel / Campus', 'Ankush Kumar', '+919876543210', 'Thapar University Hostel J, Bhadson Road', 'Patiala', 'Punjab', '147004', 1)
        """, (u_id,))

        cursor.execute("""
            INSERT INTO user_payment_mandates (user_id, mandate_type, mandate_token, max_amount_per_tx)
            VALUES (?, 'UPI_RESERVE_PAY', 'mandate_rzp_mock_token_99182', 4000.00)
        """, (u_id,))

    conn.commit()
    conn.close()

# ==========================================
# User & Address Operations
# ==========================================

def get_user_by_id(user_id: int):
    """Retrieve user details and active spending limits."""
    conn = get_user_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

def get_user_default_address(user_id: int):
    """Retrieve primary delivery address for checkout."""
    conn = get_user_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT * FROM user_addresses 
        WHERE user_id = ? AND is_default = 1
        LIMIT 1
    """, (user_id,))
    row = cursor.fetchone()
    if not row:
        # Fallback to any registered address
        cursor.execute("SELECT * FROM user_addresses WHERE user_id = ? LIMIT 1", (user_id,))
        row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

# ==========================================
# Guardrails & Spend Limit Verification
# ==========================================

def verify_agent_spend_permission(user_id: int, transaction_amount: float) -> dict:
    """
    Financial Gate: Verifies if the proposed transaction is within the user's
    agent spend limit or if explicit step-up OTP / confirmation is required.
    """
    user = get_user_by_id(user_id)
    if not user:
        return {"allowed": False, "reason": "User not found"}

    tx_limit = user["spend_limit_per_tx"]
    if transaction_amount > tx_limit:
        return {
            "allowed": False,
            "requires_explicit_confirmation": True,
            "reason": f"Amount (₹{transaction_amount:.2f}) exceeds agent transaction ceiling of ₹{tx_limit:.2f}."
        }

    return {
        "allowed": True,
        "requires_explicit_confirmation": False,
        "reason": f"Amount is within pre-authorized limit of ₹{tx_limit:.2f}."
    }

# ==========================================
# Order Lifecycle (Connecting Cart to Order)
# ==========================================

def create_order_from_cart(user_id: int, session_id: str, cart_data: dict, shipping_address_id: int | None = None) -> dict:
    """
    Freezes cart items into a formal order record ready for Razorpay checkout link attachment.
    """
    if not cart_data or not cart_data.get("items"):
        return {"success": False, "error": "Cannot create order from an empty cart."}

    if not shipping_address_id:
        addr = get_user_default_address(user_id)
        if not addr:
            return {"success": False, "error": "No shipping address available."}
        shipping_address_id = addr["id"]

    order_number = f"ORD-{datetime.now(timezone.utc).strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"

    conn = get_user_db()
    cursor = conn.cursor()

    try:
        cursor.execute("""
            INSERT INTO orders (
                order_number, user_id, session_id, shipping_address_id,
                subtotal, tax, grand_total, order_status, payment_status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', 'unpaid')
        """, (
            order_number, user_id, session_id, shipping_address_id,
            cart_data["subtotal"], cart_data["tax"], cart_data["grand_total"]
        ))
        order_id = cursor.lastrowid

        for item in cart_data["items"]:
            cursor.execute("""
                INSERT INTO order_items (
                    order_id, product_id, variant_id, sku, title,
                    color, size, unit_price, quantity, total_price
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                order_id, item["product_id"], item["variant_id"], item["sku"],
                item["title"], item.get("color"), item.get("size"),
                item["unit_price"], item["quantity"], item["item_total"]
            ))

        conn.commit()
        conn.close()

        return {
            "success": True,
            "order_id": order_id,
            "order_number": order_number,
            "grand_total": cart_data["grand_total"],
            "shipping_address_id": shipping_address_id
        }
    except Exception as e:
        conn.rollback()
        conn.close()
        return {"success": False, "error": str(e)}

def link_razorpay_payment(order_id: int, payment_link_id: str, razorpay_order_id: str | None = None):
    """Binds generated Razorpay link metadata to the pending order."""
    conn = get_user_db()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE orders 
        SET razorpay_payment_link_id = ?, razorpay_order_id = ?, updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
    """, (payment_link_id, razorpay_order_id, order_id))
    conn.commit()
    conn.close()

def finalize_order_payment(order_id: int, payment_id: str, signature: str, status: str = "paid"):
    """Marks the order as paid upon webhook confirmation."""
    conn = get_user_db()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE orders 
        SET razorpay_payment_id = ?, razorpay_signature = ?, 
            payment_status = ?, order_status = 'processing', updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
    """, (payment_id, signature, status, order_id))
    conn.commit()
    conn.close()

# ==========================================
# Audit Logging (The Bar Requirement)
# ==========================================

def log_agent_audit(session_id: str, action_type: str, reasoning: str, payload: dict, user_id: int | None = None, is_gated: bool = False, user_confirmed: bool = False):
    """
    Writes an immutable entry to the audit log tracking agent intent,
    gating enforcement, and API outputs.
    """
    conn = get_user_db()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO agent_audit_logs (
            user_id, session_id, action_type, reasoning, payload_json, is_gated, user_confirmed
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        user_id, session_id, action_type, reasoning,
        json.dumps(payload), int(is_gated), int(user_confirmed)
    ))
    conn.commit()
    conn.close()

def get_session_audit_trail(session_id: str):
    """Fetches the timeline of actions for evaluator inspection."""
    conn = get_user_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT * FROM agent_audit_logs 
        WHERE session_id = ? 
        ORDER BY timestamp ASC
    """, (session_id,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

if __name__ == "__main__":
    init_user_db()
    print("✓ user.db initialized and seeded.")
    
    # Self-test
    user = get_user_by_id(1)
    addr = get_user_default_address(1)
    
    # Add a safety check to satisfy the linter
    if user and addr:
        print(f"User: {user['name']} ({user['phone']})")
        print(f"Default Address: {addr['street_address']}, {addr['city']}")
    else:
        print("Test failed: User or address not found.")
    
    limit_check = verify_agent_spend_permission(1, 2200.00)
    print("Spend Limit Verification (₹2,200):", limit_check)