#!/usr/bin/env python3
import sqlite3
import json

conn = sqlite3.connect('app.db')
c = conn.cursor()

print("="*60)
print("CHECKING RULES CONFIGURATION")
print("="*60)

# Check Sales Rule
print("\n📊 SALES RULE:")
c.execute("SELECT id, sheet_name, start_row, mappings FROM sales_rule WHERE id=1")
row = c.fetchone()
if row:
    print(f"  ID: {row[0]}")
    print(f"  Sheet Name: {row[1]}")
    print(f"  Start Row: {row[2]}")
    print(f"  Mappings: {row[3][:100]}..." if len(row[3]) > 100 else f"  Mappings: {row[3]}")
    try:
        mappings = json.loads(row[3])
        print(f"  Mapped Columns: {list(mappings.keys())}")
    except:
        print(f"  ERROR parsing mappings!")
else:
    print("  ❌ NOT FOUND")

# Check Advances Rule
print("\n📈 ADVANCES RULE:")
c.execute("SELECT id, sheet_name, start_row, mappings FROM advance_rule WHERE id=1")
row = c.fetchone()
if row:
    print(f"  ID: {row[0]}")
    print(f"  Sheet Name: {row[1]}")
    print(f"  Start Row: {row[2]}")
    print(f"  Mappings: {row[3][:100]}..." if len(row[3]) > 100 else f"  Mappings: {row[3]}")
    try:
        mappings = json.loads(row[3])
        print(f"  Mapped Columns: {list(mappings.keys())}")
    except:
        print(f"  ERROR parsing mappings!")
else:
    print("  ❌ NOT FOUND")

# Check Output Columns
print("\n🎯 OUTPUT COLUMNS:")
c.execute("SELECT key, value FROM setting WHERE key LIKE '%output%'")
rows = c.fetchall()
for key, value in rows:
    cols = value.split(',')
    print(f"  {key}: {len(cols)} columns")
    print(f"    {cols[:5]}{'...' if len(cols) > 5 else ''}")

conn.close()
print("\n" + "="*60)
