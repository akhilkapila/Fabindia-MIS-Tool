import pandas as pd
import os

OUT_DIR = os.path.join(os.path.dirname(__file__), '..', 'temp_uploads')
combine_file = os.path.join(OUT_DIR, 'returned_combine_processed.xlsx')
final_file = os.path.join(OUT_DIR, 'returned_final_processed.xlsx')

print('Preview script running...')

if os.path.exists(combine_file):
    try:
        df = pd.read_excel(combine_file, engine='openpyxl', dtype=str)
        print('\n=== returned_combine_processed.xlsx (first 10 rows) ===')
        print(df.head(10).to_csv(index=False))
    except Exception as e:
        print(f'Error reading combine file: {e}')
else:
    print('returned_combine_processed.xlsx not found')

if os.path.exists(final_file):
    try:
        # Try to read the target sheet by name first
        try:
            df_final = pd.read_excel(final_file, sheet_name='Reconciliation by Date by Store', engine='openpyxl', dtype=str)
        except Exception:
            # Fallback: show first sheet
            xls = pd.ExcelFile(final_file, engine='openpyxl')
            sheet_to_use = 'Reconciliation by Date by Store' if 'Reconciliation by Date by Store' in xls.sheet_names else xls.sheet_names[0]
            df_final = pd.read_excel(final_file, sheet_name=sheet_to_use, engine='openpyxl', dtype=str)
        print('\n=== returned_final_processed.xlsx - Reconciliation by Date by Store (first 10 rows) ===')
        print(df_final.head(10).to_csv(index=False))
    except Exception as e:
        print(f'Error reading final file: {e}')
else:
    print('returned_final_processed.xlsx not found')
