import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent / "inventory.db"
USD_TO_INR_RATE = 60.0  # Current baseline exchange rate

def normalize_inr_price(usd_price: float, fx_rate: float = USD_TO_INR_RATE) -> float:
    """
    Converts USD to INR and normalizes to standard Indian retail/e-commerce
    psychological price points (charm pricing ending in 49, 99, 499, 999).
    """
    raw_inr = usd_price * fx_rate

    if raw_inr <= 100:
        # Sub-100: Snap to ₹49, ₹79, ₹99
        targets = [49, 79, 89, 99]
        return float(min(targets, key=lambda x: abs(x - raw_inr)))
    elif raw_inr <= 500:
        # ₹100 - ₹500: ₹149, ₹199, ₹249, ₹299, ₹349, ₹399, ₹449, ₹499
        targets = [99, 149, 199, 249, 299, 349, 399, 449, 499]
        return float(min(targets, key=lambda x: abs(x - raw_inr)))
    elif raw_inr <= 2000:
        # ₹500 - ₹2,000: Round to nearest ₹50 ending in 49 or 99 (e.g., 599, 749, 999, 1499)
        nearest_50 = round(raw_inr / 50.0) * 50
        return float(max(499, nearest_50 - 1))
    elif raw_inr <= 10000:
        # ₹2,000 - ₹10,000: Snap to nearest ₹100 ending in 99 (e.g., 2499, 2999, 4999, 7999)
        nearest_100 = round(raw_inr / 100.0) * 100
        return float(nearest_100 - 1)
    else:
        # > ₹10,000: Snap to nearest ₹500 ending in 499 or 999 (e.g., 12999, 14499, 19999)
        nearest_500 = round(raw_inr / 500.0) * 500
        return float(nearest_500 - 1)

def migrate_database():
    if not DB_PATH.exists():
        raise FileNotFoundError(f"Database file not found at {DB_PATH}")

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    try:
        # 1. Update product base prices
        cursor.execute("SELECT id, base_price FROM products")
        products = cursor.fetchall()
        
        updated_products = [
            (normalize_inr_price(base_price), p_id)
            for p_id, base_price in products
        ]
        cursor.executemany(
            "UPDATE products SET base_price = ? WHERE id = ?",
            updated_products
        )

        # 2. Update product variant prices
        cursor.execute("SELECT id, price FROM product_variants")
        variants = cursor.fetchall()

        updated_variants = [
            (normalize_inr_price(price), v_id)
            for v_id, price in variants
        ]
        cursor.executemany(
            "UPDATE product_variants SET price = ? WHERE id = ?",
            updated_variants
        )

        conn.commit()
        print(f"Successfully migrated {len(products)} products and {len(variants)} variants to normalized INR.")

    except Exception as e:
        conn.rollback()
        print(f"Error during migration: {e}")
        raise
    finally:
        conn.close()

if __name__ == "__main__":
    migrate_database()