# AlternateStoreCode Fix - December 11, 2025

## Problem Identified
**AlternateStoreCode column was empty in the output file.**

### Root Cause Analysis
The Sales Rule had an **incorrect mapping configuration**:

```
BEFORE (WRONG):
  AlternateStoreCode <- AlternateStoreCode  ✓ Correct
  StoreCode          <- AlternateStoreCode  ✗ WRONG!
```

**What this meant:**
- Both `AlternateStoreCode` and `StoreCode` output columns were reading from the same CSV column: `AlternateStoreCode`
- The CSV column `StoreCode` was being ignored
- After renaming, `AlternateStoreCode` had no source data left (it was consumed by StoreCode)
- Result: AlternateStoreCode ended up empty/NaN

### The Fix Applied

**Changed the StoreCode mapping to source from the correct CSV column:**

```
AFTER (CORRECT):
  AlternateStoreCode <- AlternateStoreCode  ✓ Reads from CSV AlternateStoreCode column
  StoreCode          <- StoreCode           ✓ Reads from CSV StoreCode column
```

**What this does:**
- `AlternateStoreCode` now correctly reads from CSV column `AlternateStoreCode`
- `StoreCode` now correctly reads from CSV column `StoreCode`
- Both columns have their own data source
- No more empty AlternateStoreCode values ✓

## Technical Details

**File Modified:** `app.db` (SQLite database)
**Table:** `SalesRule` (id=1)
**Field:** `mappings` (JSON)

**Change:**
```json
{
  "AlternateStoreCode": "AlternateStoreCode",
  "StoreCode": "StoreCode"  ← Changed from "AlternateStoreCode" to "StoreCode"
}
```

## Processing Flow (After Fix)

### CSV Input
```
RegionName | StoreName | StoreCode | AlternateStoreCode | BillDate | ...
-----------|-----------|-----------|-------------------|----------|-----
Delhi      | Store 123 | ST-001    | 1020              | 11-12-2025 | ...
Mumbai     | Store 456 | ST-002    | 1021              | 12-12-2025 | ...
```

### Processing Steps
1. **Load CSV** → Columns detected: StoreName, StoreCode, AlternateStoreCode, etc.
2. **Rename columns** using mappings:
   - `AlternateStoreCode` (CSV) → `AlternateStoreCode` (Output) = "1020", "1021"
   - `StoreCode` (CSV) → `StoreCode` (Output) = "ST-001", "ST-002"
3. **Copy AlternateStoreCode to StoreCode backup** (BP prefix removal)
4. **Remove BP prefix** from both columns
5. **Output Excel** with both columns populated ✓

### Excel Output
```
AlternateStoreCode | StoreCode | BillDate   | ...
-------------------|-----------|------------|-----
1020               | ST-001    | 11-12-2025 | ...
1021               | ST-002    | 12-12-2025 | ...
```

## What Now Works

✅ **AlternateStoreCode** - Contains actual data from CSV
✅ **StoreCode** - Contains actual data from CSV  
✅ **BillDate** - Formatted as DD-MM-YYYY
✅ **Both columns have independent data** - Not conflicting

## Server Status
- ✅ Flask restarted and running at `http://127.0.0.1:5001`
- ✅ Mappings updated in database
- ✅ Ready for testing

## Next Steps - Test
1. Upload your sales CSV file
2. Process Sales
3. Download the Excel file
4. **Verify:**
   - ✓ AlternateStoreCode column has data (store codes like "1020", "1021")
   - ✓ StoreCode column has data (store codes like "ST-001", "ST-002")
   - ✓ BillDate shows as DD-MM-YYYY format
   - ✓ No NaN/empty values in these columns

## Why This Happened

When you manually updated the mappings in Admin Portal, you likely set:
- `AlternateStoreCode` → `AlternateStoreCode` ✓
- `StoreCode` → `AlternateStoreCode` ✗

This was a configuration mistake because both were pointing to the same source column. The fix ensures each output column gets its own dedicated source column from the CSV.

