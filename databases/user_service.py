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
        razorpay_customer_id TEXT,
        razorpay_token_id TEXT,
        allowed_categories TEXT DEFAULT '[]',
        max_amount_per_tx REAL NOT NULL,
        is_active BOOLEAN DEFAULT 1,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS mandate_transactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        mandate_id INTEGER NOT NULL,
        user_id INTEGER NOT NULL,
        order_id INTEGER NOT NULL,
        amount REAL NOT NULL,
        razorpay_order_id TEXT,
        simulated_payment_id TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (mandate_id) REFERENCES user_payment_mandates (id),
        FOREIGN KEY (user_id) REFERENCES users (id),
        FOREIGN KEY (order_id) REFERENCES orders (id)
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
            INSERT INTO user_payment_mandates 
                (user_id, mandate_type, provider, mandate_token, razorpay_customer_id,
                 razorpay_token_id, max_amount_per_tx, allowed_categories)
            VALUES (?, 'UPI_AUTOPAY', 'Razorpay', 'mandate_rzp_mock_token_99182',
                    'cust_FlowCartAnkush01', 'token_FlowCartAutoPayPrimary', 4000.00,
                    '["Clothing", "Footwear", "Beauty and Personal Care"]')
        """, (u_id,))

    conn.commit()
    conn.close()


# User & Address Operations

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


# Guardrails & Spend Limit Verification

def verify_agent_spend_permission(user_id: int, transaction_amount: float) -> dict:
    """
    Financial Gate: Verifies if the proposed transaction is within the user's
    agent spend limit or if explicit step-up OTP / confirmation is required.
    """
    user = get_user_by_id(user_id)
    if not user:
        return {"allowed": False, "reason": "User not found", "spend_limit": 0.0}

    tx_limit = user["spend_limit_per_tx"]
    if transaction_amount > tx_limit:
        return {
            "allowed": False,
            "requires_explicit_confirmation": True,
            "spend_limit": tx_limit,
            "reason": f"Amount (₹{transaction_amount:.2f}) exceeds agent transaction ceiling of ₹{tx_limit:.2f}."
        }

    return {
        "allowed": True,
        "requires_explicit_confirmation": False,
        "spend_limit": tx_limit,
        "reason": f"Amount is within pre-authorized limit of ₹{tx_limit:.2f}.",
    }


# ==========================================
# Mandate-Based Auto-Pay (Phase 1)
# ==========================================

def get_active_mandate(user_id: int) -> dict | None:
    """
    Fetches the user's active UPI Autopay mandate including Razorpay token details
    and the list of approved spending categories.
    Returns None if no active mandate exists.
    """
    conn = get_user_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT * FROM user_payment_mandates
        WHERE user_id = ? AND is_active = 1
        ORDER BY created_at DESC
        LIMIT 1
    """, (user_id,))
    row = cursor.fetchone()
    conn.close()
    if not row:
        return None
    mandate = dict(row)
    # Deserialise the JSON category whitelist into a Python list
    try:
        mandate["allowed_categories"] = json.loads(mandate.get("allowed_categories") or "[]")
    except (json.JSONDecodeError, TypeError):
        mandate["allowed_categories"] = []
    return mandate


def verify_mandate_for_payment(user_id: int, cart: dict) -> dict:
    """
    Three-layer guardrail check before executing a mandate auto-debit.

    Guardrail 1 — Mandate exists and is active.
    Guardrail 2 — Cart grand_total is within mandate's per-transaction cap.
    Guardrail 3 — Every item's category is inside the user's approved category whitelist.

    Args:
        user_id: The user performing checkout.
        cart:    The cart dict returned by inventory_service.cart_get().

    Returns a dict:
        { "allowed": True,  "mandate": {...}, "reason": "..." }
        { "allowed": False, "reason": "...", "unauthorized_items": [...] }
    """
    # --- Guardrail 1: mandate existence ---
    mandate = get_active_mandate(user_id)
    if not mandate:
        return {
            "allowed": False,
            "reason": "No active UPI Autopay mandate found. Payment link will be generated instead.",
            "payment_method": "link",
        }

    grand_total = float(cart.get("grand_total", 0.0))
    max_per_tx  = float(mandate["max_amount_per_tx"])

    # --- Guardrail 2: per-transaction amount cap ---
    if grand_total > max_per_tx:
        return {
            "allowed": False,
            "reason": (
                f"Cart total ₹{grand_total:.2f} exceeds your mandate's per-transaction "
                f"limit of ₹{max_per_tx:.2f}. Payment link will be generated instead."
            ),
            "payment_method": "link",
            "mandate": mandate,
        }

    # --- Guardrail 3: category whitelist check ---
    allowed_cats = [c.lower().strip() for c in mandate["allowed_categories"]]
    unauthorized_items = []
    for item in cart.get("items", []):
        item_cat = (item.get("category") or "").lower().strip()
        if allowed_cats and item_cat not in allowed_cats:
            unauthorized_items.append({
                "title":    item.get("title", "Unknown"),
                "category": item.get("category", "Unknown"),
            })

    if unauthorized_items:
        names = ", ".join(
            f"{i['title']} ({i['category']})" for i in unauthorized_items
        )
        allowed_display = ", ".join(mandate["allowed_categories"])
        return {
            "allowed": False,
            "reason": (
                f"These items are outside your auto-pay approved categories: {names}. "
                f"Your mandate only covers: {allowed_display}. "
                f"A payment link will be sent for manual approval."
            ),
            "payment_method": "link",
            "unauthorized_items": unauthorized_items,
            "mandate": mandate,
        }

    # --- All guardrails passed ---
    return {
        "allowed": True,
        "payment_method": "mandate_auto_debit",
        "mandate": mandate,
        "reason": (
            f"All guardrails passed. ₹{grand_total:.2f} is within mandate cap ₹{max_per_tx:.2f} "
            f"and all categories are approved."
        ),
    }


