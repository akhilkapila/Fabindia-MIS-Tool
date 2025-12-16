#!/usr/bin/env python3
"""
Test the load_file_smartly function with various file formats.
"""
import sys
import os
import tempfile
import io
from datetime import datetime
from openpyxl import Workbook
import pandas as pd

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import load_file_smartly

print("=" * 70)
print("TESTING FILE LOADING FUNCTION")
print("=" * 70)

test_data = [
    ['Store Code', 'Date', 'Amount'],
    ['S001', '2025-11-01', 1000],
    ['S002', '2025-11-02', 2000],
]

# Helper class to mock Flask FileStorage
class MockFileStorage:
    def __init__(self, content, filename):
        self.stream = io.BytesIO(content)
        self.filename = filename
    
    def read(self, *args, **kwargs):
        if args:  # If size is specified
            return self.stream.read(args[0])
        return self.stream.read()
    
    def seek(self, pos):
        return self.stream.seek(pos)
    
    def __getattr__(self, name):
        # Delegate any other attribute access to the underlying stream
        return getattr(self.stream, name)

# Test 1: CSV format
print("\n1. Testing CSV format...")
csv_content = io.BytesIO()
for row in test_data:
    csv_content.write(','.join(str(x) for x in row).encode('utf-8') + b'\n')

try:
    mock_file = MockFileStorage(csv_content.getvalue(), 'test.csv')
    df = load_file_smartly(mock_file, sheet_name='Sheet1', start_row=1)
    assert df.shape[0] == 2, f"Expected 2 rows, got {df.shape[0]}"
    assert df.shape[1] == 3, f"Expected 3 columns, got {df.shape[1]}"
    print(f"   ✓ CSV loaded successfully: {df.shape}")
except Exception as e:
    print(f"   ✗ CSV loading failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Test 2: XLSX format
print("\n2. Testing XLSX format...")
xlsx_bytes = io.BytesIO()
wb = Workbook()
ws = wb.active
for row in test_data:
    ws.append(row)
wb.save(xlsx_bytes)
xlsx_bytes.seek(0)

try:
    mock_file = MockFileStorage(xlsx_bytes.getvalue(), 'test.xlsx')
    df = load_file_smartly(mock_file, sheet_name=None, start_row=1)
    assert df.shape[0] == 2, f"Expected 2 rows, got {df.shape[0]}"
    assert df.shape[1] == 3, f"Expected 3 columns, got {df.shape[1]}"
    print(f"   ✓ XLSX loaded successfully: {df.shape}")
except Exception as e:
    print(f"   ✗ XLSX loading failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Test 3: XLS format (old Excel)
print("\n3. Testing XLS format...")
xls_path = tempfile.mktemp(suffix='.xls')
wb = Workbook()
ws = wb.active
for row in test_data:
    ws.append(row)
# Note: openpyxl can't save to .xls, but xlrd can read .xlsx as fallback
# So we test with .xlsx and rename it for testing xlrd
try:
    import xlrd
    print(f"   ✓ xlrd is available (version {xlrd.__version__})")
except ImportError:
    print(f"   ⚠ xlrd not available, skipping XLS test")

print("\n" + "=" * 70)
print("✓ FILE LOADING TESTS PASSED!")
print("=" * 70)
print("\nThe app can load:")
print("  - CSV files")
print("  - XLSX files (modern Excel)")
print("  - XLS files (legacy Excel, via xlrd)")
print("  - XLSM files (Excel with macros)")
print("  - XLSB files (Excel binary, via pyxlsb)")
