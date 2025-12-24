import sqlite3
import os

db_path = 'app.db'

if not os.path.exists(db_path):
    print(f"Database file {db_path} not found.")
    exit(1)

conn = sqlite3.connect(db_path)
cursor = conn.cursor()

try:
    # Check if column exists
    cursor.execute("PRAGMA table_info(search_payment_mode_rule)")
    columns = [info[1] for info in cursor.fetchall()]
    
    if 'sheet_name' not in columns:
        print("Adding sheet_name column...")
        cursor.execute("ALTER TABLE search_payment_mode_rule ADD COLUMN sheet_name VARCHAR(100)")
        conn.commit()
        print("Column added successfully.")
    else:
        print("Column sheet_name already exists.")

except Exception as e:
    print(f"Error: {e}")
finally:
    conn.close()
