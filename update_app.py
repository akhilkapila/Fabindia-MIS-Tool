import re

file_path = r"d:\Python Project\MIS Took\FinanceTool - Test - Working\app.py"

with open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()

# Define the new function code
new_function = r'''@app.route('/process-combine-only', methods=['POST'])
@login_required
def process_combine_only():
    """
    Step A: Process Combine MIS Files (NEW SIMPLE LOGIC)
    - Multi-file support
    - Target specific sheet starting with "MIS Working"
    - Start from 3rd row (header=2)
    - Clean merge
    """
    try:
        combine_files = request.files.getlist('combine_mis')
        if not combine_files:
            return jsonify({"error": "Please select Combine MIS file(s)."}), 400

        combined_data_list = []
        
        for file in combine_files:
            filename = file.filename
            file_ext = os.path.splitext(filename)[1].lower()
            df = None
            
            try:
                # 1. Handle Excel Files (xlsx, xls, xlsb, xlsm)
                if file_ext in ['.xlsx', '.xls', '.xlsb', '.xlsm']:
                    # We need to find the sheet starting with "MIS Working"
                    file.seek(0)
                    target_sheet = None
                    engine = 'pyxlsb' if file_ext == '.xlsb' else None
                    
                    try:
                        xls = pd.ExcelFile(file, engine=engine)
                        sheet_names = xls.sheet_names
                        
                        # Find matching sheet
                        for sheet in sheet_names:
                            if sheet.strip().lower().startswith('mis working'):
                                target_sheet = sheet
                                break
                        
                        if target_sheet:
                            # Load data from 3rd row (header=2)
                            df = pd.read_excel(xls, sheet_name=target_sheet, header=2, dtype=str)
                            print(f"File '{filename}': Found sheet '{target_sheet}'")
                        else:
                            print(f"File '{filename}': No sheet starting with 'MIS Working' found. Skipping.")
                            continue 
                            
                    except Exception as e:
                        print(f"Error inspecting Excel file {filename}: {e}")
                        continue

                # 2. Handle CSV Files
                elif file_ext == '.csv':
                    file.seek(0)
                    try:
                        df = pd.read_csv(file, header=2, dtype=str, encoding_errors='replace')
                    except Exception:
                        file.seek(0)
                        df = pd.read_csv(file, header=2, dtype=str, encoding='latin1')

                else:
                    print(f"Skipping unsupported file: {filename}")
                    continue

                # 3. Process the DataFrame if loaded
                if df is not None and not df.empty:
                    # Clean columns: Strip whitespace
                    df.columns = df.columns.astype(str).str.strip()
                    # Clean rows: Drop empty rows
                    df.dropna(how='all', inplace=True)
                    
                    if not df.empty:
                        combined_data_list.append(df)
                        print(f"File '{filename}': Added {len(df)} rows.")

            except Exception as e:
                print(f"Error processing file {filename}: {e}")
                return jsonify({"error": f"Failed to process {filename}: {str(e)}"}), 400

        # --- MERGE ---
        if not combined_data_list:
            return jsonify({"error": "No matching data found. Ensure files have a sheet starting with 'MIS Working'."}), 400

        # Concatenate all
        master_combine_df = pd.concat(combined_data_list, ignore_index=True)
        # Final Clean
        master_combine_df.dropna(how='all', inplace=True)
        
        # --- EXPORT ---
        processed_filename = f"{uuid.uuid4()}_processed_combine.xlsx"
        processed_filepath = os.path.join(UPLOAD_FOLDER, processed_filename)

        # Save using the existing logic or simple excel save
        success = save_with_formatting(master_combine_df, processed_filepath, sheet_name='Combined_MIS')
        if not success:
             master_combine_df.to_excel(processed_filepath, index=False)

        session['processed_combine_filepath'] = processed_filepath

        with open(processed_filepath, 'rb') as fbuf:
            data_bytes = fbuf.read()

        return send_file(
            io.BytesIO(data_bytes),
            as_attachment=True,
            download_name="Processed_Combine_MIS.xlsx",
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )

    except Exception as e:
        print(f"Error in process_combine_only: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500
'''

# Use regex to find the old function and replace it
# Pattern: @app.route('/process-combine-only' ... down to the end of the function
# We know the specific start string and we can approximate end or use indentation matching
# But simpler: we know exact lines from previous step: 1498 to 1718

lines = content.splitlines()
# Verify lines
if "@app.route('/process-combine-only', methods=['POST'])" in lines[1497]: # 0-indexed 1497 is line 1498
    print("Found start at 1498")
    # Slice out the old function
    # Index 1497 is 1498. 
    # We want to replace up to line 1718.
    # line 1718 is index 1717.
    
    # Check if end matches roughly
    # line 1718 content was: return jsonify({"error": str(e)}), 500
    if "return jsonify" in lines[1717]:
        print("Found end at 1718")
        
        before = lines[:1497]
        after = lines[1718:] # 1718 is the line AFTER the function block? No, 1718 is the LAST line of function.
        # So slice starts at 1718+1 = 1719?
        # Let's check line 1718.
        # If line 1718 is the last line of function, we want to KEEP line 1719 onwards.
        # So lines[1718] is line 1719 (0-indexed 1718 = 1719). 
        # Wait, if line 1498 is index 1497.
        # then line 1718 is index 1717.
        # So we want lines[:1497] + new + lines[1718:] (which is starting from index 1718, i.e., line 1719)
        
        new_content = "\n".join(before) + "\n" + new_function + "\n" + "\n".join(lines[1718:])
        
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(new_content)
        print("Successfully updated app.py")
    else:
        print("End line mismatch")
        # Fallback: search for Start and End string
        # ...
else:
    print("Start line mismatch")
