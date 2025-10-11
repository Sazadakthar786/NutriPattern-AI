from flask import Flask, render_template, redirect, url_for, request, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import os
from werkzeug.utils import secure_filename
import random
import pytesseract
import easyocr
import pdfplumber
import json
import pandas as pd
from supabase_config import get_supabase_client

# Remove unused LLM imports and keys
# import openai
# import google.generativeai as genai
# GEMINI_API_KEY = 'AIzaSyC47-KitYe8DO5y2lYQ_IL-COvNs1G-KWY'
# OPENAI_API_KEY = 'sk-XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX'

app = Flask(__name__)

# Secrets and configuration via environment variables for production
app.secret_key = os.getenv('SECRET_KEY', 'dev-secret-key')


# Support DATABASE_URL (Render/Heroku style); fallback to local SQLite
database_url = os.getenv('DATABASE_URL', 'sqlite:///healthapp.db')
# SQLAlchemy requires postgresql:// instead of postgres://
if database_url.startswith('postgres://'):
    database_url = database_url.replace('postgres://', 'postgresql://', 1)
app.config['SQLALCHEMY_DATABASE_URI'] = database_url
db = SQLAlchemy(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

@login_manager.unauthorized_handler
def unauthorized():
    return jsonify({'error': 'Authentication required'}), 401
with app.app_context():
    db.create_all()

# Database initialization complete

# Supabase integration
class SupabaseService:
    def __init__(self):
        self.supabase = get_supabase_client()
    
    def create_user(self, user_data):
        """Create a new user in Supabase"""
        try:
            result = self.supabase.table('users').insert(user_data).execute()
            return result.data[0] if result.data else None
        except Exception as e:
            print(f"Supabase user creation error: {e}")
            return None
    
    def get_user(self, user_id):
        """Get user by ID from Supabase"""
        try:
            result = self.supabase.table('users').select('*').eq('id', user_id).execute()
            return result.data[0] if result.data else None
        except Exception as e:
            print(f"Supabase user retrieval error: {e}")
            return None
    
    def create_health_report(self, report_data):
        """Create a new health report in Supabase"""
        try:
            result = self.supabase.table('health_reports').insert(report_data).execute()
            return result.data[0] if result.data else None
        except Exception as e:
            print(f"Supabase health report creation error: {e}")
            return None
    
    def get_user_reports(self, user_id):
        """Get all health reports for a user from Supabase"""
        try:
            result = self.supabase.table('health_reports').select('*').eq('user_id', user_id).execute()
            return result.data if result.data else []
        except Exception as e:
            print(f"Supabase health reports retrieval error: {e}")
            return []
    
    def create_message(self, message_data):
        """Create a new message in Supabase"""
        try:
            result = self.supabase.table('messages').insert(message_data).execute()
            return result.data[0] if result.data else None
        except Exception as e:
            print(f"Supabase message creation error: {e}")
            return None
    
    def get_user_messages(self, user_id):
        """Get all messages for a user from Supabase"""
        try:
            result = self.supabase.table('messages').select('*').eq('recipient_id', user_id).execute()
            return result.data if result.data else []
        except Exception as e:
            print(f"Supabase messages retrieval error: {e}")
            return []

# Initialize Supabase service
supabase_service = SupabaseService()

# Custom Jinja2 filters
@app.template_filter('from_json')
def from_json_filter(value):
    try:
        return json.loads(value)
    except (ValueError, TypeError):
        return None

UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'pdf', 'jpg', 'jpeg', 'png'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# OpenRouter API key from environment for production
OPENROUTER_API_KEY = os.getenv('OPENROUTER_API_KEY', '')

import requests

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def extract_text_from_file(filepath, lang='eng'):
    ext = os.path.splitext(filepath)[1].lower()
    text = ''
    if ext == '.pdf':
        with pdfplumber.open(filepath) as pdf:
            for page in pdf.pages:
                text += page.extract_text() or ''
        if not text.strip():
            # Fallback to OCR for scanned PDFs
            import cv2
            from pdf2image import convert_from_path
            images = convert_from_path(filepath)
            for img in images:
                text += pytesseract.image_to_string(img, lang=lang)
    elif ext in ['.jpg', '.jpeg', '.png']:
        try:
            reader = easyocr.Reader([lang])
            result = reader.readtext(filepath, detail=0)
            text = '\n'.join(result)
        except Exception:
            text = pytesseract.image_to_string(filepath, lang=lang)
    return text

def parse_medical_values(text):
    import re
    import pandas as pd
    print('--- Extracted Text Start ---')
    print(text)
    print('--- Extracted Text End ---')
    values = {}
    # Load all test parameters from CSV
    param_df = pd.read_csv('medical_test_parameters.csv')
    # Add common abbreviations for matching
    abbrev_map = {
        'Hemoglobin (Hb)': ['Hemoglobin', 'Hb'],
        'RBC Count': ['RBC Count', 'RBC'],
        'WBC Count': ['WBC Count', 'WBC'],
        'Platelet Count': ['Platelet Count', 'Platelets'],
        'Hematocrit (HCT)': ['Hematocrit', 'HCT'],
        'MCV': ['MCV'],
        'MCH': ['MCH'],
        'MCHC': ['MCHC'],
        'RDW': ['RDW'],
        'Neutrophils (%)': ['Neutrophils'],
        'Lymphocytes (%)': ['Lymphocytes'],
        'Monocytes (%)': ['Monocytes'],
        'Eosinophils (%)': ['Eosinophils'],
        'Basophils (%)': ['Basophils'],
        'SGOT / AST': ['SGOT', 'AST'],
        'SGPT / ALT': ['SGPT', 'ALT'],
        'ALP': ['ALP'],
        'Total Bilirubin': ['Total Bilirubin', 'Bilirubin'],
        'Direct Bilirubin': ['Direct Bilirubin'],
        'Albumin': ['Albumin'],
        'Globulin': ['Globulin'],
        'A/G Ratio': ['A/G Ratio'],
        'Creatinine': ['Creatinine'],
        'Urea / BUN': ['Urea', 'BUN'],
        'Uric Acid': ['Uric Acid'],
        'Sodium (Na+)': ['Sodium', 'Na+'],
        'Potassium (K+)': ['Potassium', 'K+'],
        'Chloride (Cl-)': ['Chloride', 'Cl-'],
        'Fasting Blood Sugar (FBS)': ['Fasting Blood Sugar', 'FBS'],
        'Postprandial Blood Sugar (PPBS)': ['Postprandial Blood Sugar', 'PPBS'],
        'HbA1c': ['HbA1c'],
        'Random Blood Sugar (RBS)': ['Random Blood Sugar', 'RBS'],
        'Insulin (Fasting)': ['Insulin'],
        'Total Cholesterol': ['Total Cholesterol', 'Cholesterol'],
        'HDL': ['HDL'],
        'LDL': ['LDL'],
        'VLDL': ['VLDL'],
        'Triglycerides': ['Triglycerides'],
        'Cholesterol/HDL Ratio': ['Cholesterol/HDL Ratio'],
        'Vitamin D (25-OH)': ['Vitamin D', '25-OH'],
        'Vitamin B12': ['Vitamin B12', 'B12'],
        'Calcium': ['Calcium'],
        'Iron': ['Iron'],
        'Ferritin': ['Ferritin'],
        'TIBC': ['TIBC'],
        'Magnesium': ['Magnesium'],
        'Phosphorus': ['Phosphorus'],
        'TSH': ['TSH'],
        'T3': ['T3'],
        'T4': ['T4'],
        'Free T3': ['Free T3'],
        'Free T4': ['Free T4'],
    }
    for idx, row in param_df.iterrows():
        param = row['Test Name']
        key = param.lower().replace(' ', '_').replace('(', '').replace(')', '').replace('/', '_').replace('%', 'percent').replace('-', '_').replace('.', '').replace(',', '').replace('__', '_')
        patterns = []
        # Try all known names/abbreviations
        for name in abbrev_map.get(param, [param]):
            patterns.append(rf"{re.escape(name)}\s*[:=\-]?\s*([\d.]+)")
            patterns.append(rf"{re.escape(name)}\s*[a-zA-Z]*\s*[:=\-]?\s*([\d.]+)")
        for pat in patterns:
            m = re.search(pat, text, re.IGNORECASE)
            if m:
                values[key] = m.group(1)
                break
    # Example condition detection (expand as needed)
    conditions = []
    if 'sugar' in values and float(values['sugar']) > 140:
        conditions.append('High Blood Sugar')
    if 'cholesterol' in values and float(values['cholesterol']) > 200:
        conditions.append('High Cholesterol')
    if 'hemoglobin' in values and float(values['hemoglobin']) < 12:
        conditions.append('Anemia')
    return values, conditions

# Generate unique patient ID
def generate_patient_id():
    import random
    import string
    while True:
        # Generate a 8-character alphanumeric ID
        patient_id = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
        # Check if it already exists
        if not User.query.filter_by(patient_id=patient_id).first():
            return patient_id

# Remove get_ai_reply function

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    patient_id = db.Column(db.String(16), unique=True, nullable=False)  # Unique patient ID
    age = db.Column(db.Integer)
    gender = db.Column(db.String(10))
    height = db.Column(db.Float)
    weight = db.Column(db.Float)
    goal = db.Column(db.String(32), default='weight_loss')
    role = db.Column(db.String(16), default='user')
    profile_image = db.Column(db.String(200), nullable=True)  # New: profile image path
    reports = db.relationship('MedicalReport', backref='user', lazy=True)

class MedicalReport(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(200))
    values = db.Column(db.Text)  # JSON string of extracted values
    conditions = db.Column(db.Text)  # JSON string of detected conditions
    diet_chart = db.Column(db.Text)  # JSON string of diet chart
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

class ActivityLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, default=datetime.utcnow)
    steps = db.Column(db.Integer)
    exercise = db.Column(db.String(100))
    calories = db.Column(db.Integer)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

