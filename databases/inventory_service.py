import sqlite3
import json
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent / "inventory.db"

def get_db_connection():
    """Returns a SQLite database connection with row factory enabled."""
    if not DB_PATH.exists():
        raise FileNotFoundError(f"Database not found at '{DB_PATH}'. Please run 'python scripts/seed_inventory.py' first.")
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn

def search_products(query="", category=None, max_price=None, min_price=None, color=None, size=None, limit=10):
    """
    Search and filter products for conversational bot inquiries.
    Supports full-text keyword search and filtering by category, price, color, and size.
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    params = []
    
    # Base query joining products, categories, and variant summary
    if query and query.strip():
        # Clean query for FTS5 syntax
        fts_query = " ".join([f'"{term.strip()}*"' for term in query.split() if term.strip()])
        sql = """
            SELECT DISTINCT 
                p.id, p.title, p.brand, c.name as category, p.description, 
                p.base_price, p.rating, p.tags
            FROM products_fts fts
            JOIN products p ON fts.product_id = p.id
            JOIN categories c ON p.category_id = c.id
            LEFT JOIN product_variants v ON p.id = v.product_id
            WHERE products_fts MATCH ?
        """
        params.append(fts_query)
    else:
        sql = """
            SELECT DISTINCT 
                p.id, p.title, p.brand, c.name as category, p.description, 
                p.base_price, p.rating, p.tags
            FROM products p
            JOIN categories c ON p.category_id = c.id
            LEFT JOIN product_variants v ON p.id = v.product_id
            WHERE 1=1
        """

    if category:
        sql += " AND (LOWER(c.name) LIKE ? OR LOWER(c.slug) LIKE ?)"
        params.extend([f"%{category.lower()}%", f"%{category.lower()}%"])

    if max_price is not None:
        sql += " AND (v.price <= ? OR p.base_price <= ?)"
        params.extend([float(max_price), float(max_price)])

    if min_price is not None:
        sql += " AND (v.price >= ? OR p.base_price >= ?)"
        params.extend([float(min_price), float(min_price)])

    if color:
        sql += " AND LOWER(v.color) LIKE ?"
        params.append(f"%{color.lower()}%")

    if size:
        sql += " AND LOWER(v.size) LIKE ?"
        params.append(f"%{size.lower()}%")

    sql += " ORDER BY p.rating DESC LIMIT ?"
    params.append(limit)

    cursor.execute(sql, params)
    rows = cursor.fetchall()

    results = []
    for r in rows:
        p_id = r["id"]
        # Fetch available variants summary for each matching product
        cursor.execute("""
            SELECT id, sku, color, size, price, stock_quantity 
            FROM product_variants 
            WHERE product_id = ?
        """, (p_id,))
        variants = [dict(v) for v in cursor.fetchall()]

        colors = sorted(list(set([v["color"] for v in variants if v["color"]])))
        sizes = sorted(list(set([v["size"] for v in variants if v["size"]])))

        results.append({
            "id": r["id"],
            "title": r["title"],
            "brand": r["brand"],
            "category": r["category"],
            "description": r["description"],
            "base_price": r["base_price"],
            "rating": r["rating"],
            "tags": r["tags"].split(", ") if r["tags"] else [],
            "available_colors": colors,
            "available_sizes": sizes,
            "variants_count": len(variants),
            "variants": variants[:6] # list first 6 variants
        })

    conn.close()
    return results

def get_product_details(product_id_or_sku):
    """Get full specifications and all variants of a product by ID or SKU."""
    conn = get_db_connection()
    cursor = conn.cursor()

    if isinstance(product_id_or_sku, str) and not product_id_or_sku.isdigit():
        # Lookup by SKU
        cursor.execute("SELECT product_id FROM product_variants WHERE sku = ?", (product_id_or_sku,))
        row = cursor.fetchone()
        if not row:
            conn.close()
            return None
        product_id = row["product_id"]
    else:
        product_id = int(product_id_or_sku)

    cursor.execute("""
        SELECT p.id, p.title, p.brand, c.name as category, p.description, p.base_price, p.rating, p.tags
        FROM products p
        JOIN categories c ON p.category_id = c.id
        WHERE p.id = ?
    """, (product_id,))
    p_row = cursor.fetchone()

    if not p_row:
        conn.close()
        return None

    cursor.execute("""
        SELECT id, sku, color, size, style_or_spec, price, stock_quantity, image_url
        FROM product_variants
        WHERE product_id = ?
    """, (product_id,))
    v_rows = cursor.fetchall()

    conn.close()

    return {
        "id": p_row["id"],
        "title": p_row["title"],
        "brand": p_row["brand"],
        "category": p_row["category"],
        "description": p_row["description"],
        "base_price": p_row["base_price"],
        "rating": p_row["rating"],
        "tags": p_row["tags"].split(", ") if p_row["tags"] else [],
        "variants": [dict(v) for v in v_rows]
    }

def check_stock(variant_id_or_sku):
    """Check stock level for a specific product variant."""
    conn = get_db_connection()
    cursor = conn.cursor()

    if isinstance(variant_id_or_sku, str) and not variant_id_or_sku.isdigit():
        cursor.execute("""
            SELECT v.id, v.sku, p.title, v.color, v.size, v.price, v.stock_quantity
            FROM product_variants v
            JOIN products p ON v.product_id = p.id
            WHERE v.sku = ?
        """, (variant_id_or_sku,))
    else:
        cursor.execute("""
            SELECT v.id, v.sku, p.title, v.color, v.size, v.price, v.stock_quantity
            FROM product_variants v
            JOIN products p ON v.product_id = p.id
            WHERE v.id = ?
        """, (int(variant_id_or_sku),))

    row = cursor.fetchone()
    conn.close()

    if not row:
        return {"error": "Variant not found"}

    return dict(row)

def cart_add(session_id, variant_id, quantity=1):
    """Add item variant to shopping cart for a session."""
    conn = get_db_connection()
    cursor = conn.cursor()

    # Check variant validity and stock
    cursor.execute("""
        SELECT v.id, v.product_id, v.sku, p.title, v.color, v.size, v.price, v.stock_quantity
        FROM product_variants v
        JOIN products p ON v.product_id = p.id
        WHERE v.id = ? OR v.sku = ?
    """, (variant_id, str(variant_id)))
    v_row = cursor.fetchone()

    if not v_row:
        conn.close()
        return {"success": False, "error": "Product variant not found"}

    if v_row["stock_quantity"] < quantity:
        conn.close()
        return {
            "success": False, 
            "error": f"Insufficient stock. Requested: {quantity}, Available: {v_row['stock_quantity']}"
        }

    real_variant_id = v_row["id"]
    product_id = v_row["product_id"]

    # Check if item already exists in cart for this session
    cursor.execute("""
        SELECT id, quantity FROM cart_items 
        WHERE session_id = ? AND variant_id = ?
    """, (session_id, real_variant_id))
    existing_item = cursor.fetchone()

    if existing_item:
        new_qty = existing_item["quantity"] + quantity
        cursor.execute("""
            UPDATE cart_items SET quantity = ? WHERE id = ?
        """, (new_qty, existing_item["id"]))
    else:
        cursor.execute("""
            INSERT INTO cart_items (session_id, product_id, variant_id, quantity)
            VALUES (?, ?, ?, ?)
        """, (session_id, product_id, real_variant_id, quantity))

    conn.commit()
    conn.close()

    return {
        "success": True,
        "message": f"Added {quantity}x '{v_row['title']}' ({v_row['color']} / {v_row['size']}) to cart.",
        "item": {
            "title": v_row["title"],
            "sku": v_row["sku"],
            "color": v_row["color"],
            "size": v_row["size"],
            "unit_price": v_row["price"],
            "quantity_added": quantity
        }
    }

def cart_get(session_id):
    """Retrieve full cart breakdown for a user session."""
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT 
            ci.id as cart_item_id, ci.product_id, ci.variant_id, ci.quantity,
            p.title, p.brand, c.name as category,
            v.sku, v.color, v.size, v.price, v.stock_quantity
        FROM cart_items ci
        JOIN products p ON ci.product_id = p.id
        JOIN categories c ON p.category_id = c.id
        JOIN product_variants v ON ci.variant_id = v.id
        WHERE ci.session_id = ?
        ORDER BY ci.added_at ASC
    """, (session_id,))

    rows = cursor.fetchall()
    conn.close()

    items = []
    subtotal = 0.0
    total_items_count = 0

    for r in rows:
        item_total = round(r["price"] * r["quantity"], 2)
        subtotal += item_total
        total_items_count += r["quantity"]
        items.append({
            "cart_item_id": r["cart_item_id"],
            "product_id": r["product_id"],
            "variant_id": r["variant_id"],
            "title": r["title"],
            "brand": r["brand"],
            "category": r["category"],
            "sku": r["sku"],
            "color": r["color"],
            "size": r["size"],
            "unit_price": r["price"],
            "quantity": r["quantity"],
            "item_total": item_total,
            "in_stock": r["stock_quantity"] >= r["quantity"]
        })

    subtotal = round(subtotal, 2)
    tax = round(subtotal * 0.08, 2) # estimated 8% tax
    grand_total = round(subtotal + tax, 2)

    return {
        "session_id": session_id,
        "items": items,
        "total_items_count": total_items_count,
        "subtotal": subtotal,
        "tax": tax,
        "grand_total": grand_total
    }

