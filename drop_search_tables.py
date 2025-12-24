import sqlite3
import os

db_path = 'app.db'

if not os.path.exists(db_path):
    print(f"Database file {db_path} not found.")
    exit(1)

conn = sqlite3.connect(db_path)
cursor = conn.cursor()

try:
    print("Dropping search_payment_mode_rule table...")
    cursor.execute("DROP TABLE IF EXISTS search_payment_mode_rule")
    
    print("Dropping search_prompt table...")
    cursor.execute("DROP TABLE IF EXISTS search_prompt")
    
    conn.commit()
    print("Tables dropped successfully.")

except Exception as e:
    print(f"Error: {e}")
finally:
    conn.close()
