#!/usr/bin/env python3
"""
Fix the StoreCode mapping in Sales Rule.
Change StoreCode mapping from "AlternateStoreCode" to "StoreCode"
"""
import json
import sys
sys.path.insert(0, '.')
from app import db, SalesRule, app

with app.app_context():
    rule = db.session.get(SalesRule, 1)
    if not rule:
        print("ERROR: No Sales Rule found!")
        sys.exit(1)
    
    mappings = json.loads(rule.mappings)
    
    print("=" * 80)
    print("BEFORE FIX:")
    print("=" * 80)
    print(f"StoreCode mapping: {mappings.get('StoreCode', 'NOT FOUND')}")
    
    # FIX: Change StoreCode mapping to source from "StoreCode" column in CSV
    if 'StoreCode' in mappings:
        old_value = mappings['StoreCode']
        mappings['StoreCode'] = 'StoreCode'  # Map to StoreCode column in CSV
        
        rule.mappings = json.dumps(mappings)
        db.session.commit()
        
        print("\nAFTER FIX:")
        print("=" * 80)
        print(f"StoreCode mapping: {mappings.get('StoreCode')}")
        print("\n✓ Fixed! StoreCode will now read from CSV 'StoreCode' column")
    else:
        print("\n⚠ StoreCode mapping not found in rule!")
        print("Adding StoreCode mapping...")
        mappings['StoreCode'] = 'StoreCode'
        rule.mappings = json.dumps(mappings)
        db.session.commit()
        print("✓ Added StoreCode mapping!")
    
    print("\n" + "=" * 80)
    print("CURRENT MAPPINGS:")
    print("=" * 80)
    for final_col, raw_col in sorted(mappings.items()):
        marker = "FIX" if final_col == "StoreCode" else "   "
        print(f"[{marker}] {final_col:30s} <- {raw_col}")
