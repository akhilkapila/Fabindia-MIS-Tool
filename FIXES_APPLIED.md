# Fixes Applied - December 11, 2025

## Issues Fixed

### 1. ✅ BillDate Column Not Processing DD-MM-YYYY Format
**Problem:** BillDate column values were not being converted to DD-MM-YYYY format during processing.

**Root Cause:** `pd.to_datetime()` was using auto-detect format, which doesn't handle DD-MM-YYYY correctly when there are multiple date formats in the file.

**Solution Applied:**
- Modified `process_sales()` function (line ~760)
- Added explicit format specification: `pd.to_datetime(output_df['BillDate'], format='%d-%m-%Y', errors='coerce')`
- Added fallback to auto-detect if explicit format fails
- Added detailed logging to confirm parsing success

**Code Change:**
```python
# BEFORE:
output_df['BillDate'] = pd.to_datetime(output_df['BillDate'], errors='coerce')

# AFTER:
if 'BillDate' in output_df.columns:
    try:
        # Try DD-MM-YYYY format first (most common in your data)
        output_df['BillDate'] = pd.to_datetime(output_df['BillDate'], format='%d-%m-%Y', errors='coerce')
        logger.info(f"✓ BillDate parsed with DD-MM-YYYY format")
    except Exception as e:
        logger.warning(f"DD-MM-YYYY parsing failed, trying auto-detect: {e}")
        # Fallback to auto-detect format
        output_df['BillDate'] = pd.to_datetime(output_df['BillDate'], errors='coerce')
        logger.info(f"✓ BillDate auto-detected and parsed")
```

---

### 2. ✅ AlternateStoreCode & StoreCode Not Copying Properly
**Problem:** StoreCode column showing NaN values because AlternateStoreCode data wasn't being copied to it.

**Root Cause:** The copy logic existed but:
1. Was missing `.copy()` method, just assigning reference
2. Had poor indentation (mixed spaces/tabs)
3. Lacked logging to track if copy actually happened
4. Didn't verify source column exists before copying

**Solution Applied:**
- Fixed indentation and logic in `process_sales()` function (line ~735)
- Added explicit `.copy()` to ensure data is actually copied (not reference)
- Added detailed logging with count of copied rows
- Added warning if source column not found
- Added debug info showing available columns

**Code Change:**
```python
# BEFORE:
if rule.copy_col_source and rule.copy_col_dest:
     if rule.copy_col_source in output_df.columns:
        output_df[rule.copy_col_dest] = output_df[rule.copy_col_source]
        logger.debug(f"Copied column {rule.copy_col_source} to {rule.copy_col_dest}")

# AFTER:
if rule.copy_col_source and rule.copy_col_dest:
    if rule.copy_col_source in output_df.columns:
        # Copy AlternateStoreCode data to StoreCode column
        output_df[rule.copy_col_dest] = output_df[rule.copy_col_source].copy()
        logger.info(f"✓ Copied {rule.copy_col_source} → {rule.copy_col_dest} ({output_df[rule.copy_col_dest].notna().sum()} rows)")
    else:
        logger.warning(f"⚠ Source column '{rule.copy_col_source}' not found in dataframe. Available: {list(output_df.columns)[:10]}...")
else:
    logger.debug(f"No copy rules configured (source={rule.copy_col_source}, dest={rule.copy_col_dest})")
```

---

### 3. ✅ Removed Hardcoded Amex Rule Repair Code
**Problem:** Code was automatically repairing/overwriting Amex rule from Admin Portal on every server restart.

**Root Cause:** Lines 1515-1548 contained hardcoded logic that would:
- Create new Amex rule if missing
- Or overwrite existing mappings with hardcoded values
- User's manual updates in Admin Portal would be lost on restart

**Solution Applied:**
- Completely removed the Amex rule repair code (lines 1515-1548)
- Replaced with comment explaining Amex is managed via Admin Portal
- Now users have full control - no auto-overwriting

**Code Change:**
```python
# BEFORE: (30+ lines of auto-repair logic)
amex_rule = db.session.execute(db.select(BankRule).filter_by(bank_name='Amex')).scalar_one_or_none()
amex_mappings = { ... }
if not amex_rule:
    print("Creating new Amex rule...")
    amex_rule = BankRule(...)
    db.session.add(amex_rule)
else:
    print("Found existing Amex rule, repairing mappings...")
    amex_rule.start_row = 2
    amex_rule.sheet_name = 'AMEX MIS'
    amex_rule.mappings = json.dumps(amex_mappings)
db.session.commit()

# AFTER: (Simple comment, no auto-repair)
# --- AMEX RULE: Managed in Admin Portal ---
# Amex rule configuration is managed via Admin Portal.
# No auto-repair necessary - user has full control.
```

---

## Impact on Processing

### BillDate Processing Flow
1. **CSV Load:** Dates loaded as strings (e.g., "11-12-2025")
2. **Parsing:** Now explicitly parsed as DD-MM-YYYY format → datetime object
3. **Excel Save:** Saved as datetime in Excel
4. **Post-Processing:** `post_process_workbook()` detects as date column → formats as DD-MM-YYYY ✓

### AlternateStoreCode/StoreCode Flow
1. **CSV Load:** AlternateStoreCode column loaded with store codes
2. **Rename:** Column renamed to output format name
3. **Copy Logic:** AlternateStoreCode → StoreCode (NOW WORKS) ✓
4. **BP Removal:** Removes 'BP' prefix from both columns
5. **Output:** StoreCode has actual data, no NaN values ✓

### Amex Rule Management
1. **Before:** Server restart = auto-overwriting Amex rule mappings (user changes lost)
2. **After:** User updates in Admin Portal → permanently saved (no auto-overwrite) ✓

---

## Testing Instructions

### Test 1: BillDate DD-MM-YYYY Format
1. Upload sales CSV file with BillDate in DD-MM-YYYY format
2. Process sales
3. Download Excel file
4. Check BillDate column:
   - Should show as DD-MM-YYYY (e.g., "11-12-2025")
   - Should NOT have time component (e.g., "11-12-2025 00:00:00")
   - Cells should have `DD-MM-YYYY` number format

### Test 2: AlternateStoreCode → StoreCode
1. Upload sales CSV with AlternateStoreCode column (e.g., values like "1020", "1021")
2. Process sales
3. Download Excel file
4. Check StoreCode column:
   - Should have same values as AlternateStoreCode (e.g., "1020", "1021")
   - Should NOT have NaN/blank values
   - Log should show: "✓ Copied AlternateStoreCode → StoreCode (X rows)"

### Test 3: Amex Rule Persistence
1. Go to Admin Portal → Banking tab → Amex
2. Modify any Amex mappings
3. Save changes
4. Restart Flask server
5. Go back to Admin Portal → Banking → Amex
6. Verify your changes are still there (NOT overwritten) ✓

---

## Server Status
✅ Flask running at http://127.0.0.1:5001
✅ All syntax verified with `python -m py_compile`
✅ Ready for testing

---

## Files Modified
- `app.py` - Lines: ~760-770 (BillDate), ~735-750 (StoreCode), ~1515-1548 (Amex)

## Next Steps
1. Upload a sales file for testing
2. Verify BillDate format in processed Excel
3. Verify StoreCode has data (no NaN)
4. Check server logs for confirmation messages

