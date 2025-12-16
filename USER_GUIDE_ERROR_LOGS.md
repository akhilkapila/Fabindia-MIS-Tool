# How to Use Error Logging & Process Log Viewer

## Quick Start

### For End Users: View Last Process Log

1. **Click the "📋 View Last Log" button** in the top-right corner of any page
2. A new window opens showing your last process log
3. If errors exist:
   - ⚠️ An **error section** appears at the top in red
   - Read the extracted error messages
   - Follow the troubleshooting tips provided

### For End Users: Check Tab Error Summaries

1. After running any process (Sales, Advances, Banking, Final):
   - An inline box appears at the top of the tab
2. **If successful**: Green box says ✅ Process completed successfully
3. **If error occurred**: Red box shows ⚠️ Error detected
   - Click "📋 View Full Error Details" to open the detailed log page

---

## Understanding Error Messages

### Common Errors & How to Fix Them

#### "Could not identify Store Code and Date columns"
**What it means**: The system couldn't find the Store Code or Date column in your file.

**How to fix**:
1. Open your file in Excel
2. Check that a column named "Store Code" or similar exists
3. Check that a column named "Date" or similar exists
4. If columns have different names:
   - Go to Admin Portal → [Process Type] Rules
   - Update the mappings to match your actual column names

#### Date Format Errors
**What it means**: Dates in your file aren't in the expected DD-MM-YYYY format.

**How to fix**:
1. In Excel, select all date columns
2. Format as: Text or Date (DD-MM-YYYY)
3. Save the file
4. Try processing again

#### "Sheet name not found"
**What it means**: The file doesn't have the sheet name expected by the system.

**How to fix**:
1. Check the sheet tab name at the bottom of your Excel file
2. Go to Admin Portal → [Process Type] Rules
3. Update "Sheet Name" to match your actual sheet tab name

#### File Encoding Issues (strange characters)
**What it means**: The file encoding doesn't match what the system expects.

**How to fix**:
1. Open the file in Excel
2. Save As → choose "Excel Workbook (.xlsx)"
3. Make sure encoding is UTF-8
4. Try processing again

---

## Viewing Process Logs Step-by-Step

### Method 1: Header Button (Quickest)
1. Click **"📋 View Last Log"** in the top-right
2. See the last process log immediately
3. Errors highlighted at the top
4. Scroll down to see the full log

### Method 2: Tab Error Box
1. After running a process, look for the error/success box at the top of the tab
2. If there's an error, click the **"📋 View Full Error Details"** link
3. Opens the dedicated log page in a new window

### Method 3: Manual Navigation
1. Type in browser: `http://127.0.0.1:5001/last-process-log`
2. See the current process log page

---

## Understanding the Log Viewer Page

The log page has three sections:

### 1. Log File Path (Top)
Shows where the log file is saved on disk:
```
Log File: C:\path\to\Finance\temp_uploads\logs\process_sales_uuid.log
```
*You don't need to do anything with this—it's just informational.*

### 2. Errors Section (If Present)
**Red box** shows:
- ⚠️ **Errors Detected** header
- Error messages extracted from the log
- **What to do** with actionable tips:
  - Check date format
  - Verify all columns exist
  - Check sheet names match
  - Try UTF-8 encoding

### 3. Full Process Log (Bottom)
- Terminal-style view with monospace font
- Shows every step the process took
- Green text on black background for readability
- Helpful for debugging complex issues

---

## Tips for Better Processing

### Before You Process Files

✅ **Checklist:**
- [ ] All required columns are present (Store Code, Date, Amount, etc.)
- [ ] Date columns are formatted as DD-MM-YYYY
- [ ] No blank rows at the top (unless specified in Admin Portal)
- [ ] Sheet name matches what's configured in Admin Portal
- [ ] File is saved as .xlsx or .xls (not .csv unless specified)
- [ ] No special characters in file path (use A-Z, 0-9, underscore, hyphen only)

### If You Get an Error

1. **Check the error message** in the red box at the top of the log page
2. **Look up the error** in "Common Errors & How to Fix Them" section above
3. **Fix the issue** in your file or Admin Portal settings
4. **Re-run the process**
5. The log will update automatically

---

## Admin Portal Configuration

### How to Configure Processing Rules

1. **Click Admin Portal** in top-right (if you're an admin)
2. Choose the tab: Sales / Advances / Banking / Final
3. **Column Mappings**: 
   - Left side: System expects these names
   - Right side: Type your actual file column names
4. **Sheet Name**: Type the exact sheet tab name from your file
5. **Start Row**: The row number where data starts (usually 2 or 3)
6. Click "Save Rules"

### Example:
If your file has a column "Client Store Code" instead of "Store Code":
- In Admin Portal, set: `Store Code = Client Store Code`
- The system will map this automatically

---

## FAQ

**Q: Can I see old process logs?**
A: Currently, you only see the most recent log. Old logs are saved in `temp_uploads/logs/` on the server.

**Q: What if the log page doesn't show errors?**
A: The process completed successfully! But if you still had issues, check that the file was downloaded correctly.

**Q: Can I share the log with someone?**
A: Yes! Copy the text from the full process log section and paste into an email or document. The log contains all diagnostic information.

**Q: Why does the error message say "logger not defined"?**
A: This was a bug in older versions. Your server is running the fixed version now. If you see this, contact your admin.

**Q: My process ran but the file looks wrong. What should I do?**
A: 
1. Download the file again
2. Check that:
   - Dates display as DD-MM-YYYY (not timestamps)
   - Numbers are numeric (right-aligned), not text (left-aligned)
3. Open the process log to see what formatting was applied
4. If something is wrong, contact your admin with the log file

---

## Troubleshooting Checklist

| Issue | Check |
|-------|-------|
| Log page shows "No log available" | Run a process first |
| Error summary doesn't appear | Wait 5 seconds and refresh the page |
| File downloads but looks wrong | Check if post-processing applied (dates as DD-MM-YYYY) |
| "Column not found" error | Check Admin Portal mappings match your file's column names |
| Dates show as numbers (e.g., 45261) | Re-run process; post-processing will format them |
| File won't process at all | Check file encoding is UTF-8; try re-saving the file |

---

## Need More Help?

1. **Check the detailed log**: Click "View Last Log" and read the full log
2. **Review Admin Portal settings**: Make sure all rules are configured for your file structure
3. **Contact your administrator**: Share the process log file from `temp_uploads/logs/`

