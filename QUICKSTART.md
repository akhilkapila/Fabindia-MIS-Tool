# Finance Tool - Quick Start Guide

## Start the Application

```powershell
cd "D:\Python Project\MIS Took\FinanceTool - Test - Working"
.\.venv\Scripts\python.exe app.py
```

Then open: **http://127.0.0.1:5001**

## Login Credentials (Default)
- **Username**: admin
- **Password**: admin

## Main Features

### 1. Sales Processing
- Upload MIS Working file
- Automatic formatting applied (dates as DD-MM-YYYY)
- Download processed file

### 2. Advances Processing
- Similar to Sales
- Separate data handling
- Formatted Excel output

### 3. Banking/Collection Processing
- Bank transaction processing
- Applied formatting
- Log file generation

### 4. Combine & Final MIS (Two-Step Process)

**Step A - Combine**:
1. Upload MIS Working file (multiple stores)
2. System concatenates data from row 3
3. Appends CK column (Store+Date match key)
4. Download as `processed_combine.xlsx`

**Step B - Final**:
1. Upload the combine output + final MIS file
2. System updates Reconciliation sheet
3. Preserves other sheets
4. Download as `processed_final.xlsx`

## Output Formatting (Automatic)

✓ **Dates**: Formatted as DD-MM-YYYY  
✓ **Numbers**: General format  
✓ **Text**: General format  
✓ **Blank Cells**: Highlighted in black  
✓ **Remarks**: Preserved unchanged  

## Process Logs

After each operation:
- Click "View Last Process Log" in Final Process tab
- Shows detailed steps and timestamps
- Logs stored in `temp_uploads/logs/`

## File Support

Supported input formats:
- ✓ CSV files
- ✓ XLS (legacy Excel)
- ✓ XLSX (modern Excel)
- ✓ XLSM (Excel with macros)
- ✓ XLSB (Excel binary)

## Admin Panel

Access admin features:
1. Go to http://127.0.0.1:5001
2. Click "Admin Portal" (top right, if admin user)
3. Manage users, view database info, etc.

## Troubleshooting

**Server won't start?**
```powershell
.\.venv\Scripts\python.exe -m pip list | grep Flask
```
Should show Flask 3.1.2

**File won't upload?**
- Ensure file is in supported format
- Check file isn't corrupted
- Check column names match expected keywords

**Formatting not applied?**
- Check temp_uploads/ directory exists
- Verify downloaded file is .xlsx format
- Open in Excel and check cell formats

## Documentation

For detailed technical documentation:
- See `SETUP_VERIFICATION_REPORT.txt`
- See code comments in `app.py`
- See route handlers for specific processing logic

## Key Directories

- `templates/` - HTML templates
- `static/` - CSS and JavaScript
- `temp_uploads/` - Output files and logs
- `migrations/` - Database migrations
- `tests/` - Unit tests

---

**Last Updated**: December 9, 2025  
**Status**: ✓ Production Ready
