#!/usr/bin/env python3
"""
Check what the actual mappings are and what's happening
"""
import json
import sys
sys.path.insert(0, 'd:\\Python Project\\MIS Took\\FinanceTool - Test - Working')

from app import db, SalesRule, Setting, app

with app.app_context():
    rule = db.session.get(SalesRule, 1)
    mappings = json.loads(rule.mappings)
    
    sales_cols = db.session.execute(db.select(Setting).filter_by(key='sales_output_columns')).scalar_one_or_none()
    final_columns = [col.strip() for col in sales_cols.value.split('\n') if col.strip()]
    
    print("=" * 80)
    print("SALES OUTPUT COLUMNS vs MAPPINGS")
    print("=" * 80)
    
    print(f"\nTotal Final Columns: {len(final_columns)}")
    print(f"Total Mappings: {len(mappings)}")
    
    print("\n🔍 CHECKING ALTERNATESTORECODE:")
    if 'AlternateStoreCode' in final_columns:
        print(f"  ✓ Found in final_columns")
        raw_col = mappings.get('AlternateStoreCode', 'AlternateStoreCode')
        print(f"    Mapping: AlternateStoreCode ← {raw_col}")
        print(f"    Will look for column: {raw_col.upper()}")
    else:
        print(f"  ✗ NOT in final_columns!")
    
    print("\n📋 FINAL COLUMNS (first 20):")
    for i, col in enumerate(final_columns[:20]):
        print(f"  {i+1:2d}. {col}")
    
    print("\n📋 MAPPINGS (showing AlternateStoreCode area):")
    for final_col in final_columns:
        if 'Store' in final_col or 'Alternative' in final_col or 'Alternate' in final_col:
            raw_col = mappings.get(final_col, final_col)
            marker = "✓" if final_col == "AlternateStoreCode" else " "
            print(f"  {marker} {final_col:30s} ← {raw_col}")
    
    print("\n❓ MAPPINGS WITH NO COLUMN IN FINAL_COLUMNS:")
    for raw_col, mapped_to in mappings.items():
        if mapped_to not in final_columns:
            print(f"  ! {mapped_to:30s} (mapped from {raw_col})")
