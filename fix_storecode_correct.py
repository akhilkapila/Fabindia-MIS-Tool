#!/usr/bin/env python3
"""
Revert StoreCode mapping to read from AlternateStoreCode as intended.
The flow is:
1. AlternateStoreCode <- AlternateStoreCode (CSV column)
2. StoreCode <- AlternateStoreCode (copy same data)
3. Both get BP prefix removed
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
    print("FIXING STORECODE MAPPING")
    print("=" * 80)
    
    print("\nBEFORE:")
    print(f"  StoreCode mapping: {mappings.get('StoreCode', 'NOT FOUND')}")
    
    # REVERT: Change StoreCode mapping back to AlternateStoreCode
    # So both AlternateStoreCode and StoreCode read from same source
    mappings['StoreCode'] = 'AlternateStoreCode'
    
    rule.mappings = json.dumps(mappings)
    db.session.commit()
    
    print("\nAFTER:")
    print(f"  StoreCode mapping: {mappings.get('StoreCode')}")
    
    print("\nFLOW:")
    print("  1. CSV 'AlternateStoreCode' column -> rename to 'AlternateStoreCode' output")
    print("  2. CSV 'AlternateStoreCode' column -> rename to 'StoreCode' output (copy)")
    print("  3. Remove 'BP' prefix from BOTH columns (bp_remove_cols='StoreCode,AlternateStoreCode')")
    print("  4. Result: Both columns have same data without BP prefix")
    
    print("\n" + "=" * 80)
    print("FINAL MAPPINGS:")
    print("=" * 80)
    
    key_cols = ['AlternateStoreCode', 'StoreCode', 'StoreName']
    for final_col in sorted(mappings.keys()):
        raw_col = mappings[final_col]
        if final_col in key_cols:
            marker = "[KEY]"
        else:
            marker = "     "
        print(f"{marker} {final_col:30s} <- {raw_col}")
