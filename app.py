import os
import json
import uuid
import io
import zipfile
import pandas as pd
import time 
from openpyxl import load_workbook
from openpyxl.styles import PatternFill, Font
from flask import (
    Flask, render_template, request, send_file, session, jsonify, 
    redirect, url_for, flash, abort
)
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import (
    LoginManager, UserMixin, login_user, logout_user, 
    login_required, current_user
)
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField, BooleanField, SelectField
from wtforms.validators import DataRequired, Email, EqualTo, Length
from werkzeug.security import generate_password_hash, check_password_hash

# --- 1. APP & DB CONFIGURATION ---
app = Flask(__name__)

@app.template_filter('fromjson')
def from_json(value):
    """Loads a JSON string in the Jinja template."""
    try:
        logger, log_path = start_process_logger('process_banking')
        logger.info('Received banking process request')
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return {} 

@app.context_processor
def inject_cache_version():
    """Injects a cache-busting version string into all templates."""
    return dict(cache_v=int(time.time()))

app.secret_key = 'your-very-secret-key-change-this'

basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'app.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)
migrate = Migrate(app, db) 

UPLOAD_FOLDER = 'temp_uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
LOG_FOLDER = os.path.join(UPLOAD_FOLDER, 'logs')
os.makedirs(LOG_FOLDER, exist_ok=True)

import logging
from datetime import datetime, timedelta

# --- 2. LOGIN MANAGER CONFIGURATION ---
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
login_manager.login_message_category = 'info'

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))

# --- 3. DATABASE MODELS (FINAL) ---
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    age = db.Column(db.Integer)
    department = db.Column(db.String(100))
    reporting_manager = db.Column(db.String(100))
    is_admin = db.Column(db.Boolean, default=False, nullable=False)
    is_approved = db.Column(db.Boolean, default=False, nullable=False)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class Setting(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(50), unique=True, nullable=False)
    value = db.Column(db.Text, nullable=False)