def execute_mandate_payment(
    user_id: int,
    order_id: int,
    amount: float,
    mandate_id: int,
    session_id: str,
    razorpay_order_id: str | None = None,
    real_payment_id: str | None = None,
) -> dict:
    """
    Records a successful mandate auto-debit in the database.

    Called AFTER the Razorpay recurring payment API call succeeds (Phase 2).
    If a real_payment_id is provided (from Razorpay), it is used; otherwise
    a simulation ID is generated for test/demo purposes.

    Steps:
        1. Generate or use the provided payment ID.
        2. Insert a row into mandate_transactions for daily-spend tracking.
        3. Update the order: payment_status='paid', order_status='processing'.
        4. Write a MANDATE_AUTO_DEBIT entry to the audit log.
    """
    payment_id = real_payment_id or f"mandate_auto_{uuid.uuid4().hex[:12]}"

    conn = get_user_db()
    cursor = conn.cursor()
    try:
        # 1. Record in mandate_transactions (daily cap tracking)
        cursor.execute("""
            INSERT INTO mandate_transactions
                (mandate_id, user_id, order_id, amount, razorpay_order_id, simulated_payment_id)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (mandate_id, user_id, order_id, amount, razorpay_order_id, payment_id))

        # 2. Mark the order as paid
        cursor.execute("""
            UPDATE orders
            SET razorpay_payment_id = ?,
                razorpay_order_id   = ?,
                payment_status      = 'paid',
                order_status        = 'processing',
                updated_at          = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (payment_id, razorpay_order_id, order_id))

        conn.commit()
    except Exception as exc:
        conn.rollback()
        conn.close()
        return {"success": False, "error": str(exc)}
    finally:
        conn.close()

    # 3. Audit log (outside the transaction — non-critical)
    log_agent_audit(
        session_id=session_id,
        action_type="MANDATE_AUTO_DEBIT",
        reasoning=f"Mandate auto-debit of ₹{amount:.2f} executed for order #{order_id}.",
        payload={
            "mandate_id":        mandate_id,
            "order_id":          order_id,
            "amount":            amount,
            "payment_id":        payment_id,
            "razorpay_order_id": razorpay_order_id,
        },
        user_id=user_id,
        is_gated=True,
        user_confirmed=True,
    )

    return {
        "success":    True,
        "payment_id": payment_id,
        "order_id":   order_id,
        "amount":     amount,
    }


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


# Audit Logging (The Bar Requirement)

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

    # Self-test: basic user + address
    user = get_user_by_id(1)
    addr = get_user_default_address(1)

    if user and addr:
        print(f"User: {user['name']} ({user['phone']})")
        print(f"Default Address: {addr['street_address']}, {addr['city']}")
    else:
        print("Test failed: User or address not found.")

    # Self-test: existing spend limit check
    limit_check = verify_agent_spend_permission(1, 2200.00)
    print("Spend Limit Verification (₹2,200):", limit_check)

    # Self-test: new mandate functions
    print("\n--- Mandate Tests ---")
    mandate = get_active_mandate(1)
    if mandate:
        print(f"Active mandate: {mandate['mandate_type']} | token: {mandate['mandate_token']}")
        print(f"Allowed categories: {mandate['allowed_categories']}")
    else:
        print("No active mandate found for user 1.")

    # Guardrail test 1: valid cart within limit + approved category
    mock_cart_ok = {
        "grand_total": 1799.00,
        "items": [{"title": "Nakpro Whey", "category": "Supplements"}]
    }
    result = verify_mandate_for_payment(1, mock_cart_ok)
    print(f"\nValid cart test:    allowed={result['allowed']} | {result['reason']}")

    # Guardrail test 2: cart with unauthorized category (Electronics)
    mock_cart_bad_cat = {
        "grand_total": 2500.00,
        "items": [
            {"title": "Nakpro Whey", "category": "Supplements"},
            {"title": "Sony Headphones", "category": "Electronics"},
        ]
    }
    result2 = verify_mandate_for_payment(1, mock_cart_bad_cat)
    print(f"Bad category test:  allowed={result2['allowed']} | {result2['reason'][:80]}...")

    # Guardrail test 3: cart over mandate amount cap
    mock_cart_over_limit = {
        "grand_total": 5000.00,
        "items": [{"title": "Premium Gear Bundle", "category": "Fitness"}]
    }
    result3 = verify_mandate_for_payment(1, mock_cart_over_limit)
    print(f"Over-limit test:    allowed={result3['allowed']} | {result3['reason'][:80]}...")