class HealthReport(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    filename = db.Column(db.String(200))
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    extracted_values = db.Column(db.Text)  # JSON/text
    conditions = db.Column(db.Text)        # JSON/text
    diet_plan = db.Column(db.Text)        # JSON/text
    doctor_comment = db.Column(db.Text)   # Doctor's comment
    comment_timestamp = db.Column(db.DateTime)  # When comment was added
    shared_with_doctor = db.Column(db.Boolean, default=False)

class ChatHistory(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    message = db.Column(db.Text)
    reply = db.Column(db.Text)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    sender_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    receiver_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    message_type = db.Column(db.String(20), default='comment')  # comment, suggestion, diet_update
    content = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    is_read = db.Column(db.Boolean, default=False)
    related_report_id = db.Column(db.Integer, db.ForeignKey('health_report.id'), nullable=True)
    
    # Relationships
    sender = db.relationship('User', foreign_keys=[sender_id])
    receiver = db.relationship('User', foreign_keys=[receiver_id])
    related_report = db.relationship('HealthReport', foreign_keys=[related_report_id])

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# Registration
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = generate_password_hash(request.form['password'])
        age = request.form['age']
        gender = request.form['gender']
        height = request.form['height']
        weight = request.form['weight']
        role = request.form.get('role', 'user')
        if User.query.filter_by(username=username).first():
            flash('Username already exists.', 'danger')
            return redirect(url_for('register'))
        patient_id = generate_patient_id()
        user = User(username=username, password=password, patient_id=patient_id, age=age, gender=gender, height=height, weight=weight, role=role)
        db.session.add(user)
        db.session.commit()
        
        # Also save to Supabase
        user_data = {
            'id': user.id,
            'username': username,
            'patient_id': patient_id,
            'age': int(age),
            'gender': gender,
            'height': float(height),
            'weight': float(weight),
            'role': role,
            'created_at': datetime.now().isoformat()
        }
        supabase_result = supabase_service.create_user(user_data)
        if supabase_result:
            print(f"✅ User {username} also saved to Supabase")
        else:
            print(f"⚠️ Failed to save user {username} to Supabase")
        
        flash('Registration successful! Please log in.', 'success')
        return redirect(url_for('login'))
    return render_template('register.html')

# Login
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = User.query.filter_by(username=username).first()
        if user and check_password_hash(user.password, password):
            login_user(user)
            if user.role == 'doctor':
                return redirect(url_for('doctor_portal'))
            else:
                return redirect(url_for('dashboard'))
        flash('Invalid username or password.', 'danger')
    return render_template('login.html')

# Doctor Portal - Patient ID Entry
@app.route('/doctor-portal', methods=['GET', 'POST'])
@login_required
def doctor_portal():
    if current_user.role != 'doctor':
        flash('Access denied: Doctors only.', 'danger')
        return redirect(url_for('dashboard'))
    
    if request.method == 'POST':
        patient_id = request.form.get('patient_id', '').strip()
        if patient_id:
            patient = User.query.filter_by(patient_id=patient_id).first()
            if patient:
                return redirect(url_for('patient_records', patient_id=patient_id))
            else:
                flash('Patient ID not found. Please check and try again.', 'danger')
        else:
            flash('Please enter a patient ID.', 'danger')
    
    return render_template('doctor_portal.html')

# Patient Records View
@app.route('/patient-records/<patient_id>')
@login_required
def patient_records(patient_id):
    if current_user.role != 'doctor':
        flash('Access denied: Doctors only.', 'danger')
        return redirect(url_for('dashboard'))
    
    patient = User.query.filter_by(patient_id=patient_id).first()
    if not patient:
        flash('Patient not found.', 'danger')
        return redirect(url_for('doctor_portal'))
    
    # Get all health reports for this patient
    reports = HealthReport.query.filter_by(user_id=patient.id).order_by(HealthReport.timestamp.desc()).all()
    for report in reports:
        report.values_dict = json.loads(report.extracted_values or '{}')
        report.conds_list = json.loads(report.conditions or '[]')
    
    # Get activity logs
    activity_logs = ActivityLog.query.filter_by(user_id=patient.id).order_by(ActivityLog.date.desc()).all()
    
    return render_template('patient_records.html', patient=patient, reports=reports, activity_logs=activity_logs)

# Dashboard
@app.route('/dashboard')
@login_required
def dashboard():
    reports = HealthReport.query.filter_by(user_id=current_user.id).order_by(HealthReport.timestamp.desc()).all()
    for report in reports:
        report.values_dict = json.loads(report.extracted_values or '{}')
        report.conds_list = json.loads(report.conditions or '[]')
    activity_logs = ActivityLog.query.filter_by(user_id=current_user.id).order_by(ActivityLog.date.desc()).all()
    # Dynamically build trend_keys from all extracted keys in all reports
    all_keys = set()
    for report in reports:
        all_keys.update(report.values_dict.keys())
    trend_keys = sorted(all_keys)
    # Build trend data by carrying forward last known value
    trend_data = {}
    reversed_reports = list(reversed(reports))
    for key in trend_keys:
        values = []
        last_value = None
        for r in reversed_reports:
            vals = json.loads(r.extracted_values or '{}')
            if key in vals and vals[key] not in [None, '', 'null']:
                last_value = float(vals[key])
            values.append(last_value if last_value is not None else 0)
        trend_data[key] = values
    trend_labels = [r.timestamp.strftime('%Y-%m-%d') for r in reversed_reports]
    # Report comparison logic (carry forward)
    comparison = {}
    if len(reports) >= 2:
        latest = json.loads(reports[0].extracted_values)
        prev = json.loads(reports[1].extracted_values)
        for key in set(latest.keys()).union(prev.keys()):
            v_new = float(latest.get(key, prev.get(key, 0)))  # Use prev if missing in latest
            v_old = float(prev.get(key, v_new))  # Use latest if missing in prev
            if v_new > v_old:
                status = 'worse'
            elif v_new < v_old:
                status = 'improved'
            else:
                status = 'no_change'
            comparison[key] = {'latest': v_new, 'previous': v_old, 'status': status}
    # Personalized diet chart with explanations (UPGRADED)
    food_df = pd.read_csv('food_data.csv')
    goal = current_user.goal or 'weight_loss'
    diet_chart = []
    latest_conditions = []
    if reports:
        latest_report = reports[0]
        latest_conditions = latest_report.conds_list if hasattr(latest_report, 'conds_list') else json.loads(latest_report.conditions or '[]')
    # Map conditions to food tags
    condition_tags = []
    if latest_conditions:
        for cond in latest_conditions:
            if 'anemia' in cond.lower():
                condition_tags.append('anemia')
            if 'cholesterol' in cond.lower():
                condition_tags.append('cholesterol')
            if 'sugar' in cond.lower() or 'diabetes' in cond.lower():
                condition_tags.append('diabetes')
            if 'triglycerides' in cond.lower():
                condition_tags.append('triglycerides')
    # Always include goal as a tag
    if goal == 'diabetes_control':
        condition_tags.append('diabetes')
    elif goal == 'muscle_gain':
        condition_tags.append('muscle')  # not in csv, but for future
    elif goal == 'weight_loss':
        condition_tags.append('weight_loss')  # not in csv, but for future
    # Enhanced meal plan with better food options and specific reasons
    meal_types = ['Breakfast', 'Lunch', 'Snack', 'Dinner']
    
    # Enhanced meal suggestions with specific health benefits
    meal_suggestions = {
        'Breakfast': {
            'diabetes': ['Oatmeal', 'Greek Yogurt', 'Almonds', 'Berries', 'Cinnamon'],
            'anemia': ['Spinach', 'Eggs', 'Moong Dal Chilla', 'Pomegranate Seeds'],
            'cholesterol': ['Oatmeal', 'Walnuts', 'Flax Seeds', 'Apple'],
            'default': ['Oatmeal', 'Eggs', 'Whole Grain Bread', 'Milk']
        },
        'Lunch': {
            'diabetes': ['Brown Rice', 'Grilled Chicken', 'Mixed Vegetables', 'Quinoa'],
            'anemia': ['Spinach', 'Lentil Soup', 'Chickpeas', 'Beetroot'],
            'cholesterol': ['Fish (Salmon)', 'Brown Rice', 'Steamed Vegetables', 'Oats'],
            'default': ['Brown Rice', 'Grilled Chicken', 'Dal Tadka', 'Mixed Vegetables']
        },
        'Snack': {
            'diabetes': ['Almonds', 'Apple', 'Greek Yogurt', 'Chia Seeds'],
            'anemia': ['Dates', 'Pumpkin Seeds', 'Dark Chocolate', 'Raisins'],
            'cholesterol': ['Walnuts', 'Oatmeal Cookies', 'Fruits', 'Nuts'],
            'default': ['Apple', 'Almonds', 'Cucumber Slices', 'Sprouts Salad']
        },
        'Dinner': {
            'diabetes': ['Grilled Fish', 'Cauliflower Rice', 'Steamed Vegetables', 'Quinoa'],
            'anemia': ['Paneer', 'Spinach Curry', 'Lentil Dal', 'Brown Rice'],
            'cholesterol': ['Tofu', 'Steamed Vegetables', 'Millet', 'Fish Curry'],
            'default': ['Paneer', 'Quinoa', 'Steamed Vegetables', 'Dal Makhani']
        }
    }
    
    for meal in meal_types:
        foods = []
        meal_lower = meal.lower()
        
        # Get foods based on primary condition or goal
        primary_condition = None
        if 'diabetes' in condition_tags:
            primary_condition = 'diabetes'
        elif 'anemia' in condition_tags:
            primary_condition = 'anemia'
        elif 'cholesterol' in condition_tags:
            primary_condition = 'cholesterol'
        
        # Select foods for this meal
        if primary_condition and primary_condition in meal_suggestions[meal]:
            suggested_foods = meal_suggestions[meal][primary_condition]
        else:
            suggested_foods = meal_suggestions[meal]['default']
        
        # Build food list with reasons
        for food in suggested_foods:
            row = food_df[food_df['food'].str.lower() == food.lower()]
            if not row.empty:
                food_data = row.iloc[0]
                suitable = food_data['suitable_for']
                
                # Generate specific reason based on condition
                if primary_condition == 'diabetes':
                    reason = f"Low glycemic index food to help control blood sugar levels"
                elif primary_condition == 'anemia':
                    reason = f"Rich in iron and nutrients to combat anemia"
                elif primary_condition == 'cholesterol':
                    reason = f"Heart-healthy food to help lower cholesterol"
                else:
                    reason = f"Balanced nutrition for overall health and {goal.replace('_', ' ')}"
                
                foods.append({
                    'food': food_data['food'],
                    'calories': food_data['calories'],
                    'reason': reason
                })
        
        # Ensure we have enough foods
        if len(foods) < 2:
            # Add some general healthy foods
            general_foods = ['Apple', 'Almonds', 'Greek Yogurt', 'Quinoa']
            for food in general_foods:
                if len(foods) >= 3:
                    break
                row = food_df[food_df['food'].str.lower() == food.lower()]
                if not row.empty and not any(f['food'] == row.iloc[0]['food'] for f in foods):
                    foods.append({
                        'food': row.iloc[0]['food'],
                        'calories': row.iloc[0]['calories'],
                        'reason': 'General healthy choice for balanced nutrition'
                    })
        
        # Create meal entry
        items = ', '.join([f["food"] for f in foods])
        total_cal = sum([int(f["calories"]) for f in foods])
        
        # Combine reasons intelligently
        if len(set([f["reason"] for f in foods])) == 1:
            combined_reason = foods[0]["reason"]
        else:
            primary_reason = foods[0]["reason"]
            combined_reason = f"{primary_reason} - Additional foods provide variety and balanced nutrition"
        
        diet_chart.append({
            'meal': meal,
            'items': items,
            'calories': total_cal,
            'reason': combined_reason
        })
    
    # Store diet plan in the latest report if available
    if reports and diet_chart:
        latest_report = reports[0]
        latest_report.diet_plan = json.dumps(diet_chart)
        db.session.commit()
    
    # Fun, gamified milestones (dynamic unlocks)
    milestones = []
    # First Report Uploaded
    milestones.append({
        'icon': '🏅',
        'name': 'First Report Uploaded',
        'desc': 'Upload your first medical report',
        'unlocked': len(reports) > 0
    })
    # Step Master
    milestones.append({
        'icon': '🚶‍♂️',
        'name': 'Step Master',
        'desc': 'Walk 10,000 steps in a day',
        'unlocked': any(log.steps and log.steps >= 10000 for log in activity_logs)
    })
    # 7-Day Streak
    streak = 1
    if len(activity_logs) > 1:
        streak = 1
        for i in range(1, len(activity_logs)):
            delta = (activity_logs[i-1].date - activity_logs[i].date).days
            if delta == 1:
                streak += 1
            else:
                break
    milestones.append({
        'icon': '🔥',
        'name': '7-Day Streak',
        'desc': 'Log activity 7 days in a row',
        'unlocked': streak >= 7
    })
    # Diet Pro
    milestones.append({
        'icon': '🥗',
        'name': 'Diet Pro',
        'desc': 'Log your diet for a week',
        'unlocked': len(reports) >= 7
    })
    # Static wellness score and random tip
    wellness_score = 87  # out of 100
    wellness_tips = [
        "Drink plenty of water throughout the day!",
        "Take a short walk every hour to stay active.",
        "Eat a variety of colorful fruits and vegetables.",
        "Prioritize 7-8 hours of sleep each night.",
        "Practice deep breathing or meditation for stress relief.",
        "Celebrate your small health wins!"
    ]
    wellness_tip = random.choice(wellness_tips)
    # Read all test parameter names for display
    param_df = pd.read_csv('medical_test_parameters.csv')
    all_parameters = [row['Test Name'] for _, row in param_df.iterrows()]
    
    # Get unread messages count
    unread_messages = Message.query.filter_by(receiver_id=current_user.id, is_read=False).count()
    
    return render_template('dashboard.html', user=current_user, reports=reports, activity_logs=activity_logs, diet_chart=diet_chart, milestones=milestones, wellness_score=wellness_score, wellness_tip=wellness_tip, comparison=comparison, trend_data=trend_data, trend_labels=trend_labels, all_parameters=all_parameters, unread_messages=unread_messages)

# Upload Medical Report (POST)
@app.route('/upload', methods=['POST'])
@login_required
def upload():
    if 'report_file' not in request.files:
        flash('No file part.', 'danger')
        return redirect(url_for('dashboard'))
    file = request.files['report_file']
    if file.filename == '':
        flash('No selected file.', 'danger')
        return redirect(url_for('dashboard'))
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        save_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(save_path)
        lang = request.form.get('ocr_language', 'eng')
        text = extract_text_from_file(save_path, lang=lang)
        values, conditions = parse_medical_values(text)
        shared = bool(request.form.get('shared_with_doctor'))
        report = HealthReport(
            filename=filename,
            user_id=current_user.id,
            extracted_values=json.dumps(values),
            conditions=json.dumps(conditions),
            diet_plan='{}',
            shared_with_doctor=shared
        )
        db.session.add(report)
        db.session.commit()
        flash('Medical report uploaded and processed successfully!', 'success')
        return redirect(url_for('dashboard'))
    else:
        flash('Invalid file type. Only PDF, JPG, JPEG, PNG allowed.', 'danger')
        return redirect(url_for('dashboard'))

# Activity Log (POST)
@app.route('/activity-log', methods=['POST'])
@login_required
def activity_log():
    steps = request.form.get('steps')
    exercise = request.form.get('exercise')
    calories = request.form.get('calories')
    log = ActivityLog(
        steps=steps,
        exercise=exercise,
        calories=calories,
        user_id=current_user.id
    )
    db.session.add(log)
    db.session.commit()
    flash('Activity log added!', 'success')
    return redirect(url_for('dashboard'))

# Logout
@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Logged out successfully.', 'info')
    return redirect(url_for('login'))

@app.route('/update-goal', methods=['POST'])
@login_required
def update_goal():
    goal = request.form.get('goal')
    if goal in ['weight_loss', 'muscle_gain', 'diabetes_control']:
        current_user.goal = goal
        db.session.commit()
        flash('Health goal updated!', 'success')
    else:
        flash('Invalid goal selected.', 'danger')
    return redirect(url_for('dashboard'))

@app.route('/doctor/comment/<int:report_id>', methods=['POST'])
@login_required
def doctor_comment(report_id):
    if current_user.role != 'doctor':
        flash('Access denied: Doctors only.', 'danger')
        return redirect(url_for('dashboard'))
    
    report = HealthReport.query.get_or_404(report_id)
    comment = request.form.get('doctor_comment', '').strip()
    if comment:
        report.doctor_comment = comment
        report.comment_timestamp = datetime.utcnow()
        
        # Create a message for the patient
        message = Message(
            sender_id=current_user.id,
            receiver_id=report.user_id,
            message_type='comment',
            content=f"Doctor's Comment on {report.filename}: {comment}",
            related_report_id=report.id
        )
        
        db.session.add(message)
        db.session.commit()
        flash('Comment added successfully! Patient will be notified.', 'success')
    else:
        flash('Comment cannot be empty.', 'danger')
    
    # Redirect back to patient records
    patient = User.query.get(report.user_id)
    return redirect(url_for('patient_records', patient_id=patient.patient_id))

# Message management routes
@app.route('/messages')
@login_required
def messages():
    # Get messages for current user
    received_messages = Message.query.filter_by(receiver_id=current_user.id).order_by(Message.timestamp.desc()).all()
    sent_messages = Message.query.filter_by(sender_id=current_user.id).order_by(Message.timestamp.desc()).all()
    
    return jsonify({
        'received': [{
            'id': msg.id,
            'content': msg.content,
            'timestamp': msg.timestamp.strftime('%Y-%m-%d %H:%M'),
            'sender': msg.sender.username,
            'type': msg.message_type,
            'is_read': msg.is_read,
            'related_report': msg.related_report.filename if msg.related_report else None
        } for msg in received_messages],
        'sent': [{
            'id': msg.id,
            'content': msg.content,
            'timestamp': msg.timestamp.strftime('%Y-%m-%d %H:%M'),
            'receiver': msg.receiver.username,
            'type': msg.message_type,
            'related_report': msg.related_report.filename if msg.related_report else None
        } for msg in sent_messages]
    })

@app.route('/mark-message-read/<int:message_id>', methods=['POST'])
@login_required
def mark_message_read(message_id):
    message = Message.query.get_or_404(message_id)
    if message.receiver_id == current_user.id:
        message.is_read = True
        db.session.commit()
        return jsonify({'success': True})
    return jsonify({'success': False, 'error': 'Unauthorized'})

@app.route('/send-message', methods=['POST'])
@login_required
def send_message():
    if current_user.role != 'doctor':
        return jsonify({'success': False, 'error': 'Only doctors can send messages'})
    
    receiver_id = request.json.get('receiver_id')
    content = request.json.get('content')
    message_type = request.json.get('message_type', 'suggestion')
    
    if not receiver_id or not content:
        return jsonify({'success': False, 'error': 'Missing receiver_id or content'})
    
    # Verify receiver exists
    receiver = User.query.get(receiver_id)
    if not receiver:
        return jsonify({'success': False, 'error': 'Receiver not found'})
    
    message = Message(
        sender_id=current_user.id,
        receiver_id=receiver_id,
        message_type=message_type,
        content=content
    )
    
    db.session.add(message)
    db.session.commit()
    
    return jsonify({'success': True, 'message_id': message.id})

# Old doctor dashboard route removed - replaced with new doctor portal system

@app.route('/chatbot/test')
def chatbot_test():
    """Simple test endpoint to verify chatbot is working"""
    return jsonify({
        'status': 'ok',
        'message': 'Chatbot backend is working',
        'timestamp': datetime.utcnow().isoformat()
    })

@app.route('/chatbot/history')
@login_required
def get_chat_history():
    """Get chat history for the current user without sending a message"""
    try:
        chat_history = ChatHistory.query.filter_by(user_id=current_user.id).order_by(ChatHistory.timestamp.desc()).limit(10).all()
        chat_history = list(reversed(chat_history))
        return jsonify({
            'history': [{'message': c.message, 'reply': c.reply, 'timestamp': c.timestamp.strftime('%H:%M')} for c in chat_history]
        })
    except Exception as e:
        print(f'Error retrieving chat history: {e}')
        return jsonify({'error': 'Failed to retrieve chat history'})

@app.route('/chatbot', methods=['POST'])
@login_required
def chatbot():
    user_message = request.json.get('message', '')
    
    print(f"Chatbot called with message: {user_message}")
    print(f"Current user: {current_user.username} (ID: {current_user.id})")
    
    if not user_message.strip():
        return jsonify({'error': 'Message cannot be empty'})
    
    # Initialize reply variable
    reply = "Sorry, I couldn't process your request."
    
    try:
        # Gather user context
        reports = HealthReport.query.filter_by(user_id=current_user.id).order_by(HealthReport.timestamp.desc()).all()
        latest_report = reports[0] if reports else None
        
        # Get diet plan from latest report
        diet_chart = None
        if latest_report and latest_report.diet_plan:
            try:
                diet_chart = json.loads(latest_report.diet_plan)
            except Exception:
                diet_chart = None
        
        # Get recent activity logs
        activity_logs = ActivityLog.query.filter_by(user_id=current_user.id).order_by(ActivityLog.date.desc()).limit(5).all()
        
        # Build context string - keep it concise to avoid token limits
        context_parts = []
        context_parts.append(f"User: {current_user.username}, Age: {current_user.age if current_user.age else 'N/A'}, Goal: {current_user.goal if current_user.goal else 'N/A'}")
        
        if latest_report:
            try:
                extracted_values = json.loads(latest_report.extracted_values or '{}')
                if extracted_values:
                    # Only include key values, limit to 3-4 most important
                    key_values = list(extracted_values.items())[:3]
                    context_parts.append(f"Health Data: {', '.join([f'{k}={v}' for k, v in key_values])}")
                
                conditions = json.loads(latest_report.conditions or '[]')
                if conditions:
                    context_parts.append(f"Conditions: {', '.join(conditions[:2])}")  # Limit to 2 conditions
            except Exception as e:
                print(f"Error parsing report data: {e}")
        
        if activity_logs:
            # Only include most recent activity
            latest_log = activity_logs[0]
            context_parts.append(f"Recent: {latest_log.steps} steps, {latest_log.exercise}")
        
        # Build context string
        context = " | ".join(context_parts)
        print(f"Context length: {len(context)} characters")
        
        # Build chat history string - limit to last 3 exchanges
        history_str = ""
        if chat_history:
            recent_history = chat_history[-3:]  # Only last 3 exchanges
            history_str = " | ".join([f"Q: {c.message} A: {c.reply[:50]}..." for c in recent_history])
        
        # Compose concise prompt for LLM
        system_prompt = "You are a health assistant. Answer based ONLY on the user's data provided. Keep responses under 100 words."
        
        user_prompt = f"Context: {context}\n\nQuestion: {user_message}\n\nAnswer based ONLY on the user's data above:"
        
        print(f"Calling OpenRouter API...")
        
        # Call DeepSeek LLM via OpenRouter
        headers = {
            'Authorization': f'Bearer {OPENROUTER_API_KEY}',
            'Content-Type': 'application/json',
        }
        
        data = {
            'model': 'deepseek/deepseek-r1-0528:free',
            'messages': [
                {'role': 'system', 'content': system_prompt},
                {'role': 'user', 'content': user_prompt}
            ],
            'max_tokens': 150  # Reduced from 512 to avoid hitting limits
        }
        
        print(f"API Key: {OPENROUTER_API_KEY[:20]}...")
        print(f"Request data: {json.dumps(data, indent=2)}")
        
        try:
            response = requests.post('https://openrouter.ai/api/v1/chat/completions', 
                                   headers=headers, json=data, timeout=30)
            
            print(f"OpenRouter response status: {response.status_code}")
            
            if response.status_code == 200:
                response_data = response.json()
                print(f"Response JSON: {json.dumps(response_data, indent=2)}")
                
                if 'choices' in response_data and len(response_data['choices']) > 0:
                    reply = response_data['choices'][0]['message']['content']
                    print(f"Generated reply: {reply[:100]}...")
                    
                    # Check if reply is empty or too short
                    if not reply or len(reply.strip()) < 10:
                        print("API returned empty/short response, using fallback")
                        reply = f"Based on your data: {context}. You have a {current_user.goal} goal. Your latest health data shows good activity levels. For specific health questions, please consult your healthcare provider."
                else:
                    print("No choices in response")
                    reply = 'Sorry, the AI response was incomplete. Please try again.'
            else:
                print(f'OpenRouter API error: {response.status_code}, {response.text}')
                reply = f'API Error {response.status_code}: {response.text[:100]}'
                
        except requests.exceptions.Timeout:
            print("Request timed out")
            reply = 'Sorry, the request timed out. Please try again.'
        except requests.exceptions.ConnectionError as e:
            print(f"Connection error: {e}")
            reply = 'Sorry, there was a connection error. Please check your internet connection.'
        except requests.exceptions.RequestException as e:
            print(f"Request error: {e}")
            reply = f'Request error: {str(e)}'
        except json.JSONDecodeError as e:
            print(f"JSON decode error: {e}")
            reply = 'Sorry, there was an error parsing the response.'
        except Exception as e:
            print(f"Unexpected error in API call: {e}")
            reply = f'Unexpected error: {str(e)}'
            
    except Exception as e:
        print(f'Error in chatbot: {e}')
        reply = 'Sorry, an error occurred. Please try again.'
    
    # Ensure reply is always defined
    if 'reply' not in locals():
        reply = "Sorry, I couldn't process your request."
    
    # Fallback response if API fails completely
    if "error" in reply.lower():
        print("Using fallback response system")
        if latest_report:
            try:
                extracted_values = json.loads(latest_report.extracted_values or '{}')
                if extracted_values:
                    reply = f"Based on your latest medical report from {latest_report.timestamp.strftime('%Y-%m-%d')}, I can see your health data. However, I'm experiencing technical difficulties with the AI service. Please try again later or contact support if the issue persists."
                else:
                    reply = "I can see your medical report but I'm experiencing technical difficulties. Please try again later."
            except:
                reply = "I'm experiencing technical difficulties. Please try again later."
        else:
            reply = "I'm experiencing technical difficulties. Please try again later."
    
    print(f"Final reply: {reply}")
    
    # Store chat history
    try:
        chat = ChatHistory(user_id=current_user.id, message=user_message, reply=reply)
        db.session.add(chat)
        db.session.commit()
        print("Chat history stored successfully")
    except Exception as e:
        print(f'Error storing chat history: {e}')
    
    # Return updated chat history
    try:
        chat_history = ChatHistory.query.filter_by(user_id=current_user.id).order_by(ChatHistory.timestamp.desc()).limit(10).all()
        chat_history = list(reversed(chat_history))
        result = {
            'history': [{'message': c.message, 'reply': c.reply, 'timestamp': c.timestamp.strftime('%H:%M')} for c in chat_history]
        }
        print(f"Returning {len(result['history'])} chat history entries")
        return jsonify(result)
    except Exception as e:
        print(f'Error retrieving chat history: {e}')
        return jsonify({'error': 'Failed to retrieve chat history'})

@app.route('/upload-profile-image', methods=['POST'])
@login_required
def upload_profile_image():
    if 'profile_image' not in request.files:
        flash('No file part.', 'danger')
        return redirect(url_for('dashboard'))
    file = request.files['profile_image']
    if file.filename == '':
        flash('No selected file.', 'danger')
        return redirect(url_for('dashboard'))
    if file and file.filename.lower().rsplit('.', 1)[1] in {'jpg', 'jpeg', 'png'}:
        filename = secure_filename(f"user_{current_user.id}_profile.{file.filename.rsplit('.', 1)[1].lower()}")
        save_dir = os.path.join(app.config['UPLOAD_FOLDER'], 'profile_images')
        os.makedirs(save_dir, exist_ok=True)
        save_path = os.path.join(save_dir, filename)
        file.save(save_path)
        current_user.profile_image = f'uploads/profile_images/{filename}'
        db.session.commit()
        flash('Profile image updated!', 'success')
    else:
        flash('Invalid file type. Only JPG/PNG allowed.', 'danger')
    return redirect(url_for('dashboard'))

@app.route('/')
def home():
    return redirect(url_for('login'))

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True) 