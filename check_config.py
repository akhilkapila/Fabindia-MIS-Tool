import json
import sys
sys.path.insert(0, '.')
from app import db, SalesRule, Setting, app

with app.app_context():
    rule = db.session.get(SalesRule, 1)
    mappings = json.loads(rule.mappings)
    
    sales_cols = db.session.execute(db.select(Setting).filter_by(key='sales_output_columns')).scalar_one_or_none()
    final_columns = [col.strip() for col in sales_cols.value.split('\n') if col.strip()]
    
    print('Total Final Columns:', len(final_columns))
    print('Total Mappings:', len(mappings))
    
    print('\nFirst 10 final columns:')
    for col in final_columns[:10]:
        raw = mappings.get(col, col)
        print(f'  {col} <- {raw}')
    
    print('\n--- AlternateStoreCode check ---')
    print(f'In final_columns: {"AlternateStoreCode" in final_columns}')
    if 'AlternateStoreCode' in mappings:
        print(f'In mappings: YES - maps to {mappings["AlternateStoreCode"]}')
    else:
        print(f'In mappings: NO')
    
    print('\n--- All mappings ---')
    for final_col, raw_col in mappings.items():
        print(f'{final_col:30s} <- {raw_col}')