class SalesRule(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    start_row = db.Column(db.Integer, nullable=False, default=6)
    sheet_name = db.Column(db.String(100), nullable=False, default='SalesReportAbstract')
    mappings = db.Column(db.Text, nullable=False)
    bp_remove_cols = db.Column(db.String(255), default='StoreCode,AlternateStoreCode')
    prefix_remove_col = db.Column(db.String(50), default='StoreCode')
    prefix_remove_values = db.Column(db.String(50), default='97,98')
    copy_col_source = db.Column(db.String(50), default='AlternateStoreCode')
    copy_col_dest = db.Column(db.String(50), default='StoreCode')

class AdvanceRule(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    start_row = db.Column(db.Integer, nullable=False, default=2)
    sheet_name = db.Column(db.String(100), nullable=False, default='Sheet')
    mappings = db.Column(db.Text, nullable=False)
    vlookup_source_col = db.Column(db.String(50), default='Store')
    vlookup_sales_col = db.Column(db.String(50), default='StoreName')
    vlookup_dest_col = db.Column(db.String(50), default='Store Code')
    vlookup_value_col = db.Column(db.String(50), default='StoreCode')

class BankRule(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    bank_name = db.Column(db.String(100), unique=True, nullable=False)
    start_row = db.Column(db.Integer, nullable=False, default=2)
    sheet_name = db.Column(db.String(100), nullable=False, default='Sheet1')
    mappings = db.Column(db.Text, nullable=False)

class SearchFile(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(255), nullable=False)
    filepath = db.Column(db.String(255), nullable=False)
    upload_date = db.Column(db.DateTime, default=datetime.utcnow)

class SearchCategoryRule(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    category_name = db.Column(db.String(50), unique=True, nullable=False)
    sheet_name = db.Column(db.String(100), nullable=False)

class SearchPaymentModeRule(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    mode_name = db.Column(db.String(50), nullable=False) # Not Unique anymore
    columns = db.Column(db.String(255), nullable=False) # Comma separated keywords
    sheet_name = db.Column(db.String(255), nullable=True) # Multiselect sheets, comma separated


# --- 4. HELPER FUNCTIONS (ROBUST FILE LOADER) ---
def load_file_smartly(file, sheet_name, start_row):
    """
    Loads CSV, XLS, XLSX, or XLSB files robustly.
    Handles encoding errors, file extension mismatches, and missing sheets.
    Loads everything as strings to preserve data fidelity.
    """
    filename = file.filename.lower()
    header_row = start_row - 1 
    
    # Helper to try loading as CSV with multiple encodings
    def try_load_as_csv(f):
        encodings = ['utf-8', 'latin1', 'cp1252', 'ISO-8859-1']
        for enc in encodings:
            try:
                f.seek(0)
                df = pd.read_csv(f, header=header_row, encoding=enc, dtype=str, on_bad_lines='skip')
                # Ensure all column names are strings
                df.columns = df.columns.astype(str)
                return df
            except Exception:
                continue
        # Last resort
        f.seek(0)
        df = pd.read_csv(f, header=header_row, encoding='utf-8', encoding_errors='replace', dtype=str)
        df.columns = df.columns.astype(str)
        return df

    # Helper to try loading Excel safely (fallback to 1st sheet)
    def try_load_excel(f, engine, specific_sheet):
        try:
            # Try the specific sheet first
            df = pd.read_excel(f, header=header_row, engine=engine, sheet_name=specific_sheet, dtype=str)
            # Ensure all column names are strings
            df.columns = df.columns.astype(str)
            return df
        except ValueError as e:
            if "Worksheet" in str(e) and "not found" in str(e):
                print(f"Sheet '{specific_sheet}' not found. Trying first sheet...")
                f.seek(0)
                # Fallback: Load the first sheet (index 0)
                df = pd.read_excel(f, header=header_row, engine=engine, sheet_name=0, dtype=str)
                df.columns = df.columns.astype(str)
                return df
            raise e # Re-raise other errors

    # Helper to try loading XLSB files
    def try_load_xlsb(f, specific_sheet):
        try:
            print(f"Loading XLSB: {file.filename}")
            f.seek(0)
            df = pd.read_excel(f, header=header_row, engine='pyxlsb', sheet_name=specific_sheet, dtype=str)
            # Ensure all column names are strings
            df.columns = df.columns.astype(str)
            return df
        except ValueError as e:
            if "not found" in str(e).lower() or "sheet" in str(e).lower():
                print(f"Sheet '{specific_sheet}' not found in XLSB. Trying first sheet...")
                f.seek(0)
                df = pd.read_excel(f, header=header_row, engine='pyxlsb', sheet_name=0, dtype=str)
                df.columns = df.columns.astype(str)
                return df
            raise e

    try:
        # 1. Try loading based on extension
        if filename.endswith('.csv'):
            print(f"Loading CSV: {file.filename}")
            return try_load_as_csv(file)
        
        elif filename.endswith('.xlsb'):
            print(f"Loading XLSB: {file.filename}")
            return try_load_xlsb(file, sheet_name)
        
        elif filename.endswith(('.xlsx', '.xlsm')):
            print(f"Loading XLSX: {file.filename}")
            try:
                return try_load_excel(file, 'openpyxl', sheet_name)
            except Exception as e:
                print(f"Openpyxl failed ({e}). Trying xlrd...")
                try:
                    file.seek(0)
                    return try_load_excel(file, 'xlrd', sheet_name)
                except Exception as e2:
                    print(f"Xlrd failed ({e2}). Trying as CSV...")
                    return try_load_as_csv(file)

        elif filename.endswith('.xls'):
            print(f"Loading XLS: {file.filename}")
            try:
                return try_load_excel(file, 'xlrd', sheet_name)
            except Exception as e:
                 print(f"Xlrd failed ({e}). Trying openpyxl...")
                 try:
                     file.seek(0)
                     return try_load_excel(file, 'openpyxl', sheet_name)
                 except Exception as e2:
                     print(f"Openpyxl failed ({e2}). Trying as CSV...")
                     return try_load_as_csv(file)
        else:
             # Unknown extension, try XLSB first, then CSV as fallback
             try: return try_load_xlsb(file, sheet_name)
             except: pass
             try: return try_load_as_csv(file)
             except: pass
             raise ValueError(f"Unsupported file type: {filename}")

    except Exception as e:
        # Re-raise with a clear message
        raise ValueError(f"Could not load file {file.filename}. Error: {str(e)}")


def find_column_by_keywords(df, keywords):
    """Find first column in df whose name matches all keywords (case-insensitive)."""
    for col in df.columns:
        if not isinstance(col, str):
            continue
        up = col.upper()
        if all(k.upper() in up for k in keywords):
            return col
    # fallback: try variants (underscore/space)
    for col in df.columns:
        if not isinstance(col, str):
            continue
        c = col.replace('_', ' ').upper()
        if all(k.upper() in c for k in keywords):
            return col
    
    # Additional fallback: if looking for just one keyword, be more lenient
    if len(keywords) == 1:
        keyword = keywords[0].upper()
        for col in df.columns:
            if not isinstance(col, str):
                continue
            if keyword in col.upper().replace('_', ' ').replace('-', ' '):
                return col
    return None


def extract_month_suffix_from_dates(series):
    """Given a pandas Series of date strings, return month suffix like "Nov'25".
    Uses the most common non-null month in the series.
    """
    try:
        dates = pd.to_datetime(series, errors='coerce')
        if dates.dropna().empty:
            return None
        # get most common month-year
        month_year = dates.dropna().dt.to_period('M').mode()
        if len(month_year) == 0:
            # fallback to first non-null
            dt = dates.dropna().iloc[0]
        else:
            dt = month_year.iloc[0].to_timestamp()
        mon = dt.strftime('%b')
        yr = dt.strftime("%y")
        return f"{mon}'{yr}"
    except Exception:
        return None

def get_output_columns(type_key):
    cols = db.session.execute(db.select(Setting).filter_by(key=type_key)).scalar_one_or_none()
    if cols:
        return [col.strip() for col in cols.value.split('\n') if col.strip()]
    return []

def get_output_columns_str(type_key):
    setting = db.session.execute(db.select(Setting).filter_by(key=type_key)).scalar_one_or_none()
    return setting.value if setting else ""

def excel_col_name(n):
    name = ""
    n = n + 1 
    while n > 0:
        n, remainder = divmod(n - 1, 26)
        name = chr(65 + remainder) + name
    return name

def get_output_columns_str_with_letters(type_key):
    cols = get_output_columns(type_key)
    if not cols: return ""
    formatted_lines = []
    for i, col in enumerate(cols):
        letter = excel_col_name(i)
        formatted_lines.append(f"{letter}: {col}")
    return "\n".join(formatted_lines)


# --- Logging helper and workbook post-processing (applies to Sales/Advances/Banking/Final) ---
LOG_FOLDER = os.path.join(UPLOAD_FOLDER, 'logs')
os.makedirs(LOG_FOLDER, exist_ok=True)

import logging
from datetime import datetime

def start_process_logger(operation_name: str):
    log_id = f"{operation_name}_{uuid.uuid4().hex}"
    log_path = os.path.join(LOG_FOLDER, f"{log_id}.log")
    logger = logging.getLogger(log_id)
    logger.setLevel(logging.DEBUG)
    if not logger.handlers:
        fh = logging.FileHandler(log_path, encoding='utf-8')
        fh.setLevel(logging.DEBUG)
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        fh.setFormatter(formatter)
        logger.addHandler(fh)
    try:
        session['last_process_log'] = log_path
    except Exception:
        pass
    logger.info(f"Starting process: {operation_name}")
    return logger, log_path


def save_with_formatting(df, path, sheet_name='Sheet1'):
    """
    Saves DataFrame to Excel using XlsxWriter with HIGH-PERFORMANCE formatting applied in-flight.
    Eliminates the need for post_process_workbook.
    """
    try:
        # Use existing 'ExcelWriter' context but with 'xlsxwriter' engine
        with pd.ExcelWriter(path, engine='xlsxwriter', date_format='dd-mm-yyyy', datetime_format='dd-mm-yyyy') as writer:
            df.to_excel(writer, index=False, sheet_name=sheet_name)
            workbook = writer.book
            worksheet = writer.sheets[sheet_name]
            
            # --- FORMAT DEFINITIONS ---
            header_fmt = workbook.add_format({'bold': True, 'bg_color': '#DCE6F1', 'border': 1})
            date_fmt = workbook.add_format({'num_format': 'dd-mm-yyyy'})
            num_fmt = workbook.add_format({'num_format': 'General'}) # "Values Pasted" style
            # black_fill for blank columns: pattern 1 = solid
            black_fill = workbook.add_format({'pattern': 1, 'bg_color': '#000000', 'font_color': '#FFFFFF'})
            
            # Application:
            # 1. Format Header
            for col_num, value in enumerate(df.columns.values):
                worksheet.write(0, col_num, value, header_fmt)

            # 2. Set Column Widths & Apply Formats to Columns
            # We can apply format to the whole column range directly! 0-cost!
            for idx, col_name in enumerate(df.columns):
                series = df[col_name]
                
                # Check if column is fully empty (all NaN or empty strings)
                is_empty = series.isna().all() or (series.astype(str).str.strip() == '').all()
                
                if is_empty:
                    # Apply black fill to the entire column
                    worksheet.set_column(idx, idx, 10, black_fill)
                    continue

                # Determine type for formatting
                # Heuristic: check dtype or sample
                col_width = max(len(str(col_name)), 10) 
                
                # Check for Date (Strict Logic for specific columns + Generic detection)
                col_upper = str(col_name).upper()
                if 'BILLDATE' in col_upper or 'ORDER DATE' in col_upper or 'TRANSACTION DATE' in col_upper:
                     worksheet.set_column(idx, idx, 15, date_fmt)
                elif pd.api.types.is_datetime64_any_dtype(series):
                     worksheet.set_column(idx, idx, 15, date_fmt)
                # Check for Numeric
                elif pd.api.types.is_numeric_dtype(series):
                     worksheet.set_column(idx, idx, 12, num_fmt)
                # Text / Object
                else:
                    # Generic fallback: if it looks like a date column by name, force date format
                    if 'DATE' in col_upper:
                        worksheet.set_column(idx, idx, 15, date_fmt)
                    else:
                        worksheet.set_column(idx, idx, col_width) # Default format

        return True
    except Exception as e:
        print(f"Error in save_with_formatting: {e}")
        # Fallback to standard save if xlsxwriter fails (unlikely)
        df.to_excel(path, index=False)
        return False

# --- 5. FORMS (FINAL) ---
class LoginForm(FlaskForm):
    email = StringField('Email', validators=[DataRequired(), Email()])
    password = PasswordField('Password', validators=[DataRequired()])
    remember = BooleanField('Remember Me')
    submit = SubmitField('Login')

class RegistrationForm(FlaskForm):
    email = StringField('Email', validators=[DataRequired(), Email()])
    password = PasswordField('Password', validators=[DataRequired(), Length(min=8)])
    confirm_password = PasswordField('Confirm Password', validators=[DataRequired(), EqualTo('password', message='Passwords must match.')])
    name = StringField('Full Name', validators=[DataRequired()])
    age = StringField('Age', validators=[DataRequired()])
    department = StringField('Department', validators=[DataRequired()])
    reporting_manager = StringField('Reporting Manager', validators=[DataRequired()])
    submit = SubmitField('Create Account')

class ResetPasswordForm(FlaskForm):
    password = PasswordField('New Password', validators=[DataRequired(), Length(min=8)])
    confirm_password = PasswordField('Confirm New Password', validators=[DataRequired(), EqualTo('password', message='Passwords must match.')])
    submit = SubmitField('Reset Password')

class EditUserForm(FlaskForm):
    email = StringField('Email', validators=[DataRequired(), Email()])
    name = StringField('Full Name', validators=[DataRequired()])
    age = StringField('Age', validators=[DataRequired()]) 
    department = StringField('Department', validators=[DataRequired()])
    reporting_manager = StringField('Reporting Manager', validators=[DataRequired()])
    is_admin = BooleanField('Is Admin') 
    submit = SubmitField('Update User')

# --- 6. AUTHENTICATION ROUTES (FINAL) ---
@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('home'))
    form = LoginForm()
    if form.validate_on_submit():
        user = db.session.execute(db.select(User).filter_by(email=form.email.data)).scalar_one_or_none()
        if user and user.check_password(form.password.data):
            if not user.is_approved:
                flash('Your account has not been approved by an administrator yet.', 'warning')
                return redirect(url_for('login'))
            login_user(user, remember=form.remember.data)
            next_page = request.args.get('next')
            return redirect(next_page) if next_page else redirect(url_for('home'))
        else:
            flash('Login Unsuccessful. Please check email and password.', 'danger')
    return render_template('login.html', title='Login', form=form)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('home'))
    form = RegistrationForm()
    if form.validate_on_submit():
        user = User(
            email=form.email.data, name=form.name.data, age=form.age.data,
            department=form.department.data, reporting_manager=form.reporting_manager.data,
            is_approved=False
        )
        user.set_password(form.password.data)
        db.session.add(user)
        db.session.commit()
        flash('Your account has been created! Please wait for an administrator to approve it.', 'success')
        return redirect(url_for('login'))
    return render_template('register.html', title='Register', form=form)

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    """Allow users to request a password reset. Admin must approve via Admin Portal."""
    if current_user.is_authenticated:
        return redirect(url_for('home'))
    
    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        user = db.session.execute(db.select(User).filter_by(email=email)).scalar_one_or_none()
        
        if user:
            flash('If an account exists with that email, instructions will be sent to contact an administrator. Please reach out to your admin for password reset.', 'info')
        else:
            # Still show same message for security (don't reveal if email exists)
            flash('If an account exists with that email, instructions will be sent to contact an administrator. Please reach out to your admin for password reset.', 'info')
        return redirect(url_for('login'))
    
    return render_template('forgot_password.html', title='Forgot Password')

# --- 7. MAIN APP ROUTES (FINAL) ---
@app.route('/')
@login_required
def home():
    banks = db.session.execute(db.select(BankRule).order_by(BankRule.bank_name)).scalars().all()
    bank_names = [b.bank_name for b in banks]
    last_log = session.get('last_process_log')
    
    search_categories = db.session.execute(db.select(SearchCategoryRule).order_by(SearchCategoryRule.category_name)).scalars().all()
    search_modes = db.session.execute(db.select(SearchPaymentModeRule).order_by(SearchPaymentModeRule.mode_name)).scalars().all()
    search_file = db.session.execute(db.select(SearchFile)).scalar_one_or_none()
    
    return render_template('index.html', admin_portal=current_user.is_admin, bank_names=bank_names, current_user=current_user, last_log=last_log,
                           search_categories=search_categories, search_modes=search_modes, search_file=search_file)


@app.route('/processing-log')
@login_required
def processing_log():
    """Render a simple page showing the most recent process log contents."""
    log_path = session.get('last_process_log')
    # If no session log, try to pick the newest in LOG_FOLDER
    if not log_path or not os.path.exists(log_path):
        try:
            files = [os.path.join(LOG_FOLDER, f) for f in os.listdir(LOG_FOLDER) if f.endswith('.log')]
            files.sort(key=lambda p: os.path.getmtime(p), reverse=True)
            log_path = files[0] if files else None
        except Exception:
            log_path = None

    log_content = ''
    if log_path and os.path.exists(log_path):
        try:
            with open(log_path, 'r', encoding='utf-8', errors='replace') as fh:
                # Show last 20000 characters for safety
                data = fh.read()
                log_content = data[-20000:]
        except Exception as e:
            log_content = f'Could not read log file: {e}'
    else:
        log_content = 'No process logs found.'

    return render_template('processing_log.html', log_path=log_path, log_content=log_content)


@app.route('/api/last-log-summary')
@login_required
def api_last_log_summary():
    """Return a JSON summary of the most recent process log: path, timestamp, error lines."""
    result = {'found': False, 'path': None, 'errors': [], 'warnings': [], 'info': []}
    log_path = session.get('last_process_log')
    if not log_path or not os.path.exists(log_path):
        try:
            files = [os.path.join(LOG_FOLDER, f) for f in os.listdir(LOG_FOLDER) if f.endswith('.log')]
            files.sort(key=lambda p: os.path.getmtime(p), reverse=True)
            log_path = files[0] if files else None
        except Exception:
            log_path = None

    if not log_path or not os.path.exists(log_path):
        return jsonify(result)

    result['found'] = True
    result['path'] = log_path
    try:
        with open(log_path, 'r', encoding='utf-8', errors='replace') as fh:
            lines = fh.readlines()
            # keep last 1000 lines for scanning
            tail = lines[-1000:]
            for ln in tail:
                up = ln.upper()
                if 'ERROR' in up or 'EXCEPTION' in up:
                    result['errors'].append(ln.strip())
                elif 'WARNING' in up or 'WARN' in up:
                    result['warnings'].append(ln.strip())
                else:
                    result['info'].append(ln.strip())
            # trim arrays for payload
            result['errors'] = result['errors'][-25:]
            result['warnings'] = result['warnings'][-25:]
            result['info'] = result['info'][-25:]
            result['summary'] = {
                'error_count': len(result['errors']),
                'warning_count': len(result['warnings'])
            }
    except Exception as e:
        result['errors'].append(f'Could not read log: {e}')

    return jsonify(result)

# --- 8. FILE PROCESSING ROUTES (FINAL) ---

@app.route('/process-sales', methods=['POST'])
@login_required
def process_sales():
    rule = db.session.get(SalesRule, 1)
    if not rule:
        return jsonify({"error": "Sales rules not found in Admin Portal."}), 400
    
    final_sales_columns = get_output_columns('sales_output_columns')
    if not final_sales_columns:
        return jsonify({"error": "Sales output columns not set in Admin Portal."}), 400
    
    try:
        logger, log_path = start_process_logger('process_sales')
        logger.info('Received sales process request')
        file = request.files.get('sales_file')
        if not file: 
            logger.error("No sales file uploaded")
            return jsonify({"error": "No file uploaded."}), 400

        # Load as STRING to preserve original data exactly (dtype=str)
        logger.info(f"Loading file: {file.filename} from sheet '{rule.sheet_name}' starting at row {rule.start_row}")
        try:
            df = load_file_smartly(file, rule.sheet_name, rule.start_row)
            logger.info(f"✓ File loaded successfully - shape: {df.shape}")
        except Exception as e:
            logger.exception(f"✗ Error loading file: {e}")
            return jsonify({"error": f"Error loading file: {str(e)}"}), 400
        
        logger.info(f"Loaded data - shape: {df.shape}, columns: {list(df.columns)}")
        
        if df.empty:
            logger.error("Loaded dataframe is empty!")
            return jsonify({"error": "No data found in uploaded file."}), 400
        
        try:
            df.columns = df.columns.str.strip().str.upper()
            logger.info(f"✓ Columns converted to uppercase: {list(df.columns)[:10]}...")  # Show first 10
        except Exception as e:
            logger.exception(f"✗ Error converting columns: {e}")
            return jsonify({"error": f"Error processing columns: {str(e)}"}), 400
        
        try:
            mappings = json.loads(rule.mappings)
            logger.info(f"✓ Mappings loaded successfully")
        except Exception as e:
            logger.exception(f"✗ Error loading mappings: {e}")
            return jsonify({"error": f"Error loading mappings: {str(e)}"}), 400
        
        try:
            rename_map = {}
            for final_col in final_sales_columns:
                raw_col_name = mappings.get(final_col, final_col).upper()
                if raw_col_name in df.columns:
                    rename_map[raw_col_name] = final_col
            logger.info(f"✓ Rename map created with {len(rename_map)} mappings")
            
            df_renamed = df.rename(columns=rename_map)
            logger.info(f"✓ After rename: shape={df_renamed.shape}")
        except Exception as e:
            logger.exception(f"✗ Error renaming columns: {e}")
            return jsonify({"error": f"Error renaming columns: {str(e)}"}), 400
        
        try:
            output_df = df_renamed.reindex(columns=final_sales_columns)
            logger.info(f"✓ After reindex: shape={output_df.shape}, has {len(final_sales_columns)} columns")
        except Exception as e:
            logger.exception(f"✗ Error during reindex: {e}")
            return jsonify({"error": f"Error reindexing: {str(e)}"}), 400
        
        if output_df.empty:
            logger.warning("Dataframe is empty after reindex!")
        
        if 'StoreName' in output_df.columns: 
            output_df['StoreName'] = output_df['StoreName'].astype(str).str.strip()
        if 'AlternateStoreCode' in output_df.columns: 
            output_df['AlternateStoreCode'] = output_df['AlternateStoreCode'].astype(str).str.strip()

        # --- COLUMN COPY LOGIC: Copy source column to destination ---
        if rule.copy_col_source and rule.copy_col_dest:
            # FIX: Look for source column in the ORIGINAL dataframe (df) to ensure we get the data
            # even if mapping/renaming didn't catch it.
            source_col_upper = rule.copy_col_source.upper()
            
            if source_col_upper in df.columns:
                # Found it in source! Enforce it into Output columns.
                # We use .values to ignore index alignment issues just in case, though they should match here.
                if rule.copy_col_source in output_df.columns:
                     output_df[rule.copy_col_source] = df[source_col_upper].values
                
                if rule.copy_col_dest in output_df.columns:
                     output_df[rule.copy_col_dest] = df[source_col_upper].values
                
                logger.info(f"✓ Force-copied source '{source_col_upper}' from input file to '{rule.copy_col_source}' and '{rule.copy_col_dest}'")
            
            # Fallback: Use what's already in output_df if we didn't find it in source (maybe it was mapped differently)
            elif rule.copy_col_source in output_df.columns:
                output_df[rule.copy_col_dest] = output_df[rule.copy_col_source].copy()
                logger.info(f"✓ Copied internal {rule.copy_col_source} → {rule.copy_col_dest} ({output_df[rule.copy_col_dest].notna().sum()} rows)")
            
            else:
                logger.warning(f"⚠ Source column '{rule.copy_col_source}' (raw '{source_col_upper}') not found in dataframe. Available: {list(df.columns)[:10]}...")
        else:
            logger.debug(f"No copy rules configured (source={rule.copy_col_source}, dest={rule.copy_col_dest})")

        if rule.bp_remove_cols:
            for col in rule.bp_remove_cols.split(','):
                col = col.strip()
                if col in output_df.columns:
                    output_df[col] = output_df[col].astype(str).str.replace('BP', '', case=False)
                    logger.debug(f"Removed 'BP' prefix from {col}")
        
        if rule.prefix_remove_col and rule.prefix_remove_values:
            initial_rows = len(output_df)
            prefixes = tuple(rule.prefix_remove_values.split(','))
            if rule.prefix_remove_col in output_df.columns:
                output_df = output_df[~output_df[rule.prefix_remove_col].astype(str).str.startswith(prefixes)]
                logger.info(f"Removed {initial_rows - len(output_df)} rows with prefixes {prefixes}")

        # --- DATE FORMAT FIX (DD-MM-YYYY) WITHOUT TIME ---
        # Explicitly parse BillDate with DD-MM-YYYY format detection
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
        
        output_df = output_df.reindex(columns=final_sales_columns)

        processed_filename = f"{uuid.uuid4()}_sales.xlsx" 
        processed_filepath = os.path.join(UPLOAD_FOLDER, processed_filename)
        
        # Save to Excel file using OPTIMIZED save_with_formatting
        logger.info(f"Saving sales dataframe to Excel with fast formatting: shape={output_df.shape}")
        
        success = save_with_formatting(output_df, processed_filepath, sheet_name='Sheet1')
        
        if success:
             logger.info(f"Saved processed sales to {processed_filepath}")
        else:
             logger.error(f"Failed to save {processed_filepath}")
        
        session['processed_sales_filepath'] = processed_filepath
        logger.info(f"Output dataframe shape: {output_df.shape}, rows: {len(output_df)}")
        
        # Verify file exists and has content
        if os.path.exists(processed_filepath):
            file_size = os.path.getsize(processed_filepath)
            logger.info(f"File size after save: {file_size} bytes")
        else:
            logger.error(f"File not found after save: {processed_filepath}")
        
        # ✅ FIX: Read the post-processed file from disk and send it
        logger.info(f"Reading file from disk to send to client: {processed_filepath}")
        try:
            if not os.path.exists(processed_filepath):
                raise FileNotFoundError(f"File not found: {processed_filepath}")
            
            with open(processed_filepath, 'rb') as f:
                file_data = f.read()
            
            if not file_data:
                raise ValueError(f"File is empty: {processed_filepath}")
            
            output_buffer = io.BytesIO(file_data)
            output_buffer.seek(0)
            logger.info(f"Successfully read file from disk: {len(file_data)} bytes")
            
        except Exception as e:
            logger.exception(f"Error reading post-processed file from disk: {e}")
            logger.warning("Falling back to creating buffer from dataframe")
            # Fallback: create new buffer from dataframe
            output_buffer = io.BytesIO()
            output_df.to_excel(output_buffer, index=False, engine='openpyxl', sheet_name='Sheet1')
            output_buffer.seek(0)
            logger.info(f"Created fallback buffer: {output_buffer.getbuffer().nbytes} bytes")
        
        logger.info("Sending file to user")
        return send_file(
            output_buffer, 
            as_attachment=True, 
            download_name="Processed_Sales.xlsx", 
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )

    except Exception as e:
        try:
            logger.exception(f"Error processing sales: {e}")
        except Exception:
            print(f"Error processing sales: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/process-advances', methods=['POST'])
@login_required
def process_advances():
    rule = db.session.get(AdvanceRule, 1)
    if not rule:
        return jsonify({"error": "Advances rules not found in Admin Portal."}), 400

    final_advances_columns = get_output_columns('advances_output_columns')
    if not final_advances_columns:
        return jsonify({"error": "Advances output columns not set in Admin Portal."}), 400

    try:
        logger, log_path = start_process_logger('process_advances')
        logger.info('Received advances process request')
        if 'processed_sales_filepath' not in session:
            return jsonify({"error": "Please process a Sales file (Tab 1) first."}), 400
        
        sales_filepath = session['processed_sales_filepath']
        advances_file = request.files.get('advances_file')
        if not advances_file: return jsonify({"error": "No Advances file uploaded."}), 400

        sales_df = pd.read_excel(sales_filepath, engine='openpyxl')
        
        # Use robust loader
        advances_df = load_file_smartly(advances_file, rule.sheet_name, rule.start_row)
        advances_df.columns = advances_df.columns.str.strip().str.upper()
        mappings = json.loads(rule.mappings)

        rename_map = {}
        for final_col in final_advances_columns:
            db_raw_col = mappings.get(final_col, final_col).upper()
            if db_raw_col in advances_df.columns:
                rename_map[db_raw_col] = final_col
        advances_renamed = advances_df.rename(columns=rename_map)
        output_advances_df = advances_renamed.reindex(columns=final_advances_columns)
        
        if 'StoreName' not in sales_df or 'StoreCode' not in sales_df:
            return jsonify({"error": "Processed Sales file is missing 'StoreName' or 'StoreCode'."}), 400
        
        adv_key = rule.vlookup_source_col
        sales_key = rule.vlookup_sales_col
        dest_key = rule.vlookup_dest_col
        val_key = rule.vlookup_value_col

        if not (adv_key and sales_key and dest_key and val_key):
             return jsonify({"error": "VLOOKUP rules incomplete in Admin Portal."}), 400
        if adv_key not in output_advances_df.columns:
            return jsonify({"error": f"VLOOKUP Error: Advances key '{adv_key}' not in file. Check admin rules."}), 400
        
        lookup_map = sales_df[[sales_key, val_key]].drop_duplicates(subset=[sales_key])
        
        merged_df = pd.merge(
            output_advances_df,
            lookup_map.rename(columns={val_key: f'Sales_{val_key}'}), 
            left_on=adv_key,      
            right_on=sales_key, 
            how='left'
        )
        merged_df[dest_key] = merged_df[f'Sales_{val_key}']
        
        numeric_cols = [
            'Total Quantity', 'Approximate Value', 'Advance Amount',
            'Cash', 'Credit Card', 'Other Payments'
        ]
        if dest_key in merged_df.columns:
            merged_df[dest_key] = merged_df[dest_key].astype(str).str.strip()
        for col in numeric_cols:
            if col in merged_df.columns:
                merged_df[col] = pd.to_numeric(merged_df[col], errors='coerce')

        # --- DATE FORMAT FIX FOR ADVANCES ---
        # --- DATE FORMAT FIX FOR ADVANCES (ROBUST CASE-INSENSITIVE) ---
        target_date_cols = ['ORDER DATE', 'LAST BILL DATE']
        for col in merged_df.columns:
            if str(col).strip().upper() in target_date_cols:
                # Force conversion to datetime so xlsxwriter can apply format
                merged_df[col] = pd.to_datetime(merged_df[col], errors='coerce', dayfirst=True)
                # If still failing, try generic parser
                if merged_df[col].isna().all():
                     merged_df[col] = pd.to_datetime(merged_df[col], errors='coerce')
              
        output_advances_df = merged_df.reindex(columns=final_advances_columns)
        
        # Save combined workbook with formatting using xlsxwriter inline
        processed_filename = f"{uuid.uuid4()}_advances_sales_combined.xlsx"
        processed_filepath = os.path.join(UPLOAD_FOLDER, processed_filename)
        
        try:
            with pd.ExcelWriter(processed_filepath, engine='xlsxwriter', date_format='dd-mm-yyyy', datetime_format='dd-mm-yyyy') as writer:
                sales_df.to_excel(writer, sheet_name='Sales', index=False)
                output_advances_df.to_excel(writer, sheet_name='Advances', index=False)
                
                workbook = writer.book
                header_fmt = workbook.add_format({'bold': True, 'bg_color': '#DCE6F1', 'border': 1})
                date_fmt = workbook.add_format({'num_format': 'dd-mm-yyyy'})
                num_fmt = workbook.add_format({'num_format': 'General'})
                black_fill = workbook.add_format({'pattern': 1, 'bg_color': '#000000', 'font_color': '#FFFFFF'})

                # Helper to format a sheet
                def format_sheet(sheet_name, df):
                    ws = writer.sheets[sheet_name]
                    for col_num, value in enumerate(df.columns.values):
                        ws.write(0, col_num, value, header_fmt)
                    
                    for idx, col_name in enumerate(df.columns):
                        series = df[col_name]
                        is_empty = series.isna().all() or (series.astype(str).str.strip() == '').all()
                        
                        if is_empty:
                            ws.set_column(idx, idx, 10, black_fill)
                            continue
                        
                        col_width = max(len(str(col_name)), 10)
                        
                        col_upper = str(col_name).upper()
                        # Strict Date Checks
                        if 'ORDER DATE' in col_upper or 'LAST BILL DATE' in col_upper or 'BILLDATE' in col_upper:
                             ws.set_column(idx, idx, 15, date_fmt)
                        elif pd.api.types.is_datetime64_any_dtype(series):
                             ws.set_column(idx, idx, 15, date_fmt)
                        # Numeric Check
                        elif pd.api.types.is_numeric_dtype(series):
                             ws.set_column(idx, idx, 12, num_fmt)
                        # Text / Fallback
                        else:
                            if 'DATE' in col_upper:
                                ws.set_column(idx, idx, 15, date_fmt)
                            else:
                                ws.set_column(idx, idx, col_width)

                format_sheet('Sales', sales_df)
                format_sheet('Advances', output_advances_df)
                
            session['processed_advances_filepath'] = processed_filepath
            logger.info(f"Saved optimized combined workbook to {processed_filepath}")
            
        except Exception as e:
            logger.exception(f"Error saving/formatting Advances workbook: {e}")

        # Return file to client
        with open(processed_filepath, 'rb') as f:
            data = f.read()
        output_buffer = io.BytesIO(data)
        output_buffer.seek(0)
        print("Advances & Sales processed (with value paste). Sending 2-sheet Excel download.")
        return send_file(
            output_buffer,
            as_attachment=True,
            download_name="Processed_Advances_Consolidated.xlsx",
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
    except Exception as e:
        print(f"Error processing advances: {e}")
        return jsonify({"error": f"An error occurred: {e}"}), 500

# --- 9. BANKING PROCESSING (FINAL) ---

def process_amex_file(df, rule):
    """
    Applies the specific processing rules for an AMEX file.
    This is a special-case processor.
    """
    mappings = json.loads(rule.mappings)
    mappings_upper = {k.upper(): v.upper() for k, v in mappings.items()}
    
    # Define the correct uppercase column names
    # This logic is now "no-nonsense" and FORCES the mapping.
    COL_TRANS_DATE = mappings_upper.get("TRANSACTION DATE", "SUBMISSION DATE").upper()
    COL_CREDIT_DATE = mappings_upper.get("BANK CREDIT DATE", "SETTLEMENT DATE").upper()
    COL_SAP_CODE = "STORE CODE" # HARD-CODED FIX
    COL_AMOUNT = mappings_upper.get("AMOUNT", "SUBMISSION AMOUNT").upper()
    COL_TRANS_AMOUNT = mappings_upper.get("TRANSACTION AMOUNT", "SETTLEMENT AMOUNT").upper()
    COL_BANK_CHARGES = mappings_upper.get("BANK CHARGES", "MERCHANT SERVICE FEE").upper()
    COL_GST = mappings_upper.get("GST", "TAX AMOUNT").upper()
    COL_MID = mappings_upper.get("MID", "SUBMITTING MERCHANT NUMBER").upper()

    # Check if Store Code exists in dataframe to avoid errors
    sap_code_val = df[COL_SAP_CODE].astype(str) if COL_SAP_CODE in df.columns else pd.NA

    data_map = {
        'Bank Name': mappings.get('Bank Name', 'Amex'),
        'Mode': mappings.get('Mode', 'Card'),
        # --- FORCE DATE FORMAT DD-MM-YYYY ---
        'Transaction Date': pd.to_datetime(df[COL_TRANS_DATE], errors='coerce') if COL_TRANS_DATE in df.columns else pd.NA,
        'Bank Credit Date': pd.to_datetime(df[COL_CREDIT_DATE], errors='coerce') if COL_CREDIT_DATE in df.columns else pd.NA,
        ' SAP Code': sap_code_val,
        'Amount': df[COL_AMOUNT] if COL_AMOUNT in df.columns else pd.NA,
        'Transaction Amount': df[COL_TRANS_AMOUNT] if COL_TRANS_AMOUNT in df.columns else pd.NA,
        'Bank Charges': df[COL_BANK_CHARGES] if COL_BANK_CHARGES in df.columns else pd.NA,
        'GST': df[COL_GST] if COL_GST in df.columns else pd.NA,
        'MID': df[COL_MID] if COL_MID in df.columns else pd.NA
    }
    output_df = pd.DataFrame(data_map)
    
    # Keep dates as datetime objects; post_process_workbook will enforce DD-MM-YYYY
    if 'Transaction Date' in output_df.columns:
        output_df['Transaction Date'] = pd.to_datetime(output_df['Transaction Date'], errors='coerce')
    if 'Bank Credit Date' in output_df.columns:
        output_df['Bank Credit Date'] = pd.to_datetime(output_df['Bank Credit Date'], errors='coerce')

    # --- HARD-CODED "BP" REMOVAL FOR AMEX ---
    if ' SAP Code' in output_df.columns:
        output_df[' SAP Code'] = output_df[' SAP Code'].astype(str).str.replace('BP', '', case=False)
    
    return output_df

def process_generic_bank_file(df, rule):
    """
    Applies generic mapping rules for any bank.
    """
    final_bank_columns = get_output_columns('bank_output_columns')
    mappings = json.loads(rule.mappings)
    
    rename_map = {}
    for final_col in final_bank_columns:
        raw_col_name = mappings.get(final_col, final_col).upper()
        if raw_col_name in df.columns:
            rename_map[raw_col_name] = final_col
    df_renamed = df.rename(columns=rename_map)
    
    # --- THIS IS THE FIX ---
    # After renaming, we remove any duplicates that were created
    df_renamed = df_renamed.loc[:, ~df_renamed.columns.duplicated(keep='first')]
    # --- END OF FIX ---
    
    output_df = df_renamed.reindex(columns=final_bank_columns)
    
    output_df['Bank Name'] = mappings.get('Bank Name', rule.bank_name)
    output_df['Mode'] = mappings.get('Mode', 'Card')
    
    # --- FORCE DATE FORMAT DD-MM-YYYY ---
    if 'Transaction Date' in output_df.columns:
        output_df['Transaction Date'] = pd.to_datetime(output_df['Transaction Date'], errors='coerce')
    if 'Bank Credit Date' in output_df.columns:
        output_df['Bank Credit Date'] = pd.to_datetime(output_df['Bank Credit Date'], errors='coerce')

    # --- HARD-CODED "BP" REMOVAL FOR ALL BANKS ---
    sap_col = next((col for col in output_df.columns if 'SAP CODE' in col.upper()), None)
    if sap_col:
        output_df[sap_col] = output_df[sap_col].astype(str).str.replace('BP', '', case=False).str.strip()
            
    return output_df

BANK_PROCESSORS = {
    'Amex': process_amex_file
}

@app.route('/process-banking', methods=['POST'])
@login_required
def process_banking():
    all_processed_dfs = [] 
    final_bank_columns = get_output_columns('bank_output_columns')

    try:
        logger, log_path = start_process_logger('process_banking')
        logger.info('Received banking process request')
        for bank_name in request.form.getlist('bank_name'):
            
            rule = db.session.execute(db.select(BankRule).filter_by(bank_name=bank_name)).scalar_one_or_none()
            if not rule:
                print(f"Warning: No rule found for bank '{bank_name}'. Skipping.")
                continue
                
            print(f"Processing file for: {bank_name}")
            
            file = request.files.get(f'file_{bank_name}')
            from_date = request.form.get(f'date_from_{bank_name}')
            to_date = request.form.get(f'date_to_{bank_name}')

            if file:
                df = load_file_smartly(file, rule.sheet_name, rule.start_row)
                df.columns = df.columns.str.strip().str.upper()
                
                # --- THIS IS THE FIX for the 'Axis' (duplicate labels) bug ---
                df = df.loc[:, ~df.columns.duplicated(keep='first')]
                # --- END OF FIX ---
                
                mappings = json.loads(rule.mappings)
                credit_date_col = mappings.get('Bank Credit Date', 'Bank Credit Date').upper()
                
                if credit_date_col in df.columns:
                    df[credit_date_col] = pd.to_datetime(df[credit_date_col], errors='coerce')
                    if from_date and to_date:
                        try:
                            # --- UPDATED: Parse DD-MM-YYYY from Flatpickr ---
                            from_date_dt = pd.to_datetime(from_date, format='%d-%m-%Y', errors='coerce')
                            to_date_dt = pd.to_datetime(to_date, format='%d-%m-%Y', errors='coerce')
                            # --- END UPDATE ---
                            
                            if pd.notna(from_date_dt) and pd.notna(to_date_dt):
                                df = df[
                                    (df[credit_date_col] >= from_date_dt) &
                                    (df[credit_date_col] <= to_date_dt)
                                ]
                        except Exception as e:
                            print(f"Error during date filter for {bank_name}: {e}")
                
                if df.empty:
                    print(f"No data after date filter for {bank_name}.")
                    continue
                
                processor_function = BANK_PROCESSORS.get(bank_name, process_generic_bank_file)
                processed_df = processor_function(df, rule)
                
                # --- THIS IS THE FINAL FIX ---
                # We append the dataframe directly. NO REINDEX.
                # The processor functions are now responsible for their own columns.
                all_processed_dfs.append(processed_df)

        if not all_processed_dfs:
            return jsonify({"error": "No files were processed. Check rules or date ranges."}), 400

        master_df = pd.concat(all_processed_dfs, ignore_index=True)
        output_df = master_df.reindex(columns=final_bank_columns)
        
        # --- DATE FORMAT: ensure datetime dtype for date columns so post-processing can format cells ---
        for col in ['Transaction Date', 'Bank Credit Date']:
            if col in output_df.columns:
                output_df[col] = pd.to_datetime(output_df[col], errors='coerce')

        # Save as Excel so we can enforce formatting
        # Save using optimized helper
        processed_filename = f"{uuid.uuid4()}_banking.xlsx"
        processed_filepath = os.path.join(UPLOAD_FOLDER, processed_filename)
        
        success = save_with_formatting(output_df, processed_filepath, sheet_name='Banking')
        logger.info(f"Saved banking workbook to {processed_filepath} (Success={success})")

        # Return Excel file
        with open(processed_filepath, 'rb') as f:
            data = f.read()
        output_buffer = io.BytesIO(data)
        output_buffer.seek(0)
        print("Banking files processed successfully. Sending Excel download.")
        return send_file(
            output_buffer,
            as_attachment=True,
            download_name="Processed_Collection.xlsx",
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )

    except Exception as e:
        print(f"Error processing banking: {e}")
        return jsonify({"error": f"An error occurred: {e}"}), 500


# --- 10. ADMIN PORTAL ROUTES (FINAL) ---
@app.route('/admin')
@login_required
def admin_portal():
    if not current_user.is_admin:
        abort(403) 
    
    active_tab = request.args.get('tab', None)
    banks = db.session.execute(db.select(BankRule).order_by(BankRule.bank_name)).scalars().all()
    # prompts removed
    pending_users = db.session.execute(db.select(User).filter_by(is_approved=False, is_admin=False).order_by(User.name)).scalars().all()
    approved_users = db.session.execute(db.select(User).filter_by(is_approved=True, is_admin=False).order_by(User.name)).scalars().all()
    
    search_categories = db.session.execute(db.select(SearchCategoryRule).order_by(SearchCategoryRule.category_name)).scalars().all()
    search_modes = db.session.execute(db.select(SearchPaymentModeRule).order_by(SearchPaymentModeRule.mode_name)).scalars().all()
    search_file = db.session.execute(db.select(SearchFile)).scalar_one_or_none()

    output_cols_data = {
        'sales': {'str': get_output_columns_str_with_letters('sales_output_columns'), 'json': json.dumps(get_output_columns('sales_output_columns'))},
        'advances': {'str': get_output_columns_str_with_letters('advances_output_columns'), 'json': json.dumps(get_output_columns('advances_output_columns'))},
        'banking': {'str': get_output_columns_str_with_letters('bank_output_columns'), 'json': json.dumps(get_output_columns('bank_output_columns'))}
    }
    
    def serialize_rule(rule):
        if not rule: return {}
        data = {col.name: getattr(rule, col.name) for col in rule.__table__.columns}
        if 'mappings' in data and data['mappings']:
            data['mappings'] = json.loads(data['mappings']) 
        return data

    sales_rule = db.session.get(SalesRule, 1)
    advance_rule = db.session.get(AdvanceRule, 1)

    return render_template(
        'admin.html',
        title='Admin Portal',
        banks=banks,
        # prompts removed
        search_categories=search_categories, # Pass categories
        search_modes=search_modes, # Pass modes
        search_file=search_file, # Pass file
        banks_json=json.dumps([serialize_rule(b) for b in banks]),
        sales_rule_json=json.dumps(serialize_rule(sales_rule)),
        advance_rule_json=json.dumps(serialize_rule(advance_rule)),
        output_cols=output_cols_data,
        pending_users=pending_users,
        approved_users=approved_users,
        active_tab=active_tab
    )

@app.route('/admin/save_output_columns/<type>', methods=['POST'])
@login_required
def save_output_columns(type):
    if not current_user.is_admin: abort(403)
    active_tab = request.form.get('active_tab', 'Sales')
    key_map = {
        'sales': 'sales_output_columns',
        'advances': 'advances_output_columns',
        'banking': 'bank_output_columns'
    }
    key = key_map.get(type)
    if not key:
        flash('Invalid output column type.', 'error')
        return redirect(url_for('admin_portal', tab=active_tab))
    cols_str = request.form.get(f'output_columns_{type}', '')

    cleaned_lines = []
    for line in cols_str.split('\n'):
        line = line.strip()
        if not line: continue
        if ": " in line:
            parts = line.split(": ", 1)
            if parts[0].isalpha() and parts[0].isupper():
                cleaned_lines.append(parts[1].strip())
            else:
                cleaned_lines.append(line)
        else:
            cleaned_lines.append(line)
    cleaned_cols_str = "\n".join(cleaned_lines)

    setting = db.session.execute(db.select(Setting).filter_by(key=key)).scalar_one_or_none()
    if not setting:
        setting = Setting(key=key)
        db.session.add(setting)
    setting.value = cleaned_cols_str
    db.session.commit()
    
    flash(f'{type.capitalize()} output columns saved!', 'success')
    return redirect(url_for('admin_portal', tab=active_tab))

@app.route('/admin/save_sales_rule', methods=['POST'])
@login_required
def save_sales_rule():
    if not current_user.is_admin: abort(403)
    rule = db.session.get(SalesRule, 1)
    if not rule:
        rule = SalesRule(id=1)
        db.session.add(rule)
        
    mappings = {}
    output_cols = get_output_columns('sales_output_columns')
    for col in output_cols:
        map_val = request.form.get(f'map_{col}')
        if map_val: mappings[col] = map_val
            
    rule.start_row = int(request.form.get('start_row', 6))
    rule.sheet_name = request.form.get('sheet_name', '')
    rule.mappings = json.dumps(mappings)
    rule.bp_remove_cols = request.form.get('bp_remove_cols', '')
    rule.prefix_remove_col = request.form.get('prefix_remove_col', '')
    rule.prefix_remove_values = request.form.get('prefix_remove_values', '')
    rule.copy_col_source = request.form.get('copy_col_source', '')
    rule.copy_col_dest = request.form.get('copy_col_dest', '')
    
    db.session.commit()
    flash('Sales rules updated successfully!', 'success')
    return redirect(url_for('admin_portal', tab='Sales'))

@app.route('/admin/save_advance_rule', methods=['POST'])
@login_required
def save_advance_rule():
    if not current_user.is_admin: abort(403)
    rule = db.session.get(AdvanceRule, 1)
    if not rule:
        rule = AdvanceRule(id=1)
        db.session.add(rule)
        
    mappings = {}
    output_cols = get_output_columns('advances_output_columns')
    for col in output_cols:
        map_val = request.form.get(f'map_{col}')
        if map_val: mappings[col] = map_val
            
    rule.start_row = int(request.form.get('start_row', 2))
    rule.sheet_name = request.form.get('sheet_name', 'Sheet1')
    rule.mappings = json.dumps(mappings)
    rule.vlookup_source_col = request.form.get('vlookup_source_col', '')
    rule.vlookup_sales_col = request.form.get('vlookup_sales_col', '')
    rule.vlookup_dest_col = request.form.get('vlookup_dest_col', '')
    rule.vlookup_value_col = request.form.get('vlookup_value_col', '')
    
    db.session.commit()
    flash('Advances rules updated successfully!', 'success')
    return redirect(url_for('admin_portal', tab='Advances'))

@app.route('/admin/save_bank', methods=['POST'])
@login_required
def save_bank():
    if not current_user.is_admin: abort(403)
    
    bank_id = request.form.get('bank_id')
    bank_name = request.form.get('bank_name')
    start_row = int(request.form.get('start_row', 2))
    sheet_name = request.form.get('sheet_name', 'Sheet1')
    
    mappings = {}
    output_cols = get_output_columns('bank_output_columns')
    for col in output_cols:
        map_val = request.form.get(f'map_{col}')
        if map_val: mappings[col] = map_val
            
    mappings['Bank Name'] = request.form.get(f'map_Bank Name', bank_name)
    mappings['Mode'] = request.form.get(f'map_Mode', 'Card')

    if bank_id == 'new':
        existing = db.session.execute(db.select(BankRule).filter_by(bank_name=bank_name)).scalar_one_or_none()
        if existing:
            flash(f"Error: Bank name '{bank_name}' already exists.", 'danger')
            return redirect(url_for('admin_portal', tab='Banking'))
            
        new_bank = BankRule(
            bank_name=bank_name,
            start_row=start_row,
            sheet_name=sheet_name,
            mappings=json.dumps(mappings)
        )
        db.session.add(new_bank)
        flash(f'Bank rule for {bank_name} created!', 'success')
        
    else: 
        bank = db.session.get(BankRule, int(bank_id))
        if not bank:
            flash('Bank rule not found.', 'danger')
            return redirect(url_for('admin_portal', tab='Banking'))
        
        bank.bank_name = bank_name
        bank.start_row = start_row
        bank.sheet_name = sheet_name
        bank.mappings = json.dumps(mappings)
        flash(f'Bank rule for {bank_name} updated!', 'success')
        
    db.session.commit()
    return redirect(url_for('admin_portal', tab='Banking'))

@app.route('/admin/delete_bank/<int:bank_id>')
@login_required
def delete_bank(bank_id):
    if not current_user.is_admin: abort(403)
    bank = db.session.get(BankRule, bank_id)
    if bank:
        db.session.delete(bank)
        db.session.commit()
        flash(f'Bank rule for {bank.bank_name} deleted.', 'success')
    else:
        flash('Bank rule not found.', 'danger')
    return redirect(url_for('admin_portal', tab='Banking'))

# --- 11. USER MANAGEMENT ROUTES (FINAL) ---
@app.route('/admin/approve_user/<int:user_id>')
@login_required
def approve_user(user_id):
    if not current_user.is_admin: abort(403)
    user = db.session.get(User, user_id)
    if user:
        user.is_approved = True
        db.session.commit()
        flash(f'User {user.name} has been approved.', 'success')
    else:
        flash('User not found.', 'danger')
    return redirect(url_for('admin_portal', tab='UserManagement'))

@app.route('/admin/delete_user/<int:user_id>')
@login_required
def delete_user(user_id):
    if not current_user.is_admin: abort(403) 
    user = db.session.get(User, user_id)
    if user and not user.is_admin:
        db.session.delete(user)
        db.session.commit()
        flash(f'User {user.name} has been deleted.', 'success')
    elif user.is_admin:
        flash('Cannot delete the admin account.', 'danger')
    else:
        flash('User not found.', 'danger')
    return redirect(url_for('admin_portal', tab='UserManagement'))

@app.route('/admin/reset_password/<int:user_id>', methods=['GET', 'POST'])
@login_required
def reset_password(user_id):
    if not current_user.is_admin: abort(403) 
    user = db.session.get(User, user_id)
    if not user:
        flash('User not found.', 'danger')
        return redirect(url_for('admin_portal', tab='UserManagement'))
    form = ResetPasswordForm()
    if form.validate_on_submit():
        user.set_password(form.password.data)
        db.session.commit()
        flash(f"Password for {user.name} has been reset.", 'success')
        return redirect(url_for('admin_portal', tab='UserManagement'))
    return render_template('reset_password.html', title='Reset Password', form=form, user=user)

@app.route('/admin/edit_user/<int:user_id>', methods=['GET', 'POST'])
@login_required
def edit_user(user_id):
    if not current_user.is_admin: abort(403)
    user = db.session.get(User, user_id)
    if not user:
        flash('User not found.', 'danger')
        return redirect(url_for('admin_portal', tab='UserManagement'))
    
    form = EditUserForm(obj=user)
    if form.validate_on_submit():
        # Optional: Check for email uniqueness if email changed
        if form.email.data != user.email:
             existing_user = db.session.execute(db.select(User).filter_by(email=form.email.data)).scalar_one_or_none()
             if existing_user:
                 flash('Email already exists.', 'danger')
                 return render_template('edit_user.html', form=form, user=user)

        user.email = form.email.data
        user.name = form.name.data
        user.age = form.age.data
        user.department = form.department.data
        user.reporting_manager = form.reporting_manager.data
        user.is_admin = form.is_admin.data
        db.session.commit()
        flash(f'User {user.name} updated.', 'success')
        return redirect(url_for('admin_portal', tab='UserManagement'))
    
    return render_template('edit_user.html', form=form, user=user)


# --- 12. DEBUG & LOG ROUTES (USER-FRIENDLY) ---
@app.route('/last-process-log')
@login_required
def last_process_log():
    """Display the last process log in a user-friendly format."""
    last_log_path = session.get('last_process_log')
    log_content = ""
    error_summary = ""
    
    if last_log_path and os.path.exists(last_log_path):
        try:
            with open(last_log_path, 'r', encoding='utf-8') as f:
                log_content = f.read()
            # Extract error summary: look for ERROR, Exception, or error messages
            lines = log_content.split('\n')
            error_lines = [l for l in lines if 'error' in l.lower() or 'exception' in l.lower()]
            if error_lines:
                error_summary = '\n'.join(error_lines[-5:])  # Last 5 error lines
        except Exception as e:
            log_content = f"Could not read log file: {str(e)}"
    else:
        log_content = "No process log available yet. Run a process first."
    
    return render_template('last_process_log.html', 
                          log_content=log_content, 
                          error_summary=error_summary,
                          log_path=last_log_path)

@app.route('/api/last-process-log-json')
@login_required
def last_process_log_json():
    """Return last process log as JSON for AJAX calls."""
    last_log_path = session.get('last_process_log')
    log_content = ""
    error_summary = ""
    has_errors = False
    
    if last_log_path and os.path.exists(last_log_path):
        try:
            with open(last_log_path, 'r', encoding='utf-8') as f:
                log_content = f.read()
            lines = log_content.split('\n')
            error_lines = [l for l in lines if 'error' in l.lower() or 'exception' in l.lower()]
            if error_lines:
                error_summary = '\n'.join(error_lines)
                has_errors = True
        except Exception as e:
            log_content = f"Could not read log file: {str(e)}"
            has_errors = True
    
    return jsonify({
        "log_path": last_log_path,
        "log_content": log_content,
        "error_summary": error_summary,
        "has_errors": has_errors,
        "available": bool(last_log_path and os.path.exists(last_log_path))
    })


# --- 13. DATABASE DEFAULT DATA (FINAL) ---
def create_default_data():
    """
    Called on first run to populate the database
    with all our finalized rules.
    """
    with app.app_context():
        if not db.session.execute(db.select(User).filter_by(email='admin@tool.com')).scalar_one_or_none():
            admin = User(email='admin@tool.com', name='Admin User', age=99, department='IT', reporting_manager='System', is_admin=True, is_approved=True)
            admin.set_password('admin123')
            db.session.add(admin)

        if not db.session.execute(db.select(Setting).filter_by(key='sales_output_columns')).scalar_one_or_none():
            sales_cols = Setting(key='sales_output_columns', value=('AlternateStoreCode\nRegionName\nStoreName\nStoreCode\nBillDate\nQuantity\nDiscount\nDiscountPercentage\nBaseValue\nSGST\nCGST\nIGST\nUTGST\nTax\nCash\nCard\nCreditCardType\nCoupon\nCredit\nInsuranceCredit\nCashAdvance\nCreditCardAdvance\nAdvancedAmount\nGiftVoucher\nCCNUsed\nCCNIssued\nPointsAllocated\nPointsRedeemed\nCheque\nPrepaidCard\nOtherPayments\nAmount\nMRPTOTAL\nPinCode\nWSDN\nAccentiv\nAM\nCA\nCards\nMA\nMO\nOnline Payment\nPaytm\nPayTM DQR\nPayU Payment\nPP\nQC Wallet\nVC\nVouchagram\nUPI\nCredit Card - Airport Stores\nUPI - Airport Stores\nCash - Airport Stores'))
            db.session.add(sales_cols)

        if not db.session.execute(db.select(Setting).filter_by(key='advances_output_columns')).scalar_one_or_none():
            adv_cols = Setting(key='advances_output_columns', value=('Region\nStore\nStore Code\nOrder Date\nOrder Number\nLast Bill Date\nBill Number\nCustomer Code\nCustomer Name\nNo Of Items\nTotal Quantity\nApproximate Value\nAdvance Amount\nCash\nCredit Card\nCoupon\nCredit\nGV\nCCN\nPoints\nCheque\nPrepaid Card\nTemp Credit\nCash Advance\nCredit Card Advance\nOtherPayments\nPayment Mode\nBalance Amount\nStatus'))
            db.session.add(adv_cols)

        if not db.session.execute(db.select(Setting).filter_by(key='bank_output_columns')).scalar_one_or_none():
            bank_cols = Setting(key='bank_output_columns', value=('Bank Name\nMode\nTransaction Date\nBank Credit Date\n SAP Code\nAmount\nTransaction Amount\nBank Charges\nGST\nMID'))
            db.session.add(bank_cols)

        if not db.session.get(SalesRule, 1):
            sales_rule = SalesRule(id=1, start_row=6, sheet_name='SalesReportAbstract', mappings=json.dumps({"AlternateStoreCode": "AlternateStoreCode", "StoreName": "StoreName"}), bp_remove_cols='StoreCode,AlternateStoreCode', prefix_remove_col='StoreCode', prefix_remove_values='97,98', copy_col_source='AlternateStoreCode', copy_col_dest='StoreCode')
            db.session.add(sales_rule)
        
        if not db.session.get(AdvanceRule, 1):
            adv_rule = AdvanceRule(id=1, start_row=2, sheet_name='Sheet', mappings=json.dumps({"Store": "Store"}), vlookup_source_col = 'Store', vlookup_sales_col = 'StoreName', vlookup_dest_col = 'Store Code', vlookup_value_col = 'StoreCode')
            db.session.add(adv_rule)
        
        # --- DEFAULT SEARCH RULES ---
        if not db.session.execute(db.select(SearchCategoryRule).filter_by(category_name='Sales')).scalar_one_or_none():
            db.session.add(SearchCategoryRule(category_name='Sales', sheet_name='Sheet1')) 
        if not db.session.execute(db.select(SearchCategoryRule).filter_by(category_name='Advances')).scalar_one_or_none():
             db.session.add(SearchCategoryRule(category_name='Advances', sheet_name='Sheet1'))
        if not db.session.execute(db.select(SearchCategoryRule).filter_by(category_name='Banking')).scalar_one_or_none():
             db.session.add(SearchCategoryRule(category_name='Banking', sheet_name='Collection'))

        if not db.session.execute(db.select(SearchPaymentModeRule).filter_by(mode_name='Cash')).scalar_one_or_none():
            db.session.add(SearchPaymentModeRule(mode_name='Cash', columns='Cash,Cash Amount,HB-Cash,MR-Cash,CO-Cash,Ad-Cash'))
        if not db.session.execute(db.select(SearchPaymentModeRule).filter_by(mode_name='Card')).scalar_one_or_none():
            db.session.add(SearchPaymentModeRule(mode_name='Card', columns='Card,Credit Card,HB-Card,MR-Card,CO-Card,Ad-Card'))
        if not db.session.execute(db.select(SearchPaymentModeRule).filter_by(mode_name='Online')).scalar_one_or_none():
            db.session.add(SearchPaymentModeRule(mode_name='Online', columns='Online,Online Payment,Paytm,HB-Online,MR-Online,CO-Online,Ad-Online'))
        
        # --- AMEX RULE: Managed in Admin Portal ---
        # Amex rule configuration is managed via Admin Portal.
        # No auto-repair necessary - user has full control.
        
# --- NEW: STEP 4 LOGIC (Process Final) ---

# STEP A: Process Combine MIS Files Only
@app.route('/process-combine-only', methods=['POST'])
@login_required
def process_combine_only():
    """
    Step A: Process Combine MIS Files (NEW SIMPLE LOGIC)
    - Multi-file support
    - Target specific sheet starting with "MIS Working"
    - Start from 3rd row (header=2)
    - Clean merge
    """
    # Start logger
    logger, log_path = start_process_logger('process_combine_only')
    
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
                            logger.info(f"File '{filename}': Found sheet '{target_sheet}'")
                        else:
                            logger.warning(f"File '{filename}': No sheet starting with 'MIS Working' found. Skipping.")
                            continue 
                            
                    except Exception as e:
                        logger.error(f"Error inspecting Excel file {filename}: {e}")
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
                    logger.warning(f"Skipping unsupported file: {filename}")
                    continue

                # 3. Process the DataFrame if loaded
                if df is not None and not df.empty:
                    # Clean columns: Strip whitespace
                    df.columns = df.columns.astype(str).str.strip()
                    # Clean rows: Drop empty rows
                    df.dropna(how='all', inplace=True)
                    
                    if not df.empty:
                        combined_data_list.append(df)
                        logger.info(f"File '{filename}': Added {len(df)} rows.")

            except Exception as e:
                logger.error(f"Error processing file {filename}: {e}")
                return jsonify({"error": f"Failed to process {filename}: {str(e)}"}), 400

        # --- MERGE ---
        if not combined_data_list:
            return jsonify({"error": "No matching data found. Ensure files have a sheet starting with 'MIS Working'."}), 400

        # Concatenate all
        master_combine_df = pd.concat(combined_data_list, ignore_index=True)
        # Final Clean
        master_combine_df.dropna(how='all', inplace=True)
        
        # FIX: Deduplicate columns to prevent errors in loop
        master_combine_df = master_combine_df.loc[:, ~master_combine_df.columns.duplicated()]

        # --- NEW REQUIREMENT: COLUMN LIMIT (A-CJ) [Index 0-87] ---
        MAX_COLS = 86
        if len(master_combine_df.columns) > MAX_COLS:
            master_combine_df = master_combine_df.iloc[:, :MAX_COLS]
        
        # --- NEW REQUIREMENT: DATA FORMATTING ---
        for col in master_combine_df.columns:
            # 1. Check for Date
            if isinstance(col, str) and 'DATE' in col.upper():
                series = master_combine_df[col]
                # Try to parse as numeric first to catch Excel serial dates
                numeric_series = pd.to_numeric(series, errors='coerce')
                
                # Check for likely Excel serial dates (roughly years 1980-2100)
                # 29221 = 1980-01-01, 73050 = 2100-01-01
                mask_serial = numeric_series.notna() & (numeric_series > 25000) & (numeric_series < 80000)
                
                # Default parse as strings (dayfirst=True for DD-MM-YYYY)
                date_series = pd.to_datetime(series, errors='coerce', dayfirst=True)
                
                # If we found serial dates, overwrite those entries
                if mask_serial.any():
                    try:
                        # Excel epoch is usually 1899-12-30
                        serial_dates = pd.to_datetime(numeric_series[mask_serial], unit='D', origin='1899-12-30')
                        date_series.update(serial_dates)
                        logger.info(f"Col '{col}': Converted {mask_serial.sum()} Excel serial dates")
                    except Exception as e:
                        logger.warning(f"Col '{col}': Failed to convert serial dates: {e}")
                
                master_combine_df[col] = date_series
            
            # 2. Check for Numeric logic
            elif isinstance(col, str):
                try:
                    master_combine_df[col] = pd.to_numeric(master_combine_df[col], errors='ignore')
                except Exception:
                    pass
                
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
        logger.exception(f"Error in process_combine_only: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500



# --- TEST-ONLY ENDPOINTS (no auth) ---
@app.route('/_test/process-combine-only', methods=['POST'])
def _test_process_combine_only():
    # Only active when in debug mode
    if not app.debug:
        return jsonify({"error": "Not available"}), 403
    try:
        combine_files = request.files.getlist('combine_mis')
        if not combine_files:
            return jsonify({"error": "Please select Combine MIS file(s)."}), 400
        combined_data_list = []
        for file in combine_files:
            df = load_file_smartly(file, "MIS Working", 3)
            combined_data_list.append(df)
        if not combined_data_list:
            return jsonify({"error": "No data found in Combine MIS files."}), 400
        master_combine_df = pd.concat(combined_data_list, ignore_index=True)
        master_combine_df.columns = master_combine_df.columns.astype(str).str.strip()

        # minimal post-processing: ensure CK exists
        df = master_combine_df.copy()
        df.columns = df.columns.astype(str).str.strip()
        # try basic detection
        combine_store_col = find_column_by_keywords(df, ['STORE', 'CODE']) or find_column_by_keywords(df, ['STORE'])
        combine_date_col = find_column_by_keywords(df, ['DATE'])
        if combine_date_col and combine_date_col in df.columns:
            df[combine_date_col] = pd.to_datetime(df[combine_date_col], errors='coerce')
        if combine_store_col and combine_store_col in df.columns and combine_date_col and combine_date_col in df.columns:
            df['CK'] = df[combine_store_col].astype(str).str.strip() + '_' + df[combine_date_col].dt.strftime('%d-%m-%Y').fillna('')
        else:
            df['CK'] = ''

        processed_filename = f"{uuid.uuid4()}_processed_combine.xlsx"
        processed_filepath = os.path.join(UPLOAD_FOLDER, processed_filename)
        df.to_excel(processed_filepath, index=False, engine='openpyxl')
        session['processed_combine_filepath'] = processed_filepath
        # Post-process workbook formatting
        try:
            # post_process_workbook(processed_filepath, sheets=None, min_data_row=3, logger=logger)
            pass
        except Exception:
            pass
        with open(processed_filepath, 'rb') as f:
            data = f.read()
        return send_file(io.BytesIO(data), as_attachment=True, download_name='Processed_Combine_MIS.xlsx', mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@app.route('/_test/process-final-only', methods=['POST'])
def _test_process_final_only():
    # Simple passthrough test endpoint for Final MIS (no merging) — only in debug
    if not app.debug:
        return jsonify({"error": "Not available"}), 403
    try:
        final_mis_file = request.files.get('final_mis')
        if not final_mis_file:
            return jsonify({'error': 'Please provide final_mis file'}), 400
        # Save and post-process final file then return
        processed_final_name = f"{uuid.uuid4()}_processed_final.xlsx"
        processed_final_path = os.path.join(UPLOAD_FOLDER, processed_final_name)
        # simply copy incoming file to disk then post-process formatting
        final_mis_file.seek(0)
        with open(processed_final_path, 'wb') as out:
            out.write(final_mis_file.read())
        try:
            # post_process_workbook(processed_final_path, sheets=None, min_data_row=3, logger=None)
            pass
        except Exception:
            pass
        with open(processed_final_path, 'rb') as f:
            data = f.read()
        session['processed_final_filepath'] = processed_final_path
        return send_file(io.BytesIO(data), as_attachment=True, download_name='Processed_Final_MIS.xlsx', mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


# STEP B: Process Final MIS File Only
@app.route('/process-final-only', methods=['POST'])
@login_required
def process_final_only():
    """Process ONLY Final MIS file - Returns processed template without merging."""
    try:
        # This step can use the processed Combine MIS from Step A (session)
        # or accept Combine MIS files uploaded with this request.
        final_mis_file = request.files.get('final_mis')
        if not final_mis_file:
            return jsonify({"error": "Please select Final MIS file."}), 400

        master_combine_df = None
        if 'processed_combine_filepath' in session:
            processed_combine_path = session.get('processed_combine_filepath')
            if os.path.exists(processed_combine_path):
                master_combine_df = pd.read_excel(processed_combine_path, engine='openpyxl', dtype=str)
                master_combine_df.columns = master_combine_df.columns.astype(str).str.strip()
            else:
                # session path missing on disk; fallback to uploaded combine files
                master_combine_df = None

        if master_combine_df is None:
            # Accept combine files uploaded together with Step B
            combine_files = request.files.getlist('combine_mis')
            if not combine_files:
                return jsonify({"error": "Please run Step A first or upload Combine MIS file(s) here."}), 400
            combined_data_list = []
            for file in combine_files:
                try:
                    df = load_file_smartly(file, "MIS Working", 3)
                    combined_data_list.append(df)
                except Exception as e:
                    return jsonify({"error": f"Failed to load {file.filename}: {str(e)}"}), 400
            if not combined_data_list:
                return jsonify({"error": "No data found in provided Combine MIS files."}), 400
            master_combine_df = pd.concat(combined_data_list, ignore_index=True)
            master_combine_df.columns = master_combine_df.columns.astype(str).str.strip()


        # Read the uploaded Final MIS workbook (all sheets), but we will only modify the reconciliation sheet
        try:
            final_mis_file.seek(0)
            xls = pd.ExcelFile(final_mis_file)
            sheets = {}
            for name in xls.sheet_names:
                # Final MIS file: header is in row 3 (index 2), data starts from row 4 (index 3)
                df = pd.read_excel(xls, sheet_name=name, dtype=str, header=2)
                df.columns = df.columns.astype(str).str.strip()
                sheets[name] = df
        except Exception as e:
            return jsonify({"error": f"Could not read Final MIS workbook: {str(e)}"}), 400

        # Identify the target sheet
        preferred = "Reconciliation by Date by Store"
        if preferred in sheets:
            target_sheet = preferred
        else:
            # fallback: try to find by heuristics
            target_sheet = None
            for name, df_sheet in sheets.items():
                cols = [str(c).upper() for c in df_sheet.columns]
                if any('STORE' in c and 'CODE' in c for c in cols) and any('DATE' in c for c in cols):
                    target_sheet = name
                    break
            if not target_sheet:
                return jsonify({"error": f"Could not detect '{preferred}' sheet in Final MIS. Please ensure the sheet exists."}), 400

        # Load target sheet as dataframe
        final_df = sheets[target_sheet]
        final_df.columns = final_df.columns.astype(str).str.strip()

        # Standardize keys in master combine using heuristics (supporting variants)
        combine_store_col = find_column_by_keywords(master_combine_df, ['STORE', 'CODE']) or find_column_by_keywords(master_combine_df, ['STORE']) or 'Store Code'
        combine_date_col = find_column_by_keywords(master_combine_df, ['DATE']) or 'Date'

        # Standardize keys in final_df using heuristics
        final_store_col = find_column_by_keywords(final_df, ['STORE', 'CODE']) or find_column_by_keywords(final_df, ['STORE']) or 'Store Code'
        final_date_col = find_column_by_keywords(final_df, ['DATE']) or 'Date'

        # Verify columns exist
        if combine_store_col not in master_combine_df.columns:
            combine_store_col = 'Store Code' if 'Store Code' in master_combine_df.columns else None
        if combine_date_col not in master_combine_df.columns:
            combine_date_col = 'Date' if 'Date' in master_combine_df.columns else None
        if final_store_col not in final_df.columns:
            final_store_col = 'Store Code' if 'Store Code' in final_df.columns else None
        if final_date_col not in final_df.columns:
            final_date_col = 'Date' if 'Date' in final_df.columns else None

        if not combine_store_col or not combine_date_col or not final_store_col or not final_date_col:
            # Provide detailed error with available columns
            combine_cols = ', '.join([str(c)[:50] for c in master_combine_df.columns[:10]])
            final_cols = ', '.join([str(c)[:50] for c in final_df.columns[:10]])
            error_detail = f"Combine columns: [{combine_cols}...] | Final columns: [{final_cols}...]"
            return jsonify({
                "error": f"Could not identify Store Code and Date columns. {error_detail}"
            }), 400

        # Prepare master combine keys
        master_combine_df[combine_store_col] = master_combine_df[combine_store_col].astype(str).str.strip()
        # keep actual datetime for date column
        master_combine_df[combine_date_col] = pd.to_datetime(master_combine_df[combine_date_col], errors='coerce')
        # create string match key for joining
        master_combine_df['MatchKey'] = master_combine_df[combine_store_col].astype(str) + '_' + master_combine_df[combine_date_col].dt.strftime('%d-%m-%Y').fillna('')
        master_combine_dedup = master_combine_df.drop_duplicates(subset=['MatchKey'], keep='first')

        # Prepare final keys
        final_df[final_store_col] = final_df[final_store_col].astype(str).str.strip()
        # keep actual datetime for final date column
        final_df[final_date_col] = pd.to_datetime(final_df[final_date_col], errors='coerce')
        final_df['MatchKey'] = final_df[final_store_col].astype(str) + '_' + final_df[final_date_col].dt.strftime('%d-%m-%Y').fillna('')

        # Columns allowed to be updated in Final MIS (only these will be written from Combine)
        update_columns = [
            'HB-Card', 'HB-Cash', 'HB-Online',
            'MR-Card', 'MR-Cash', 'MR-Online',
            'CO-Card', 'CO-Cash', 'CO-Online-Paytm', 'CO-Online-Other', 'CO-CCN', 'CO-Bank Offer',
            'Remarks', 'Performa Invoice Number',
            'Ad-Card', 'Ad-Cash', 'Ad-Online - PayTm', 'Ad-Online - Other', 'Ad-CCN', 'Ad-Store Correction', 'Ad-Bank Offer'
        ]
        
        try:
            # Filter combine columns that exist and should be copied
            combine_cols_to_merge = ['MatchKey'] + [c for c in update_columns if c in master_combine_dedup.columns]
            
            # Merge: left join master combine into final_df for matching rows
            merged = pd.merge(final_df, master_combine_dedup[combine_cols_to_merge], on='MatchKey', how='left', suffixes=('', '_combine'))

            # Update columns from Combine data
            for col in update_columns:
                combine_col = f"{col}_combine"
                if combine_col in merged.columns:
                    # Copy non-null values from combine file
                    merged[col] = merged[combine_col].fillna(merged[col])
                    merged = merged.drop(columns=[combine_col])
                elif col not in merged.columns:
                    # Column doesn't exist in Final or Combine, create empty
                    merged[col] = ''

            # Remove MatchKey column (temporary column used for merging)
            if 'MatchKey' in merged.columns:
                merged = merged.drop(columns=['MatchKey'])

            # Build updated sheet (preserve original column order, excluding MatchKey)
            original_cols = [c for c in final_df.columns if c != 'MatchKey' and c in merged.columns]
            
            # Add any missing columns from merged that weren't in original final_df
            for col in merged.columns:
                if col not in original_cols and col not in ['MatchKey']:
                    original_cols.append(col)
            
            updated_sheet = merged[original_cols].copy()
            # Replace sheet in sheets dict
            sheets[target_sheet] = updated_sheet
        except Exception as merge_error:
            return jsonify({"error": f"Error during data merge: {str(merge_error)}"}), 400

        # Save the updated workbook to buffer and return
        # Save and Format using xlsxwriter inline (replacing openpyxl post-processing)
        processed_final_name = f"{uuid.uuid4()}_processed_final.xlsx"
        processed_final_path = os.path.join(UPLOAD_FOLDER, processed_final_name)
        
        try:
             with pd.ExcelWriter(processed_final_path, engine='xlsxwriter', date_format='dd-mm-yyyy', datetime_format='dd-mm-yyyy') as writer:
                workbook = writer.book
                # Formats
                header_fmt = workbook.add_format({'bold': True, 'bg_color': '#DCE6F1', 'border': 1})
                date_fmt = workbook.add_format({'num_format': 'dd-mm-yyyy'})
                black_fill = workbook.add_format({'pattern': 1, 'bg_color': '#000000', 'font_color': '#FFFFFF'})
                num_fmt = workbook.add_format({'num_format': 'General'})

                for name, df_sheet in sheets.items():
                    # Clean columns
                    df_sheet.columns = df_sheet.columns.astype(str)
                    
                    # --- CRITICAL FIX: INFER DATA TYPES FOR "VALUE PASTE" ---
                    # Since we loaded with dtype=str, strictly convert back where possible.
                    for col in df_sheet.columns:
                        # Skip ID-like columns that should remain text (optional heuristic)
                        if 'CODE' in col.upper() or 'ID' in col.upper() or 'GST' in col.upper() or 'NUMBER' in col.upper() and 'BILL' not in col.upper():
                             continue # Keep as text usually

                        # 1. Try Numeric (Float/Int)
                        # Remove common currency symbols if any
                        try:
                            # flexible numeric conversion
                            numeric_series = pd.to_numeric(df_sheet[col], errors='coerce')
                            # If significant portion is numeric, keep it
                            non_na = numeric_series.notna().sum()
                            total = len(df_sheet)
                            if total > 0 and (non_na / total) > 0.3: # heuristic threshold
                                df_sheet[col] = numeric_series
                        except:
                            pass

                        # 2. Try Date (Strict Name Check + Content)
                        if 'DATE' in col.upper():
                             df_sheet[col] = pd.to_datetime(df_sheet[col], errors='coerce', dayfirst=True)

                    df_sheet.to_excel(writer, sheet_name=name, index=False)
                    ws = writer.sheets[name]
                    
                    # Format Header
                    for col_num, value in enumerate(df_sheet.columns.values):
                        ws.write(0, col_num, value, header_fmt)
                        
                    # Format Body
                    for idx, col_name in enumerate(df_sheet.columns):
                        series = df_sheet[col_name]
                        # Check empty
                        is_empty = series.isna().all() or (series.astype(str).str.strip() == '').all()
                        if is_empty:
                             ws.set_column(idx, idx, 10, black_fill)
                             continue
                             
                        # Check dates
                        if pd.api.types.is_datetime64_any_dtype(series) or 'DATE' in str(col_name).upper():
                             ws.set_column(idx, idx, 15, date_fmt)
                        # Check numeric
                        elif pd.api.types.is_numeric_dtype(series):
                             ws.set_column(idx, idx, 12, num_fmt)
                        else:
                             ws.set_column(idx, idx, max(len(str(col_name)), 10))

             session['processed_final_filepath'] = processed_final_path
             
             # Read back to return
             with open(processed_final_path, 'rb') as f:
                 output_data = f.read()
             output_buffer = io.BytesIO(output_data)

        except Exception as e:
             print(f"Error saving/formatting Final MIS: {e}")
             return jsonify({"error": f"Error saving file: {e}"}), 500

        return send_file(
            io.BytesIO(output_buffer.getvalue()),
            as_attachment=True,
            download_name="Processed_Final_MIS.xlsx",
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        
    except Exception as e:
        print(f"Error in process_final_only: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500




@app.route('/process-individual-combine', methods=['POST'])
@login_required
def process_individual_combine():
    """Process a SINGLE Combine MIS file and update the Final MIS file."""
    try:
        combine_file = request.files.get('combine_mis')
        final_mis_file = request.files.get('final_mis')

        if not combine_file or not final_mis_file:
            return jsonify({"error": "Missing files. Please select both Combine MIS and Final MIS files."}), 400

        # --- Process 1: Load Single Combine MIS File ---
        try:
            df_combine = load_file_smartly(combine_file, "MIS Working", 3)
            print(f"DEBUG Individual: Loaded combine file {combine_file.filename}")
            print(f"DEBUG Individual: Combine columns: {list(df_combine.columns)}")
        except Exception as e:
            print(f"Error loading combine file {combine_file.filename}: {e}")
            return jsonify({"error": f"Failed to load 'MIS Working' from {combine_file.filename}: {str(e)}"}), 400

        df_combine.columns = df_combine.columns.astype(str).str.strip()
        
        # Find columns
        combine_store_col = next((c for c in df_combine.columns if isinstance(c, str) and 'STORE' in c.upper() and 'CODE' in c.upper()), None)
        combine_date_col = next((c for c in df_combine.columns if isinstance(c, str) and 'DATE' in c.upper()), None)
        
        if combine_store_col is None:
            combine_store_col = df_combine.columns[0] if len(df_combine.columns) > 0 else None
        if combine_date_col is None:
            combine_date_col = df_combine.columns[1] if len(df_combine.columns) > 1 else df_combine.columns[0]

        if not combine_store_col or not combine_date_col:
            return jsonify({"error": "Could not identify Store Code and Date columns in Combine MIS file."}), 400

        # Standardize values
        if combine_store_col in df_combine.columns:
            df_combine[combine_store_col] = df_combine[combine_store_col].astype(str).str.strip()
        if combine_date_col in df_combine.columns:
            df_combine[combine_date_col] = pd.to_datetime(df_combine[combine_date_col], errors='coerce')

        # --- Process 2: Load Final MIS ---
        try:
            final_df = load_file_smartly(final_mis_file, "Reconciliation by Date by Store", 1)
            print(f"DEBUG Individual: Loaded final MIS file")
            print(f"DEBUG Individual: Final columns: {list(final_df.columns)}")
        except Exception as e:
            return jsonify({"error": f"Could not load 'Reconciliation by Date by Store' sheet: {str(e)}"}), 400
        
        final_df.columns = final_df.columns.astype(str).str.strip()
        
        # Find columns in final
        final_store_col = next((c for c in final_df.columns if isinstance(c, str) and 'STORE' in c.upper() and 'CODE' in c.upper()), None)
        final_date_col = next((c for c in final_df.columns if isinstance(c, str) and 'DATE' in c.upper()), None)
        
        if final_store_col is None:
            final_store_col = final_df.columns[0] if len(final_df.columns) > 0 else None
        if final_date_col is None:
            final_date_col = final_df.columns[1] if len(final_df.columns) > 1 else final_df.columns[0]

        if not final_store_col or not final_date_col:
            return jsonify({"error": "Could not identify Store Code and Date columns in Final MIS file."}), 400

        # Standardize final values
        if final_store_col in final_df.columns:
            final_df[final_store_col] = final_df[final_store_col].astype(str).str.strip()
        if final_date_col in final_df.columns:
            final_df[final_date_col] = pd.to_datetime(final_df[final_date_col], errors='coerce')

        # --- Process 3: Merge and Update ---
        update_columns = [
            'HB-Card', 'HB-Cash', 'HB-Online',
            'MR-Card', 'MR-Cash', 'MR-Online',
            'CO-Card', 'CO-Cash', 'CO-Online-Paytm', 'CO-Online-Other', 'CO-CCN', 'CO-Bank Offer',
            'Remarks', 'Performa Invoice Number',
            'Ad-Card', 'Ad-Cash', 'Ad-Online - PayTm', 'Ad-Online - Other', 'Ad-CCN', 'Ad-Store Correction', 'Ad-Bank Offer'
        ]

        # Create match keys (use DD-MM-YYYY formatted date for stable matching)
        df_combine['MatchKey'] = df_combine[combine_store_col].astype(str).str.strip() + '_' + df_combine[combine_date_col].dt.strftime('%d-%m-%Y').fillna('')
        final_df['MatchKey'] = final_df[final_store_col].astype(str).str.strip() + '_' + final_df[final_date_col].dt.strftime('%d-%m-%Y').fillna('')
        
        # Merge
        merged = pd.merge(final_df, df_combine, on='MatchKey', how='left', suffixes=('', '_new'))
        
        # Update columns
        for col in update_columns:
            new_col = f"{col}_new"
            if new_col in merged.columns and col in merged.columns:
                merged[col] = merged[new_col].fillna(merged[col])
                merged = merged.drop(columns=[new_col])
        
        # Keep only original columns
        cols_to_keep = [c for c in final_df.columns if c in merged.columns and c != 'MatchKey']
        final_updated_df = merged[cols_to_keep].copy()

        # --- Output: Return updated Final MIS (preserve all original sheets) ---
        try:
            final_mis_file.seek(0)
            xls = pd.ExcelFile(final_mis_file)
            sheets = {name: pd.read_excel(xls, sheet_name=name, dtype=str) for name in xls.sheet_names}
        except Exception:
            # Fallback: if we cannot read all sheets, just return the updated sheet alone
            output_buffer = io.BytesIO()
            final_updated_df.to_excel(output_buffer, index=False, engine='openpyxl')
            output_buffer.seek(0)
            return send_file(
                output_buffer,
                as_attachment=True,
                download_name=f"Updated_Final_MIS_{combine_file.filename.split('.')[0]}.xlsx",
                mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            )

        # Replace the target sheet with our updated dataframe
        target_sheet = None
        preferred = "Reconciliation by Date by Store"
        if preferred in sheets:
            target_sheet = preferred
        else:
            # Try to guess sheet by presence of final_store_col/final_date_col
            for name, df_sheet in sheets.items():
                cols = [str(c).upper() for c in df_sheet.columns]
                if any('STORE' in c and 'CODE' in c for c in cols) and any('DATE' in c for c in cols):
                    target_sheet = name
                    break
        if not target_sheet:
            # default to first sheet name
            target_sheet = list(sheets.keys())[0]

        # Write back updated sheet (keep other sheets unchanged)
        sheets[target_sheet] = final_updated_df

        output_buffer = io.BytesIO()
        with pd.ExcelWriter(output_buffer, engine='openpyxl') as writer:
            for name, df_sheet in sheets.items():
                df_sheet.columns = df_sheet.columns.astype(str)
                df_sheet.to_excel(writer, sheet_name=name, index=False)
        output_buffer.seek(0)

        return send_file(
            output_buffer,
            as_attachment=True,
            download_name=f"Updated_Final_MIS_{combine_file.filename.split('.')[0]}.xlsx",
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )

    except Exception as e:
        print(f"Error in process_individual_combine: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


# --- Inspection endpoints for UI warnings ---
@app.route('/inspect-final-mis', methods=['POST'])
@login_required
def inspect_final_mis():
    """Return sheet names and columns for uploaded Final MIS file for UI inspection."""
    try:
        final_mis_file = request.files.get('final_mis')
        if not final_mis_file:
            return jsonify({"error": "No file uploaded."}), 400

        filename = final_mis_file.filename.lower()
        # If Excel-like, try to load sheet names
        if filename.endswith(('.xlsx', '.xlsm', '.xls', '.xlsb')):
            try:
                final_mis_file.seek(0)
                xls = pd.ExcelFile(final_mis_file)
                sheets = xls.sheet_names
                sheet_columns = {}
                preferred = "Reconciliation by Date by Store"
                for name in sheets:
                    try:
                        # read only header
                        cols = pd.read_excel(xls, sheet_name=name, nrows=0).columns.tolist()
                        sheet_columns[name] = [str(c) for c in cols]
                    except Exception:
                        sheet_columns[name] = []

                return jsonify({"sheets": sheets, "sheet_columns": sheet_columns, "preferred_present": preferred in sheets})
            except Exception as e:
                return jsonify({"error": f"Could not inspect Excel file: {str(e)}"}), 400
        else:
            # Try as CSV
            try:
                final_mis_file.seek(0)
                df = pd.read_csv(final_mis_file, nrows=0)
                cols = [str(c) for c in df.columns.tolist()]
                return jsonify({"sheets": [final_mis_file.filename], "sheet_columns": {final_mis_file.filename: cols}, "preferred_present": False})
            except Exception as e:
                return jsonify({"error": f"Could not inspect file: {str(e)}"}), 400
    except Exception as e:
        print(f"Error in inspect_final_mis: {e}")
        return jsonify({"error": str(e)}), 500


@app.route('/inspect-combine-mis', methods=['POST'])
@login_required
def inspect_combine_mis():
    """Return sheet names and columns for uploaded Combine MIS file for UI inspection."""
    try:
        combine_file = request.files.get('combine_mis')
        if not combine_file:
            return jsonify({"error": "No file uploaded."}), 400

        filename = combine_file.filename.lower()
        preferred = "MIS Working"
        if filename.endswith(('.xlsx', '.xlsm', '.xls', '.xlsb')):
            try:
                combine_file.seek(0)
                xls = pd.ExcelFile(combine_file)
                sheets = xls.sheet_names
                sheet_columns = {}
                for name in sheets:
                    try:
                        cols = pd.read_excel(xls, sheet_name=name, nrows=0).columns.tolist()
                        sheet_columns[name] = [str(c) for c in cols]
                    except Exception:
                        sheet_columns[name] = []
                return jsonify({"sheets": sheets, "sheet_columns": sheet_columns, "preferred_present": preferred in sheets})
            except Exception as e:
                return jsonify({"error": f"Could not inspect Excel file: {str(e)}"}), 400
        else:
            try:
                combine_file.seek(0)
                df = pd.read_csv(combine_file, nrows=0)
                cols = [str(c) for c in df.columns.tolist()]
                return jsonify({"sheets": [combine_file.filename], "sheet_columns": {combine_file.filename: cols}, "preferred_present": False})
            except Exception as e:
                return jsonify({"error": f"Could not inspect file: {str(e)}"}), 400
    except Exception as e:
        print(f"Error in inspect_combine_mis: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/process-final-step', methods=['POST'])
@login_required
def process_final_step():
    try:
        combine_files = request.files.getlist('combine_mis')
        final_mis_file = request.files.get('final_mis')

        if not combine_files or not final_mis_file:
            return jsonify({"error": "Missing files."}), 400

        # --- Process 1: Combine MIS Files ---
        combined_data_list = []
        
        for file in combine_files:
            try:
                # Read 'MIS Working' from row 3 (index 2)
                df = load_file_smartly(file, "MIS Working", 3)
                
                df.columns = df.columns.astype(str).str.strip()
                
                # Remove completely empty rows to be safe
                df = df.dropna(how='all')

                if not df.empty:
                    combined_data_list.append(df)
            except Exception as e:
                print(f"Error loading combine file {file.filename}: {e}")
                # Fail soft or hard? Let's fail hard to ensure data integrity
                return jsonify({"error": f"Failed to load 'MIS Working' from {file.filename}: {str(e)}"}), 400

        if not combined_data_list:
            return jsonify({"error": "No valid data found in Combine MIS files."}), 400

        master_combine_df = pd.concat(combined_data_list, ignore_index=True)
        master_combine_df = master_combine_df.dropna(how='all')
        # Columns already stripped, but ensuring type consistency
        master_combine_df.columns = master_combine_df.columns.astype(str).str.strip()
        
        print(f"DEBUG: Combined DF columns: {list(master_combine_df.columns)}")
        
        # Standardize Keys in Combined Data for Matching
        # Heuristic: Find column with 'Store' and 'Code'
        combine_store_col = next((c for c in master_combine_df.columns if isinstance(c, str) and 'STORE' in c.upper() and 'CODE' in c.upper()), None)
        # Heuristic: Find column with 'Date'
        combine_date_col = next((c for c in master_combine_df.columns if isinstance(c, str) and 'DATE' in c.upper()), None)
        
        # If not found, use first and second columns as fallback
        if combine_store_col is None:
            combine_store_col = master_combine_df.columns[0] if len(master_combine_df.columns) > 0 else None
            print(f"DEBUG: Store column not found by heuristic, using first column: {combine_store_col}")
        if combine_date_col is None:
            combine_date_col = master_combine_df.columns[1] if len(master_combine_df.columns) > 1 else master_combine_df.columns[0]
            print(f"DEBUG: Date column not found by heuristic, using second column: {combine_date_col}")

        if combine_store_col and combine_store_col in master_combine_df.columns:
            master_combine_df[combine_store_col] = master_combine_df[combine_store_col].astype(str).str.strip()
        if combine_date_col and combine_date_col in master_combine_df.columns:
             # Keep date column as datetime; matching will use formatted strings when building keys
             master_combine_df[combine_date_col] = pd.to_datetime(master_combine_df[combine_date_col], errors='coerce')

        # --- Process 2: Update Final MIS ---
        try:
            final_df = load_file_smartly(final_mis_file, "Reconciliation by Date by Store", 1)
        except Exception as e:
             return jsonify({"error": f"Could not load 'Reconciliation by Date by Store' sheet: {str(e)}"}), 400
        
        print(f"DEBUG: Final DF columns: {list(final_df.columns)}")
        
        # Prepare Final DF Keys
        final_store_col = next((c for c in final_df.columns if isinstance(c, str) and 'STORE' in c.upper() and 'CODE' in c.upper()), None)
        final_date_col = next((c for c in final_df.columns if isinstance(c, str) and 'DATE' in c.upper()), None)
        
        # If not found, use first and second columns as fallback
        if final_store_col is None:
            final_store_col = final_df.columns[0] if len(final_df.columns) > 0 else None
            print(f"DEBUG: Final store column not found by heuristic, using first column: {final_store_col}")
        if final_date_col is None:
            final_date_col = final_df.columns[1] if len(final_df.columns) > 1 else final_df.columns[0]
            print(f"DEBUG: Final date column not found by heuristic, using second column: {final_date_col}")

        if final_store_col and final_store_col in final_df.columns:
            final_df[final_store_col] = final_df[final_store_col].astype(str).str.strip()
        if final_date_col and final_date_col in final_df.columns:
            final_df[final_date_col] = pd.to_datetime(final_df[final_date_col], errors='coerce')

        # Columns to Update (from your provided CSV list)
        update_columns = [
            'HB-Card', 'HB-Cash', 'HB-Online',
            'MR-Card', 'MR-Cash', 'MR-Online',
            'CO-Card', 'CO-Cash', 'CO-Online-Paytm', 'CO-Online-Other', 'CO-CCN', 'CO-Bank Offer',
            'Remarks', 'Performa Invoice Number',
            'Ad-Card', 'Ad-Cash', 'Ad-Online - PayTm', 'Ad-Online - Other', 'Ad-CCN', 'Ad-Store Correction', 'Ad-Bank Offer'
        ]

        # Perform Update
        # We iterate through the Final DF and look up values in Master Combined
        # A merge is faster than iteration.
        
        # Validate that we have required columns
        if not combine_store_col or not combine_date_col:
            return jsonify({"error": "Could not identify Store Code and Date columns in Combine MIS files."}), 400
        if not final_store_col or not final_date_col:
            return jsonify({"error": "Could not identify Store Code and Date columns in Final MIS file."}), 400
        
        # Create match keys
        master_combine_df['MatchKey'] = master_combine_df[combine_store_col].astype(str) + '_' + master_combine_df[combine_date_col].astype(str)
        final_df['MatchKey'] = final_df[final_store_col].astype(str) + '_' + final_df[final_date_col].astype(str)
        
        # Drop duplicates in matched data to avoid explosion, keeping last or first? Assuming first.
        master_combine_dedup = master_combine_df.drop_duplicates(subset=['MatchKey'])
        
        # Merge
        # We want to keep all rows in Final DF, just update columns
        merged = pd.merge(final_df, master_combine_dedup, on='MatchKey', how='left', suffixes=('', '_new'))
        
        # Update specific columns if they exist in the new data
        for col in update_columns:
            new_col = f"{col}_new"
            if new_col in merged.columns and col in merged.columns:
                # Update matching rows, keep original if no match or new val is nan
                merged[col] = merged[new_col].fillna(merged[col])
                # Drop the _new column after updating
                merged = merged.drop(columns=[new_col])
        
        # Cleanup: Remove remaining _new columns and MatchKey
        cols_to_keep = [c for c in final_df.columns if c in merged.columns and c != 'MatchKey']
        
        final_updated_df = merged[cols_to_keep].copy()

        # --- Output ---
        # Create a ZIP file containing both
        memory_file = io.BytesIO()
        with zipfile.ZipFile(memory_file, 'w', zipfile.ZIP_DEFLATED) as zf:
            # 1. Combined Data
            tmp_buf = io.BytesIO()
            # Remove MatchKey before exporting
            master_export = master_combine_df.drop(columns=['MatchKey']) if 'MatchKey' in master_combine_df.columns else master_combine_df
            master_export.to_excel(tmp_buf, index=False, engine='openpyxl')
            tmp_buf.seek(0)
            zf.writestr('Combined_MIS_Data.xlsx', tmp_buf.getvalue())
            
            # 2. Updated Final MIS
            try:
                # Try to preserve other sheets from the uploaded Final MIS
                final_mis_file.seek(0)
                xls = pd.ExcelFile(final_mis_file)
                sheets = {name: pd.read_excel(xls, sheet_name=name, dtype=str) for name in xls.sheet_names}
                # Replace target sheet
                preferred = "Reconciliation by Date by Store"
                if preferred in sheets:
                    target = preferred
                else:
                    target = None
                    for name, df_sheet in sheets.items():
                        cols = [str(c).upper() for c in df_sheet.columns]
                        if any('STORE' in c and 'CODE' in c for c in cols) and any('DATE' in c for c in cols):
                            target = name
                            break
                    if not target:
                        target = list(sheets.keys())[0]
                sheets[target] = final_updated_df

                tmp_buf = io.BytesIO()
                with pd.ExcelWriter(tmp_buf, engine='openpyxl') as writer:
                    for name, df_sheet in sheets.items():
                        df_sheet.columns = df_sheet.columns.astype(str)
                        df_sheet.to_excel(writer, sheet_name=name, index=False)
                tmp_buf.seek(0)
                zf.writestr('Updated_Final_MIS.xlsx', tmp_buf.getvalue())
            except Exception:
                tmp_buf = io.BytesIO()
                final_updated_df.to_excel(tmp_buf, index=False, engine='openpyxl')
                tmp_buf.seek(0)
                zf.writestr('Updated_Final_MIS.xlsx', tmp_buf.getvalue())

        memory_file.seek(0)
        
        return send_file(
            memory_file,
            as_attachment=True,
            download_name="Final_Process_Output.zip",
            mimetype='application/zip'
        )

    except Exception as e:
        print(f"Error in process_final_step: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

# --- 13. SEARCH & PROMPTS API (NEW feature) ---

@app.route('/api/prompts', methods=['GET', 'POST'])
@login_required
def api_prompts():
    if request.method == 'GET':
        prompts = db.session.execute(db.select(Prompt).order_by(Prompt.title)).scalars().all()
        return jsonify([{'id': p.id, 'title': p.title, 'content': p.content} for p in prompts])
    
    data = request.json
    if not data or not data.get('title') or not data.get('content'):
        return jsonify({"error": "Title and content required"}), 400
    
    prompt = Prompt(title=data['title'], content=data['content'])
    db.session.add(prompt)
    db.session.commit()
    return jsonify({'id': prompt.id, 'title': prompt.title, 'content': prompt.content}), 201

@app.route('/api/prompts/<int:id>', methods=['PUT', 'DELETE'])
@login_required
def api_prompt_item(id):
    prompt = db.session.get(Prompt, id)
    if not prompt:
        return jsonify({"error": "Prompt not found"}), 404
        
    if request.method == 'DELETE':
        db.session.delete(prompt)
        db.session.commit()
        return jsonify({"message": "Deleted"}), 200
    
    data = request.json
    if 'title' in data: prompt.title = data['title']
    if 'content' in data: prompt.content = data['content']
    db.session.commit()
    return jsonify({'id': prompt.id, 'title': prompt.title, 'content': prompt.content})

@app.route('/api/search', methods=['GET'])
@login_required
def api_search():
    query = request.args.get('q', '').strip().lower()
    
    # --- Advanced Filters ---
    # Date: 'start' and 'end' in YYYY-MM-DD format, or 'all'
    date_type = request.args.get('date_type', 'all') # 'all', 'range', 'single'
    start_date_str = request.args.get('start_date', '')
    end_date_str = request.args.get('end_date', '')
    
    # Categories: comma-separated list (e.g., "sales,banking")
    categories_str = request.args.get('categories', '')
    categories = [c.lower() for c in categories_str.split(',') if c.strip()]
    
    # Payment Modes: comma-separated
    payment_modes_str = request.args.get('payment_modes', '')
    payment_modes = [p.lower() for p in payment_modes_str.split(',') if p.strip()]

    if not query and not (categories or payment_modes or date_type != 'all'):
         return jsonify({"results": [], "summary": {"total_count": 0, "total_value": 0}})

    results = []
    total_value = 0.0
    
    excel_exts = ('.xlsx', '.xls', '.xlsm', '.xlsb', '.csv')
    
    # Date parsing helper
    start_dt = None
    end_dt = None
    if date_type in ('range', 'single') and start_date_str:
        try:
            start_dt = datetime.strptime(start_date_str, '%Y-%m-%d')
            if date_type == 'range' and end_date_str:
                 end_dt = datetime.strptime(end_date_str, '%Y-%m-%d') + timedelta(days=1) # Include end date
            elif date_type == 'single':
                 end_dt = start_dt + timedelta(days=1)
            else:
                 end_dt = start_dt + timedelta(days=1) # Fallback for open-ended range
        except Exception:
            pass

    if os.path.exists(UPLOAD_FOLDER):
        for root, dirs, files in os.walk(UPLOAD_FOLDER):
            for file in files:
                if file.endswith('.log'): continue
                
                lower_file = file.lower()
                path = os.path.join(root, file)
                rel_path = os.path.relpath(path, UPLOAD_FOLDER)
                
                # --- 1. Category Filter (Filename based) ---
                if categories:
                    # Categories: sales, advances, banking
                    # Heuristics:
                    is_sales = 'sales' in lower_file
                    is_advances = 'advances' in lower_file or 'ad-' in lower_file
                    is_banking = 'bank' in lower_file or 'collection' in lower_file or 'statement' in lower_file
                    
                    matched_category = False
                    if 'sales' in categories and is_sales: matched_category = True
                    if 'advances' in categories and is_advances: matched_category = True
                    if 'banking' in categories and is_banking: matched_category = True
                    
                    if not matched_category: continue

                # --- 2. Date Filter (File Modification Time) ---
                # NOTE: For deep searching, we might ideally check DATES INSIDE the file, 
                # but for global search, file mod time is the standard "file date".
                if start_dt and end_dt:
                    mtime = datetime.fromtimestamp(os.path.getmtime(path))
                    if not (start_dt <= mtime < end_dt):
                        continue

                # --- Search Logic ---
                if lower_file.endswith(excel_exts):
                    try:
                        dfs = {}
                        if lower_file.endswith('.csv'):
                            dfs['Sheet1'] = pd.read_csv(path, dtype=str, on_bad_lines='skip', nrows=5000)
                        else:
                            xls = pd.ExcelFile(path)
                            for sheet_name in xls.sheet_names:
                                dfs[sheet_name] = pd.read_excel(xls, sheet_name=sheet_name, dtype=str, nrows=2000)
                        
                        for sheet, df in dfs.items():
                             # Standardize columns for payment mode check
                             df_upper = df.copy()
                             df_upper.columns = df_upper.columns.astype(str).str.upper().str.strip()
                             
                             # Payment Mode Filter
                             if payment_modes:
                                 # Find payment mode column
                                 pm_col = next((c for c in df_upper.columns if 'PAYMENT' in c or 'MOP' in c or 'MODE' in c), None)
                                 if pm_col:
                                     # Filter DF
                                     # Check if any of the payment_modes exists in the cell value
                                     mask = df_upper[pm_col].astype(str).str.lower().apply(lambda x: any(pm in x for pm in payment_modes))
                                     df = df[mask]
                                     df_upper = df_upper[mask]
                             
                             if df.empty: continue

                             # Text Query Filter
                             if query:
                                 mask = df.apply(lambda x: x.astype(str).str.lower().str.contains(query, na=False))
                                 matched_rows = df[mask.any(axis=1)]
                             else:
                                 matched_rows = df # Return all if only filtering by cat/mode
                             
                             if matched_rows.empty: continue

                             # Calculate Value (Heuristic)
                             amount_col = next((c for c in df_upper.columns if 'AMOUNT' in c or 'TOTAL' in c or 'NET' in c or 'VALUE' in c), None)
                             
                             for idx, row in matched_rows.head(10).iterrows(): # Limit 10 to UI
                                 # Highlight snippet
                                 match_details = "Matched Filters"
                                 if query:
                                     matched_cols = [col for col in df.columns if query in str(row[col]).lower()]
                                     match_details = f"Matched in: {', '.join(matched_cols)}"
                                 
                                 # Add to total value
                                 if amount_col:
                                     try:
                                         val = float(str(row.get(df.columns[df_upper.columns.get_loc(amount_col)])).replace(',','').strip())
                                         total_value += val
                                     except:
                                         pass

                                 results.append({
                                     "type": "excel_row",
                                     "name": file,
                                     "path": rel_path,
                                     "sheet": sheet,
                                     "row_index": idx + 2,
                                     "match_type": match_details,
                                     "data": row.fillna('').to_dict()
                                 })
                            
                             # If query is empty but filters active, assume we want value of all filtered rows
                             if not query and amount_col:
                                  # Sum remaining rows not just the head(10)
                                  remaining = matched_rows.iloc[10:]
                                  for idx, row in remaining.iterrows():
                                      try:
                                          val = float(str(row.get(df.columns[df_upper.columns.get_loc(amount_col)])).replace(',','').strip())
                                          total_value += val
                                      except: pass
                                      
                    except Exception as e:
                        print(f"Error searching excel {file}: {e}")

    return jsonify({
        "results": results, 
        "summary": {
            "total_count": len(results),
            "total_value": total_value
        }
    })

@app.route('/api/search/export', methods=['GET'])
@login_required
def api_search_export():
    """Export search results to Excel."""
    # Reuse logic from api_search but return file
    # For brevity, I'll copy the core logic. In refactoring, this should be a shared function.
    query = request.args.get('q', '').strip().lower()
    date_type = request.args.get('date_type', 'all') 
    start_date_str = request.args.get('start_date', '')
    end_date_str = request.args.get('end_date', '')
    categories_str = request.args.get('categories', '')
    categories = [c.lower() for c in categories_str.split(',') if c.strip()]
    payment_modes_str = request.args.get('payment_modes', '')
    payment_modes = [p.lower() for p in payment_modes_str.split(',') if p.strip()]

    all_rows = []
    
    excel_exts = ('.xlsx', '.xls', '.xlsm', '.xlsb', '.csv')
    
    from datetime import datetime, timedelta
    start_dt = None
    end_dt = None
    if date_type in ('range', 'single') and start_date_str:
        try:
            start_dt = datetime.strptime(start_date_str, '%Y-%m-%d')
            if date_type == 'range' and end_date_str:
                 end_dt = datetime.strptime(end_date_str, '%Y-%m-%d') + timedelta(days=1)
            else:
                 end_dt = start_dt + timedelta(days=1)
        except Exception: pass

    if os.path.exists(UPLOAD_FOLDER):
        for root, dirs, files in os.walk(UPLOAD_FOLDER):
            for file in files:
                if file.endswith('.log'): continue
                path = os.path.join(root, file)
                lower_file = file.lower()
                
                if categories:
                    is_sales = 'sales' in lower_file
                    is_advances = 'advances' in lower_file or 'ad-' in lower_file
                    is_banking = 'bank' in lower_file or 'collection' in lower_file
                    matched_category = False
                    if 'sales' in categories and is_sales: matched_category = True
                    if 'advances' in categories and is_advances: matched_category = True
                    if 'banking' in categories and is_banking: matched_category = True
                    if not matched_category: continue

                if start_dt and end_dt:
                    mtime = datetime.fromtimestamp(os.path.getmtime(path))
                    if not (start_dt <= mtime < end_dt): continue

                if lower_file.endswith(excel_exts):
                    try:
                        dfs = {}
                        if lower_file.endswith('.csv'):
                             dfs['Sheet1'] = pd.read_csv(path, dtype=str, on_bad_lines='skip')
                        else:
                             xls = pd.ExcelFile(path)
                             for sheet_name in xls.sheet_names:
                                 dfs[sheet_name] = pd.read_excel(xls, sheet_name=sheet_name, dtype=str)
                        
                        for sheet, df in dfs.items():
                             df_upper = df.copy()
                             df_upper.columns = df_upper.columns.astype(str).str.upper().str.strip()
                             
                             if payment_modes:
                                 pm_col = next((c for c in df_upper.columns if 'PAYMENT' in c or 'MOP' in c or 'MODE' in c), None)
                                 if pm_col:
                                     mask = df_upper[pm_col].astype(str).str.lower().apply(lambda x: any(pm in x for pm in payment_modes))
                                     df = df[mask]
                             
                             if df.empty: continue

                             if query:
                                 mask = df.apply(lambda x: x.astype(str).str.lower().str.contains(query, na=False))
                                 matched_rows = df[mask.any(axis=1)]
                             else:
                                 matched_rows = df
                             
                             if matched_rows.empty: continue
                             
                             # Add source metadata
                             matched_rows = matched_rows.copy()
                             matched_rows.insert(0, 'Source File', file)
                             matched_rows.insert(1, 'Source Sheet', sheet)
                             all_rows.append(matched_rows)

                    except Exception: pass
    
    if not all_rows:
        return jsonify({"error": "No data found to export"}), 404
        
    final_df = pd.concat(all_rows, ignore_index=True)
    
    output_buffer = io.BytesIO()
    final_df.to_excel(output_buffer, index=False, engine='openpyxl')
    output_buffer.seek(0)
    
    return send_file(
        output_buffer,
        as_attachment=True,
        download_name=f"Search_Results_{int(time.time())}.xlsx",
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
        
# --- 14. SEARCH DASHBOARD ROUTES & LOGIC ---

@app.route('/admin/save_search_file', methods=['POST'])
@login_required
def save_search_file():
    if not current_user.is_admin: abort(403)
    file = request.files.get('search_file')
    if not file:
        flash('No file selected.', 'error')
        return redirect(url_for('admin_portal', tab='SearchConfig'))
    
    filename = file.filename
    ext = os.path.splitext(filename)[1].lower()
    if ext not in ['.xlsx', '.xls', '.xlsb', '.csv']:
        flash('Unsupported file type.', 'error')
        return redirect(url_for('admin_portal', tab='SearchConfig'))

    # Clear existing file
    existing = db.session.execute(db.select(SearchFile)).scalar_one_or_none()
    if existing:
        try:
            if os.path.exists(existing.filepath):
                os.remove(existing.filepath)
            db.session.delete(existing)
        except Exception: pass
    
    # Save new file
    safe_filename = f"search_master_{uuid.uuid4().hex}{ext}"
    filepath = os.path.join(UPLOAD_FOLDER, safe_filename)
    file.save(filepath)
    
    new_file = SearchFile(filename=filename, filepath=filepath)
    db.session.add(new_file)
    db.session.commit()
    
    flash(f'Search file "{filename}" uploaded successfully.', 'success')
    return redirect(url_for('admin_portal', tab='SearchConfig'))

@app.route('/admin/delete_search_file')
@login_required
def delete_search_file():
    if not current_user.is_admin: abort(403)
    existing = db.session.execute(db.select(SearchFile)).scalar_one_or_none()
    if existing:
        try:
            if os.path.exists(existing.filepath):
                os.remove(existing.filepath)
        except Exception: pass
        db.session.delete(existing)
        db.session.commit()
        flash('Search file deleted.', 'success')
    else:
        flash('No search file to delete.', 'info')
    return redirect(url_for('admin_portal', tab='SearchConfig'))

@app.route('/admin/save_search_rule', methods=['POST'])
@login_required
def save_search_rule():
    if not current_user.is_admin: abort(403)
    rule_type = request.form.get('rule_type') # 'category' or 'payment_mode'
    
    if rule_type == 'category':
        name = request.form.get('category_name')
        sheet = request.form.get('sheet_name')
        if name and sheet:
            # unique check
            existing = db.session.execute(db.select(SearchCategoryRule).filter_by(category_name=name)).scalar_one_or_none()
            if existing: existing.sheet_name = sheet
            else: db.session.add(SearchCategoryRule(category_name=name, sheet_name=sheet))
            db.session.commit()
            flash(f'Category "{name}" Saved.', 'success')

    elif rule_type == 'payment_mode':
        name = request.form.get('mode_name')
        cols = request.form.get('columns')
        sheet_name = request.form.get('sheet_name', '').strip() or None
        
        if name and cols:
            # Always add new rule (since mode_name is not unique anymore)
            # Users can delete old rules if they want to change them
            db.session.add(SearchPaymentModeRule(mode_name=name, columns=cols, sheet_name=sheet_name))
            db.session.commit()
            flash(f'Payment Mode Rule "{name}" Added.', 'success')
            
    return redirect(url_for('admin_portal', tab='SearchConfig'))

@app.route('/admin/delete_search_rule/<type>/<int:id>')
@login_required
def delete_search_rule(type, id):
    if not current_user.is_admin: abort(403)
    if type == 'category':
        rule = db.session.get(SearchCategoryRule, id)
    else:
        rule = db.session.get(SearchPaymentModeRule, id)
    
    if rule:
        db.session.delete(rule)
        db.session.commit()
        flash('Rule deleted.', 'success')
    return redirect(url_for('admin_portal', tab='SearchConfig'))


@app.route('/api/search_dashboard', methods=['POST'])
@login_required
def search_dashboard_api():
    query = request.form.get('query', '').strip().lower()
    categories = request.form.getlist('categories[]') 
    payment_modes = request.form.getlist('payment_modes[]') 
    
    # 1. Get the Active File
    search_file = db.session.execute(db.select(SearchFile)).scalar_one_or_none()
    if not search_file or not os.path.exists(search_file.filepath):
        return jsonify({'error': 'No active search file configured by Admin.'}), 400
    
    results = []
    
    try:
        # 2. Determine Sheets to Search based on Categories
        cat_rules = db.session.execute(db.select(SearchCategoryRule)).scalars().all()
        sheet_map = {r.category_name: r.sheet_name for r in cat_rules}
        
        target_sheets = []
        if not categories: 
            target_sheets = list(sheet_map.values())
        else:
            for cat in categories:
                if cat in sheet_map:
                    target_sheets.append(sheet_map[cat])

        # 3. Determine Columns to Search based on Payment Modes with Sheet context
        # Fetch all rules first
        all_mode_rules = db.session.execute(db.select(SearchPaymentModeRule)).scalars().all()
        
        # We need to filter which rules apply based on the selected 'payment_modes'
        # Structure: target_col_specs = [ {'keywords': [], 'sheet_patterns': ['A', 'B'] or None} ]
        target_col_specs = []
        
        if payment_modes:
            for pm in payment_modes:
                # Find all rules that match this mode name
                matching_rules = [r for r in all_mode_rules if r.mode_name == pm]
                
                for r in matching_rules:
                    sheets = None
                    if r.sheet_name:
                        sheets = [s.strip().lower() for s in r.sheet_name.split(',') if s.strip()]
                    
                    target_col_specs.append({
                        'keywords': [k.strip().upper() for k in r.columns.split(',')],
                        'sheet_patterns': sheets 
                    })
        
        # 4. Load File
        filepath = search_file.filepath
        
        xl = pd.ExcelFile(filepath)
        all_sheets = xl.sheet_names
        
        for sheet in all_sheets:
            # Check if this sheet matches any target sheet pattern (substring match)
            matched_cat_sheet = next((s for s in target_sheets if str(s).lower() in sheet.lower()), None)
            
            if categories and not matched_cat_sheet:
                continue 
            
            # Load sheet
            df = pd.read_excel(xl, sheet_name=sheet, dtype=str)
            df.columns = df.columns.astype(str).str.strip()
            
            # Filter Columns based on Specs
            cols_to_search = []
            matched_col_names = []
            
            if target_col_specs:
                for col in df.columns:
                    upper_col = col.upper()
                    
                    # Check if this column matches ANY spec that is valid for this sheet
                    # A spec is valid if:
                    # 1. spec['sheet_patterns'] is None (applies to all sheets)
                    # 2. OR current sheet matches ANY of the sheet_patterns
                    
                    for spec in target_col_specs:
                        is_sheet_valid = False
                        if not spec['sheet_patterns']:
                            is_sheet_valid = True
                        else:
                            # Check if current 'sheet' (from file) partially matches any pattern
                            for pattern in spec['sheet_patterns']:
                                if pattern in sheet.lower():
                                    is_sheet_valid = True
                                    break # Found a matching pattern for this rule
                            
                        if is_sheet_valid:
                            # Check keywords
                            if any(k in upper_col for k in spec['keywords']):
                                cols_to_search.append(col)
                                matched_col_names.append(col)
                                break # Matched this column, move to next
                                
                if not cols_to_search:
                     continue 
            else:
                cols_to_search = df.columns.tolist()
            
            if not query: continue
            
            # Subset DF
            df_subset = df[cols_to_search]
            
            # Perform search (case insensitive)
            mask = df_subset.apply(lambda x: x.astype(str).str.lower().str.contains(query, na=False))
            matched_indices = df_subset[mask.any(axis=1)].index
            
            if len(matched_indices) > 0:
                # Limit to first 50 matches per sheet
                for idx in matched_indices[:50]:
                    row_data = df.iloc[idx].to_dict()
                    # Find which column matched
                    matched_cols = []
                    for col in cols_to_search:
                        val = str(row_data.get(col, '')).lower()
                        if query in val:
                            matched_cols.append(col)
                    
                    results.append({
                        'sheet': sheet,
                        'row': int(idx) + 2, 
                        'matched_columns': ', '.join(matched_cols),
                        'data': row_data
                    })

        return jsonify({'results': results})

    except Exception as e:
        return jsonify({'error': str(e)}), 500

# --- 15. SPLIT FILE ROUTE ---
@app.route('/process-split-file', methods=['POST'])
@login_required
def process_split_file():
    try:
        file = request.files.get('split_file')
        split_col = request.form.get('split_column', 'AMVIAK SPOC').strip()
        custom_sheet_name = request.form.get('sheet_name', '').strip()
        
        if not file: return jsonify({'error': 'No file uploaded'}), 400
        
        target_sheet = custom_sheet_name if custom_sheet_name else "Reconciliation by Date by Store"
        
        try:
            filename = file.filename.lower()
            df = None
            if filename.endswith(('.xlsx', '.xls', '.xlsb', '.xlsm')):
                 xl = pd.ExcelFile(file)
                 sheet_to_use = None
                 
                 # Resolve sheet name
                 if custom_sheet_name and custom_sheet_name in xl.sheet_names:
                     sheet_to_use = custom_sheet_name
                 elif "Reconciliation by Date by Store" in xl.sheet_names:
                     sheet_to_use = "Reconciliation by Date by Store"
                 else:
                     sheet_to_use = xl.sheet_names[0] 
                 
                 # Logic to find header row for the column
                 preview = pd.read_excel(xl, sheet_name=sheet_to_use, nrows=10, header=None)
                 header_row_idx = -1
                 for i, row in preview.iterrows():
                     row_str = row.astype(str).str.upper().tolist()
                     if split_col.upper() in row_str:
                         header_row_idx = i
                         break
                 
                 if header_row_idx == -1: header_row_idx = 1
                 
                 df = pd.read_excel(xl, sheet_name=sheet_to_use, header=header_row_idx, dtype=str)
                 
            elif filename.endswith('.csv'):
                 df = pd.read_csv(file, dtype=str) 
            
            if df is None: return jsonify({'error': 'Unsupported file'}), 400
            
            df.columns = df.columns.astype(str).str.strip()
            
            real_col = next((c for c in df.columns if c.upper() == split_col.upper()), None)
            if not real_col:
                return jsonify({'error': f'Column "{split_col}" not found in sheet.'}), 400
                
            unique_vals = df[real_col].dropna().unique()
            
            output_zip = io.BytesIO()
            import zipfile
            with zipfile.ZipFile(output_zip, 'w') as zf:
                for val in unique_vals:
                    val_str = str(val).strip()
                    if not val_str: continue
                    
                    sub_df = df[df[real_col] == val]
                    
                    buf = io.BytesIO()
                    with pd.ExcelWriter(buf, engine='xlsxwriter') as writer:
                        sub_df.to_excel(writer, index=False, sheet_name='Sheet1')
                    
                    safe_val = "".join([c for c in val_str if c.isalpha() or c.isdigit() or c==' ']).strip()
                    zf.writestr(f"{safe_val}.xlsx", buf.getvalue())
            
            output_zip.seek(0)
            return send_file(output_zip, as_attachment=True, download_name="Split_Files.zip", mimetype='application/zip')

        except Exception as e:
            return jsonify({'error': str(e)}), 400
            
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# --- 16. RUN THE APP (FINAL) ---
if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        create_default_data()
    # --- UPDATED: Added host='0.0.0.0' ---
    app.run(host='0.0.0.0', port=5001, debug=True)