import sqlite3
from pathlib import Path

# Path to the database created by user_service.py
USER_DB_PATH = Path(__file__).resolve().parent / "users.db"

def seed_sample_users():
    """Populate users.db with 5 diverse mock users for testing."""
    if not USER_DB_PATH.exists():
        print(f"Error: {USER_DB_PATH} not found. Run 'user_service.py' first to create the database.")
        return

    conn = sqlite3.connect(USER_DB_PATH)
    cursor = conn.cursor()

    # Define our 5 mock users with varying spend limits
    sample_users = [
        {
            "user": ("Ankita Panda", "ankita@example.com", "+919876543211", 10000.00, 25000.00),
            "address": ("Home", "Ankita Panda", "+919876543211", "Flat 402, Sunshine Apartments, Indiranagar", "Bangalore", "Karnataka", "560038"),
            "mandate": ("UPI_RESERVE_PAY", "mandate_rzp_mock_ankita_10k", 10000.00)
        },
        {
            "user": ("Rohan Mehta", "rohan@example.com", "+919876543212", 2000.00, 5000.00),
            "address": ("Work", "Rohan Mehta", "+919876543212", "TechPark Tower B, Andheri East", "Mumbai", "Maharashtra", "400069"),
            "mandate": ("UPI_AUTOPAY", "mandate_rzp_mock_rohan_2k", 2000.00)
        },
        {
            "user": ("Priya Patel", "priya@example.com", "+919876543213", 1500.00, 3000.00),
            "address": ("Home", "Priya Patel", "+919876543213", "House 14, Hauz Khas Village", "New Delhi", "Delhi", "110016"),
            "mandate": ("CARD_TOKEN", "tok_rzp_mock_priya_1500", 1500.00)
        },
        {
            "user": ("Arjun Desai", "arjun@example.com", "+919876543214", 25000.00, 50000.00),
            "address": ("Home", "Arjun Desai", "+919876543214", "Villa 9, Satellite Road", "Ahmedabad", "Gujarat", "380015"),
            "mandate": ("UPI_RESERVE_PAY", "mandate_rzp_mock_arjun_25k", 25000.00)
        },
        {
            "user": ("Neha Singh", "neha@example.com", "+919876543215", 5000.00, 10000.00),
            "address": ("Campus", "Neha Singh", "+919876543215", "Room 21, Symbiosis Hostel, Viman Nagar", "Pune", "Maharashtra", "411014"),
            "mandate": ("UPI_RESERVE_PAY", "mandate_rzp_mock_neha_5k", 5000.00)
        }
    ]

    users_added = 0

    for data in sample_users:
        try:
            # 1. Insert User
            cursor.execute("""
                INSERT INTO users (name, email, phone, spend_limit_per_tx, daily_spend_limit)
                VALUES (?, ?, ?, ?, ?)
            """, data["user"])
            user_id = cursor.lastrowid

            # 2. Insert Address
            cursor.execute("""
                INSERT INTO user_addresses (user_id, label, recipient_name, phone, street_address, city, state, postal_code, is_default)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1)
            """, (user_id,) + data["address"])

            # 3. Insert Payment Mandate
            cursor.execute("""
                INSERT INTO user_payment_mandates (user_id, mandate_type, mandate_token, max_amount_per_tx)
                VALUES (?, ?, ?, ?)
            """, (user_id,) + data["mandate"])
            
            users_added += 1

        except sqlite3.IntegrityError as e:
            # Catch duplicates (e.g., if you run the script twice and emails/phones conflict)
            print(f"Skipped {data['user'][0]} - likely already exists in the database. ({e})")

    conn.commit()
    conn.close()

    print(f"✓ Successfully added {users_added} sample users to the database.")

if __name__ == "__main__":
    print("Seeding users database...")
    seed_sample_users()
