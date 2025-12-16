#!/usr/bin/env python3
"""
Quick validation that all imports and critical functions exist.
"""
import sys
import os

# Add parent directory to path so we can import app
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

print("=" * 60)
print("TESTING IMPORTS AND CRITICAL FUNCTIONS")
print("=" * 60)

try:
    print("\n1. Importing Flask and dependencies...")
    from flask import Flask, render_template, jsonify, request, send_file, session
    from flask_login import LoginManager, login_required, current_user
    from flask_sqlalchemy import SQLAlchemy
    from flask_migrate import Migrate
    print("   ✓ Flask imports successful")
except ImportError as e:
    print(f"   ✗ Flask import error: {e}")
    sys.exit(1)

try:
    print("\n2. Importing pandas and openpyxl...")
    import pandas as pd
    from openpyxl import load_workbook, Workbook
    print("   ✓ Data processing imports successful")
except ImportError as e:
    print(f"   ✗ Data import error: {e}")
    sys.exit(1)

try:
    print("\n3. Importing app.py...")
    import app
    print("   ✓ app.py imported successfully")
except ImportError as e:
    print(f"   ✗ app.py import error: {e}")
    sys.exit(1)

# Check for critical functions
print("\n4. Checking for critical helper functions...")
critical_functions = [
    'load_file_smartly',
    'find_column_by_keywords',
    'extract_month_suffix_from_dates',
    'post_process_workbook',
    'start_process_logger'
]

missing = []
for func_name in critical_functions:
    if hasattr(app, func_name):
        print(f"   ✓ {func_name} found")
    else:
        print(f"   ✗ {func_name} NOT found")
        missing.append(func_name)

if missing:
    print(f"\n✗ Missing functions: {missing}")
    sys.exit(1)

# Check for critical routes
print("\n5. Checking for critical routes...")
critical_routes = [
    'home',
    'process_sales',
    'process_advances',
    'process_banking',
    'process_combine_only',
    'process_final_only',
    'processing_log'
]

missing_routes = []
for route_name in critical_routes:
    if hasattr(app, route_name):
        print(f"   ✓ {route_name} route found")
    else:
        print(f"   ✗ {route_name} route NOT found")
        missing_routes.append(route_name)

if missing_routes:
    print(f"\n✗ Missing routes: {missing_routes}")
    sys.exit(1)

print("\n" + "=" * 60)
print("✓ ALL CHECKS PASSED!")
print("=" * 60)
print("\nThe Flask app is ready to run.")
print("Start it with: python app.py")
print("Access it at: http://127.0.0.1:5001")
