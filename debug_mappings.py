#!/usr/bin/env python3
"""
Debug script to check:
1. What mappings are configured in Admin Portal
2. What columns are in the sales CSV
3. Why AlternateStoreCode isn't being populated
"""
import sqlite3
import json
import os
import sys

# Add the project folder to path
sys.path.insert(0, 'd:\\Python Project\\MIS Took\\FinanceTool - Test - Working')

from app import db, SalesRule, app

print("=" * 80)
print("CHECKING SALES RULE MAPPINGS")
print("=" * 80)

with app.app_context():
    rule = db.session.get(SalesRule, 1)
    if rule:
        print(f"\n📋 SALES RULE (ID=1):")
        print(f"   Sheet Name: {rule.sheet_name}")
        print(f"   Start Row: {rule.start_row}")
        print(f"   Copy Source: {rule.copy_col_source}")
        print(f"   Copy Dest: {rule.copy_col_dest}")
        print(f"   BP Remove Cols: {rule.bp_remove_cols}")
        
        mappings = json.loads(rule.mappings)
        print(f"\n🔗 MAPPINGS ({len(mappings)} total):")
        for final_col, raw_col in mappings.items():
            marker = "✓" if final_col == "AlternateStoreCode" else " "
            print(f"   {marker} {final_col:25s} ← {raw_col}")
    else:
        print("❌ No sales rule found!")

print("\n" + "=" * 80)
print("CHECKING LATEST PROCESS LOG")
print("=" * 80)

log_folder = 'd:\\Python Project\\MIS Took\\FinanceTool - Test - Working\\temp_uploads\\logs'
log_files = [f for f in os.listdir(log_folder) if f.startswith('process_sales') and f.endswith('.log')]
if log_files:
    latest_log = sorted(log_files, key=lambda f: os.path.getmtime(os.path.join(log_folder, f)), reverse=True)[0]
    log_path = os.path.join(log_folder, latest_log)
    print(f"\n📄 Latest Log: {latest_log}")
    
    with open(log_path, 'r') as f:
        lines = f.readlines()
        
    # Find key lines
    print("\n🔍 KEY PROCESSING STEPS:")
    for i, line in enumerate(lines):
        if 'Loaded data' in line:
            print(f"\n   {line.strip()}")
        elif 'Columns converted to uppercase' in line:
            print(f"   {line.strip()}")
        elif 'Rename map created' in line:
            print(f"   {line.strip()}")
        elif 'After rename' in line:
            print(f"   {line.strip()}")
        elif 'Copied' in line or 'Source column' in line:
            print(f"   {line.strip()}")
        elif 'AlternateStoreCode' in line:
            print(f"   {line.strip()}")
else:
    print("❌ No process logs found!")

print("\n" + "=" * 80)