def cart_remove(session_id, cart_item_id):
    """Remove specific item from cart."""
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("DELETE FROM cart_items WHERE session_id = ? AND id = ?", (session_id, cart_item_id))
    affected = cursor.rowcount
    conn.commit()
    conn.close()

    return {"success": affected > 0}

def cart_clear(session_id):
    """Clear all cart items for a session."""
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("DELETE FROM cart_items WHERE session_id = ?", (session_id,))
    conn.commit()
    conn.close()

    return {"success": True}

def list_categories():
    """List all inventory categories and their product counts."""
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT c.id, c.name, c.slug, c.description, COUNT(p.id) as product_count
        FROM categories c
        LEFT JOIN products p ON c.id = p.category_id
        GROUP BY c.id
        ORDER BY c.name ASC
    """)
    rows = cursor.fetchall()
    conn.close()

    return [dict(r) for r in rows]

if __name__ == "__main__":
    # Self-test queries
    print("=== Categories ===")
    for cat in list_categories():
        print(f" - {cat['name']}: {cat['product_count']} items")

    print("\n=== Search Demo: 'running shoes' ===")
    search_res = search_products(query="running shoes", color="black")
    print(f"Found {len(search_res)} matching items:")
    for prod in search_res[:3]:
        print(f" -> {prod['title']} | ${prod['base_price']} | Rating: {prod['rating']} | Colors: {prod['available_colors']}")

    print("\n=== Add to Cart Demo ===")
    if search_res and search_res[0]["variants"]:
        v_id = search_res[0]["variants"][0]["id"]
        add_res = cart_add("test_session_1", v_id, 2)
        print("Add Result:", add_res)
        cart_info = cart_get("test_session_1")
        print("Cart Contents:", json.dumps(cart_info, indent=2))
