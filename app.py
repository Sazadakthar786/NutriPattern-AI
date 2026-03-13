from flask import Flask, render_template, redirect, url_for, request, flash, jsonify, send_file
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import os
from werkzeug.utils import secure_filename
import random
import pdfplumber
import cv2
import numpy as np

# Try to import pytesseract and easyocr, make them optional
PYTESSERACT_AVAILABLE = False
EASYOCR_AVAILABLE = False

# Check if tesseract command is available (more reliable than importing pytesseract)
import subprocess
try:
    result = subprocess.run(['tesseract', '--version'], capture_output=True, text=True, timeout=2)
    if result.returncode == 0:
        PYTESSERACT_AVAILABLE = True
except (FileNotFoundError, subprocess.TimeoutExpired, Exception):
    PYTESSERACT_AVAILABLE = False

# Try to import pytesseract for actual usage (may fail on Python 3.14 but tesseract command works)
try:
    import pytesseract
except (ImportError, Exception):
    # pytesseract import failed, but we can use subprocess as fallback
    pass

try:
    import easyocr
    EASYOCR_AVAILABLE = True
except ImportError:
    EASYOCR_AVAILABLE = False
import json
import pandas as pd
from io import BytesIO
from nutri_report_generator import generate_patient_report

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

# OpenRouter API key from environment (do not hardcode secrets)
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")

import requests

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def extract_text_with_tesseract(filepath, lang='eng'):
    """Extract text using tesseract with OpenCV preprocessing for reliable OCR."""
    try:
        import pytesseract
        img = cv2.imread(filepath)
        if img is None:
            print(f"OpenCV could not read image: {filepath}")
            return ""
        # Preprocess: grayscale -> Gaussian blur -> adaptive threshold
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        blur = cv2.GaussianBlur(gray, (5, 5), 0)
        thresh = cv2.adaptiveThreshold(
            blur, 255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY,
            11, 2
        )
        # Run OCR on processed image; PSM 6 = uniform block of text (tables)
        text = pytesseract.image_to_string(thresh, lang=lang, config="--psm 6")
        # Save OCR output for debugging
        try:
            with open("ocr_debug.txt", "w", encoding="utf-8") as f:
                f.write(text)
        except Exception as e:
            print(f"Could not write ocr_debug.txt: {e}")
        return text
    except (ImportError, Exception):
        # Fallback to subprocess if pytesseract import failed
        try:
            import tempfile
            from PIL import Image

            img = Image.open(filepath)
            with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp:
                img.save(tmp.name)
                tmp_path = tmp.name

            try:
                result = subprocess.run(
                    ['tesseract', tmp_path, 'stdout', '-l', lang, '--psm', '6'],
                    capture_output=True,
                    text=True,
                    timeout=30
                )
                if result.returncode == 0:
                    text = result.stdout
                    try:
                        with open("ocr_debug.txt", "w", encoding="utf-8") as f:
                            f.write(text)
                    except Exception:
                        pass
                    return text
                else:
                    print(f"Tesseract error: {result.stderr}")
                    return ""
            finally:
                if os.path.exists(tmp_path):
                    os.unlink(tmp_path)
        except Exception as e:
            print(f"Tesseract subprocess failed: {e}")
            return ""

def extract_text_from_file(filepath, lang='eng'):
    ext = os.path.splitext(filepath)[1].lower()
    text = ''
    
    if not os.path.exists(filepath):
        print(f"Error: File not found: {filepath}")
        return text
    
    try:
        if ext == '.pdf':
            print(f"Processing PDF file: {filepath}")
            try:
                with pdfplumber.open(filepath) as pdf:
                    print(f"PDF has {len(pdf.pages)} pages")
                    for i, page in enumerate(pdf.pages):
                        tables = page.extract_tables()
                        if tables:
                            for table in tables:
                                for row in table:
                                    text += " ".join([str(cell) for cell in row if cell]) + "\n"
                        else:
                            text += page.extract_text() or ""
                    if text.strip():
                        print(f"Extracted {len(text)} characters from PDF (tables/text)")
            except Exception as e:
                print(f"Error reading PDF with pdfplumber: {e}")
                text = ''

            # If no text extracted, try OCR for scanned PDFs
            if not text.strip():
                print("No text extracted from PDF, trying OCR...")
                if PYTESSERACT_AVAILABLE:
                    try:
                        from pdf2image import convert_from_path
                        print("Converting PDF to images...")
                        images = convert_from_path(filepath)
                        print(f"Converted to {len(images)} images")
                        for i, img in enumerate(images):
                            import tempfile
                            with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp:
                                img.save(tmp.name)
                                tmp_path = tmp.name
                            try:
                                img_text = extract_text_with_tesseract(tmp_path, lang)
                                text += img_text
                                if img_text:
                                    print(f"OCR extracted {len(img_text)} characters from image {i+1}")
                            finally:
                                if os.path.exists(tmp_path):
                                    os.unlink(tmp_path)
                    except Exception as e:
                        print(f"PDF OCR failed: {e}")
                        import traceback
                        traceback.print_exc()
                else:
                    print("Pytesseract not available for PDF OCR")
            else:
                print(f"Successfully extracted {len(text)} characters from PDF")
                
        elif ext in ['.jpg', '.jpeg', '.png']:
            print(f"Processing image file: {filepath}")
            try:
                # Try easyocr first if available (usually more accurate)
                if EASYOCR_AVAILABLE:
                    print("Using EasyOCR for text extraction...")
                    try:
                        reader = easyocr.Reader([lang], gpu=False)
                        result = reader.readtext(filepath, detail=0)
                        text = '\n'.join(result)
                        print(f"EasyOCR extracted {len(text)} characters")
                    except Exception as e:
                        print(f"EasyOCR failed: {e}, trying pytesseract...")
                        if PYTESSERACT_AVAILABLE:
                            text = extract_text_with_tesseract(filepath, lang)
                            print(f"Tesseract extracted {len(text)} characters")
                        else:
                            text = ""
                            print("No OCR library available")
                elif PYTESSERACT_AVAILABLE:
                    print("Using Tesseract for text extraction...")
                    text = extract_text_with_tesseract(filepath, lang)
                    print(f"Tesseract extracted {len(text)} characters")
                else:
                    text = ""
                    print("No OCR library available. Install pytesseract or easyocr.")
                    print("Install with: pip install pytesseract easyocr")
            except Exception as e:
                print(f"OCR failed: {e}")
                import traceback
                traceback.print_exc()
                text = ""
        else:
            print(f"Unsupported file extension: {ext}")
            
    except Exception as e:
        print(f"Unexpected error in extract_text_from_file: {e}")
        import traceback
        traceback.print_exc()
        text = ""
    
    return text

def parse_medical_values(text):
    import re
    import pandas as pd
    values = {}

    if not text or not text.strip():
        print("Warning: No text extracted from file")
        return values, []

    # Save OCR/text output for debugging
    try:
        with open("ocr_debug.txt", "w", encoding="utf-8") as f:
            f.write(text)
    except Exception as e:
        print(f"Could not write ocr_debug.txt: {e}")

    print('--- Extracted Text Start ---')
    print(text[:500] if len(text) > 500 else text)
    print('--- Extracted Text End ---')

    try:
        param_df = pd.read_csv('medical_test_parameters.csv')
    except Exception as e:
        print(f"Error loading CSV: {e}")
        return values, []

    # Common abbreviations for matching
    abbrev_map = {
        'Hemoglobin (Hb)': ['Hemoglobin', 'Hb', 'HGB', 'Hgb'],
        'RBC Count': ['RBC Count', 'RBC', 'Red Blood Cell'],
        'WBC Count': ['WBC Count', 'WBC', 'White Blood Cell'],
        'Platelet Count': ['Platelet Count', 'Platelets', 'PLT'],
        'Hematocrit (HCT)': ['Hematocrit', 'HCT', 'Hct'],
        'MCV': ['MCV'],
        'MCH': ['MCH'],
        'MCHC': ['MCHC'],
        'RDW': ['RDW'],
        'Neutrophils (%)': ['Neutrophils', 'Neutrophil'],
        'Lymphocytes (%)': ['Lymphocytes', 'Lymphocyte'],
        'Monocytes (%)': ['Monocytes', 'Monocyte'],
        'Eosinophils (%)': ['Eosinophils', 'Eosinophil'],
        'Basophils (%)': ['Basophils', 'Basophil'],
        'SGOT / AST': ['SGOT', 'AST', 'Aspartate'],
        'SGPT / ALT': ['SGPT', 'ALT', 'Alanine'],
        'ALP': ['ALP', 'Alkaline Phosphatase'],
        'Total Bilirubin': ['Total Bilirubin', 'Bilirubin', 'T.Bilirubin', 'TBil'],
        'Direct Bilirubin': ['Direct Bilirubin', 'D.Bilirubin', 'DBil'],
        'Albumin': ['Albumin', 'ALB'],
        'Globulin': ['Globulin', 'GLOB'],
        'A/G Ratio': ['A/G Ratio', 'A:G', 'AG Ratio'],
        'Creatinine': ['Creatinine', 'CREA', 'CREAT'],
        'Urea / BUN': ['Urea', 'BUN', 'Blood Urea Nitrogen'],
        'Uric Acid': ['Uric Acid', 'Uric', 'UA'],
        'Sodium (Na+)': ['Sodium', 'Na+', 'Na'],
        'Potassium (K+)': ['Potassium', 'K+', 'K'],
        'Chloride (Cl-)': ['Chloride', 'Cl-', 'Cl'],
        'Fasting Blood Sugar (FBS)': ['Fasting Blood Sugar', 'FBS', 'Fasting Glucose', 'FBG'],
        'Postprandial Blood Sugar (PPBS)': ['Postprandial Blood Sugar', 'PPBS', 'PP Glucose', 'PPG'],
        'HbA1c': ['HbA1c', 'HBA1C', 'A1C', 'Glycated Hemoglobin'],
        'Random Blood Sugar (RBS)': ['Random Blood Sugar', 'RBS', 'Random Glucose', 'RBG'],
        'Insulin (Fasting)': ['Insulin', 'Fasting Insulin'],
        'Total Cholesterol': ['Total Cholesterol', 'Cholesterol', 'CHOL', 'TC'],
        'HDL': ['HDL', 'High Density Lipoprotein'],
        'LDL': ['LDL', 'Low Density Lipoprotein'],
        'VLDL': ['VLDL', 'Very Low Density Lipoprotein'],
        'Triglycerides': ['Triglycerides', 'TG', 'TRIG'],
        'Cholesterol/HDL Ratio': ['Cholesterol/HDL Ratio', 'CHOL/HDL', 'TC/HDL'],
        'Vitamin D (25-OH)': ['Vitamin D', '25-OH', '25OH', 'Vit D'],
        'Vitamin B12': ['Vitamin B12', 'B12', 'Vit B12', 'Cobalamin'],
        'Calcium': ['Calcium', 'Ca'],
        'Iron': ['Iron', 'Fe'],
        'Ferritin': ['Ferritin', 'FER'],
        'TIBC': ['TIBC', 'Total Iron Binding Capacity'],
        'Magnesium': ['Magnesium', 'Mg'],
        'Phosphorus': ['Phosphorus', 'Phos', 'P'],
        'TSH': ['TSH', 'Thyroid Stimulating Hormone'],
        'T3': ['T3', 'Triiodothyronine'],
        'T4': ['T4', 'Thyroxine'],
        'Free T3': ['Free T3', 'FT3', 'Free Triiodothyronine'],
        'Free T4': ['Free T4', 'FT4', 'Free Thyroxine'],
    }
    
    # Line-by-line extraction to avoid capturing reference range numbers from other lines
    lines = text.split("\n")

    for idx, row in param_df.iterrows():
        param = row['Test Name']
        key = param.lower().replace(' ', '_').replace('(', '').replace(')', '').replace('/', '_').replace('%', 'percent').replace('-', '_').replace('.', '').replace(',', '').replace('__', '_')

        if key in values:
            continue

        # Stricter patterns: numbers immediately after test name; optional unit capture
        names = abbrev_map.get(param, [param])
        names = sorted(names, key=len, reverse=True)
        patterns = []
        unit_pattern = r"\s*(mg/dL|g/dL|mmol/L|IU/L|%)?"
        for name in names:
            patterns.append((rf"{re.escape(name)}\s*[:-]?\s*([\d.]+){unit_pattern}", True))   # with unit
            patterns.append((rf"{re.escape(name)}\s*[:-]?\s*([\d]+\.\d+)", False))
            patterns.append((rf"{re.escape(name)}\s*[:-]?\s*(\d+)", False))
        patterns.append((rf"{re.escape(param)}\s*[:-]?\s*([\d.]+){unit_pattern}", True))
        patterns.append((rf"{re.escape(param)}\s*[:-]?\s*([\d]+\.\d+)", False))
        patterns.append((rf"{re.escape(param)}\s*[:-]?\s*(\d+)", False))

        found = False
        for pat, has_unit in patterns:
            if found:
                break
            for line in lines:
                m = re.search(pat, line, re.IGNORECASE)
                if m:
                    value_str = m.group(1)
                    if not value_str:
                        continue
                    unit_str = m.group(2) if has_unit and m.lastindex >= 2 and m.group(2) else None
                    try:
                        value_float = float(value_str.replace(',', '.'))
                    except ValueError:
                        continue
                    # Value validation to reject OCR mistakes and reference range numbers
                    if value_float > 1000:
                        continue
                    if "hemoglobin" in key and not (3 <= value_float <= 25):
                        continue
                    if "globulin" in key and not (0 <= value_float <= 10):
                        continue
                    if "uric_acid" in key and not (1 <= value_float <= 20):
                        continue
                    if "cholesterol" in key and "ratio" not in key and not (50 <= value_float <= 400):
                        continue
                    values[key] = value_str
                    if unit_str:
                        values[key + "_unit"] = unit_str
                    print(f"Extracted {param}: {value_str}")
                    found = True
                    break
            if found:
                break

    print(f"Extracted parameters: {list(values.keys())}")
    
    # Condition detection - use actual keys from values dict
    conditions = []
    try:
        # Check for high blood sugar (check all sugar-related keys)
        sugar_keys = [k for k in values.keys() if 'sugar' in k or 'glucose' in k or 'fbs' in k or 'ppbs' in k or 'rbs' in k or 'hba1c' in k]
        for sugar_key in sugar_keys:
            try:
                val = float(values[sugar_key])
                if 'fbs' in sugar_key or 'fasting' in sugar_key:
                    if val > 100:
                        conditions.append('High Blood Sugar (Fasting)')
                elif 'ppbs' in sugar_key or 'postprandial' in sugar_key:
                    if val > 140:
                        conditions.append('High Blood Sugar (Postprandial)')
                elif 'hba1c' in sugar_key:
                    if val > 5.6:
                        conditions.append('Pre-diabetes or Diabetes (High HbA1c)')
                elif 'rbs' in sugar_key or 'random' in sugar_key:
                    if val > 140:
                        conditions.append('High Blood Sugar (Random)')
            except (ValueError, KeyError):
                continue
        
        # Check for high cholesterol
        chol_keys = [k for k in values.keys() if 'cholesterol' in k and 'ratio' not in k]
        for chol_key in chol_keys:
            try:
                val = float(values[chol_key])
                if val > 200:
                    conditions.append('High Cholesterol')
            except (ValueError, KeyError):
                continue
        
        # Check for anemia (low hemoglobin)
        hb_keys = [k for k in values.keys() if 'hemoglobin' in k or 'hb' in k]
        for hb_key in hb_keys:
            try:
                val = float(values[hb_key])
                if val < 12:
                    conditions.append('Anemia (Low Hemoglobin)')
            except (ValueError, KeyError):
                continue
        
        # Check for high triglycerides
        trig_keys = [k for k in values.keys() if 'triglyceride' in k]
        for trig_key in trig_keys:
            try:
                val = float(values[trig_key])
                if val > 150:
                    conditions.append('High Triglycerides')
            except (ValueError, KeyError):
                continue
                
    except Exception as e:
        print(f"Error in condition detection: {e}")
    
    return values, conditions

def analyze_dietary_needs(extracted_values, param_df, user_gender=None):
    """
    Analyze medical parameters to determine specific dietary needs.
    Returns a dictionary with dietary requirements.
    """
    needs = {
        'needs_iron': False,
        'needs_cholesterol_control': False,
        'needs_sugar_control': False,
        'needs_triglyceride_control': False,
        'needs_protein': False,
        'needs_calcium': False,
        'needs_vitamin_d': False,
        'specific_recommendations': []
    }
    
    if not extracted_values or len(extracted_values) == 0:
        return needs
    
    import re
    
    # Gender mapping
    gender_map = {'male': 'M', 'm': 'M', 'female': 'F', 'f': 'F'}
    user_gender_code = gender_map.get(user_gender.lower() if user_gender else '', '') if user_gender else ''
    
    # Check each parameter
    for idx, row in param_df.iterrows():
        param_name = row['Test Name']
        normal_range_str = str(row['Normal Range'])
        
        # Convert parameter name to key format
        key = param_name.lower().replace(' ', '_').replace('(', '').replace(')', '').replace('/', '_').replace('%', 'percent').replace('-', '_').replace('.', '').replace(',', '').replace('__', '_')
        
        if key not in extracted_values:
            continue
        
        try:
            value = float(extracted_values[key])
            
            # Hemoglobin - check for anemia
            if 'hemoglobin' in key or 'hb' in key:
                range_str_clean = normal_range_str.replace(',', '')
                if user_gender_code == 'M':
                    m_match = re.search(r'([\d.]+)[–-]([\d.]+)[^)]*\(M\)', range_str_clean)
                    if m_match:
                        min_val = float(m_match.group(1))
                        if value < min_val:
                            needs['needs_iron'] = True
                            needs['specific_recommendations'].append(f"Hemoglobin is {value:.1f} (low), focus on iron-rich foods")
                elif user_gender_code == 'F':
                    f_match = re.search(r'([\d.]+)[–-]([\d.]+)[^)]*\(F\)', range_str_clean)
                    if f_match:
                        min_val = float(f_match.group(1))
                        if value < min_val:
                            needs['needs_iron'] = True
                            needs['specific_recommendations'].append(f"Hemoglobin is {value:.1f} (low), focus on iron-rich foods")
            
            # Blood Sugar - check for diabetes/pre-diabetes
            elif 'sugar' in key or 'glucose' in key or 'fbs' in key or 'ppbs' in key or 'rbs' in key:
                if 'fbs' in key or 'fasting' in key:
                    if value > 100:
                        needs['needs_sugar_control'] = True
                        needs['specific_recommendations'].append(f"Fasting Blood Sugar is {value:.1f} (high), choose low glycemic foods")
                elif 'ppbs' in key or 'postprandial' in key:
                    if value > 140:
                        needs['needs_sugar_control'] = True
                        needs['specific_recommendations'].append(f"Postprandial Blood Sugar is {value:.1f} (high), control meal portions")
                elif 'hba1c' in key:
                    if value > 5.6:
                        needs['needs_sugar_control'] = True
                        needs['specific_recommendations'].append(f"HbA1c is {value:.1f}% (high), maintain consistent meal timing")
            
            # Cholesterol
            elif 'cholesterol' in key and 'ratio' not in key and 'hdl' not in key and 'ldl' not in key and 'vldl' not in key:
                if value > 200:
                    needs['needs_cholesterol_control'] = True
                    needs['specific_recommendations'].append(f"Total Cholesterol is {value:.1f} (high), choose heart-healthy foods")
            elif 'ldl' in key:
                if value > 100:
                    needs['needs_cholesterol_control'] = True
                    needs['specific_recommendations'].append(f"LDL is {value:.1f} (high), reduce saturated fats")
            elif 'hdl' in key:
                if value < 40:
                    needs['needs_cholesterol_control'] = True
                    needs['specific_recommendations'].append(f"HDL is {value:.1f} (low), include healthy fats and exercise")
            
            # Triglycerides
            elif 'triglyceride' in key:
                if value > 150:
                    needs['needs_triglyceride_control'] = True
                    needs['specific_recommendations'].append(f"Triglycerides are {value:.1f} (high), reduce refined carbs and sugars")
            
            # Calcium
            elif 'calcium' in key:
                range_match = re.search(r'([\d.]+)[–-]([\d.]+)', normal_range_str.replace(',', ''))
                if range_match:
                    min_val = float(range_match.group(1))
                    if value < min_val:
                        needs['needs_calcium'] = True
                        needs['specific_recommendations'].append(f"Calcium is {value:.1f} (low), include dairy and leafy greens")
            
            # Vitamin D
            elif 'vitamin_d' in key or '25-oh' in key:
                range_match = re.search(r'([\d.]+)[–-]([\d.]+)', normal_range_str.replace(',', ''))
                if range_match:
                    min_val = float(range_match.group(1))
                    if value < min_val:
                        needs['needs_vitamin_d'] = True
                        needs['specific_recommendations'].append(f"Vitamin D is {value:.1f} (low), include fortified foods and sunlight exposure")
            
            # Iron
            elif 'iron' in key and 'ferritin' not in key and 'tibc' not in key:
                range_match = re.search(r'([\d.]+)[–-]([\d.]+)', normal_range_str.replace(',', ''))
                if range_match:
                    min_val = float(range_match.group(1))
                    if value < min_val:
                        needs['needs_iron'] = True
                        needs['specific_recommendations'].append(f"Iron is {value:.1f} (low), include iron-rich foods with vitamin C")
                        
        except (ValueError, TypeError):
            continue
    
    return needs

def calculate_wellness_score(reports, user_gender=None):
    """
    Calculate wellness score based on medical parameters from reports.
    Returns a score from 0-100 based on how many parameters are within normal range.
    """
    if not reports or len(reports) == 0:
        return 50  # Default score if no reports
    
    # Get the latest report
    latest_report = reports[0]
    try:
        extracted_values = json.loads(latest_report.extracted_values or '{}')
    except (json.JSONDecodeError, TypeError):
        return 50  # Default if no values
    
    if not extracted_values or len(extracted_values) == 0:
        return 50  # Default if no values extracted

    # Use path relative to app file so CSV is found regardless of cwd
    csv_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'medical_test_parameters.csv')
    try:
        param_df = pd.read_csv(csv_path)
    except Exception as e:
        print(f"Error loading CSV for wellness calculation: {e}")
        return 50
    
    import re
    
    # Parse normal ranges and check values
    checked_params = 0
    normal_params = 0
    slightly_abnormal = 0
    severely_abnormal = 0
    
    # Gender mapping
    gender_map = {'male': 'M', 'm': 'M', 'female': 'F', 'f': 'F'}
    user_gender_code = gender_map.get(user_gender.lower() if user_gender else '', '') if user_gender else ''
    
    for idx, row in param_df.iterrows():
        param_name = row['Test Name']
        normal_range_str = str(row['Normal Range'])
        
        # Convert parameter name to key format (same as in parse_medical_values)
        key = param_name.lower().replace(' ', '_').replace('(', '').replace(')', '').replace('/', '_').replace('%', 'percent').replace('-', '_').replace('.', '').replace(',', '').replace('__', '_')

        if key not in extracted_values or key.endswith('_unit'):
            continue

        try:
            value = float(extracted_values[key])
            checked_params += 1
            
            # Parse normal range
            is_normal = False
            severity = 0  # 0=normal, 1=slightly abnormal, 2=severely abnormal
            
            # Handle gender-specific ranges
            if '(M)' in normal_range_str and '(F)' in normal_range_str:
                # Remove commas and extract ranges
                range_str_clean = normal_range_str.replace(',', '')
                if user_gender_code == 'M':
                    # Extract male range - more flexible pattern
                    m_match = re.search(r'([\d.]+)[–-]([\d.]+)[^)]*\(M\)', range_str_clean)
                    if m_match:
                        min_val, max_val = float(m_match.group(1)), float(m_match.group(2))
                        if min_val <= value <= max_val:
                            is_normal = True
                        else:
                            deviation = min(abs(value - min_val), abs(value - max_val)) / max_val if max_val > 0 else 1.0
                            severity = 1 if deviation < 0.2 else 2
                elif user_gender_code == 'F':
                    # Extract female range - more flexible pattern
                    f_match = re.search(r'([\d.]+)[–-]([\d.]+)[^)]*\(F\)', range_str_clean)
                    if f_match:
                        min_val, max_val = float(f_match.group(1)), float(f_match.group(2))
                        if min_val <= value <= max_val:
                            is_normal = True
                        else:
                            deviation = min(abs(value - min_val), abs(value - max_val)) / max_val if max_val > 0 else 1.0
                            severity = 1 if deviation < 0.2 else 2
                else:
                    # No gender specified, try to parse first range found
                    range_str_clean = normal_range_str.replace(',', '')
                    range_match = re.search(r'([\d.]+)[–-]([\d.]+)', range_str_clean)
                    if range_match:
                        min_val, max_val = float(range_match.group(1)), float(range_match.group(2))
                        if min_val <= value <= max_val:
                            is_normal = True
                        else:
                            deviation = min(abs(value - min_val), abs(value - max_val)) / max_val if max_val > 0 else 1.0
                            severity = 1 if deviation < 0.2 else 2
            # Handle "Less than" ranges (case-insensitive)
            elif 'less than' in normal_range_str.lower() or '<' in normal_range_str:
                max_match = re.search(r'[<\s]*(?:less\s+than\s+)?([\d.]+)', normal_range_str, re.IGNORECASE)
                if max_match:
                    max_val = float(max_match.group(1))
                    if value <= max_val:
                        is_normal = True
                    else:
                        deviation = (value - max_val) / max_val
                        severity = 1 if deviation < 0.2 else 2
            # Handle standard ranges (e.g., "5–40", "70-100", "4,500–11,000")
            else:
                # Remove commas from range string for parsing
                range_str_clean = normal_range_str.replace(',', '')
                range_match = re.search(r'([\d.]+)[–-]([\d.]+)', range_str_clean)
                if range_match:
                    min_val, max_val = float(range_match.group(1)), float(range_match.group(2))
                    if min_val <= value <= max_val:
                        is_normal = True
                    else:
                        # Calculate deviation percentage
                        if value < min_val:
                            deviation = (min_val - value) / min_val if min_val > 0 else 1.0
                        else:
                            deviation = (value - max_val) / max_val if max_val > 0 else 1.0
                        severity = 1 if deviation < 0.2 else 2
            
            if is_normal:
                normal_params += 1
            elif severity == 1:
                slightly_abnormal += 1
            else:
                severely_abnormal += 1
                
        except (ValueError, TypeError) as e:
            continue
    
    if checked_params == 0:
        return 50  # No parameters checked

    # Credit-based formula: normal=100%, slight=70%, severe=40% (more balanced than penalty-only)
    base_score = (normal_params * 100 + slightly_abnormal * 70 + severely_abnormal * 40) / checked_params

    wellness_score = min(100, round(base_score))
    if normal_params == checked_params:
        wellness_score = 100

    print(f"Wellness: checked={checked_params}, normal={normal_params}, slight={slightly_abnormal}, severe={severely_abnormal} -> score={wellness_score}")
    return wellness_score

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
    return db.session.get(User, int(user_id))

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
        try:
            report.values_dict = json.loads(report.extracted_values or '{}')
        except (json.JSONDecodeError, TypeError):
            report.values_dict = {}
        try:
            report.conds_list = json.loads(report.conditions or '[]')
        except (json.JSONDecodeError, TypeError):
            report.conds_list = []
    
    activity_logs = ActivityLog.query.filter_by(user_id=current_user.id).order_by(ActivityLog.date.desc()).all()
    
    # Dynamically build trend_keys from all extracted keys in all reports
    all_keys = set()
    for report in reports:
        if hasattr(report, 'values_dict') and report.values_dict:
            all_keys.update(report.values_dict.keys())
    trend_keys = sorted(all_keys)
    
    # Build trend data by carrying forward last known value
    trend_data = {}
    reversed_reports = list(reversed(reports))
    for key in trend_keys:
        values = []
        last_value = None
        for r in reversed_reports:
            try:
                vals = json.loads(r.extracted_values or '{}')
                if key in vals and vals[key] not in [None, '', 'null', '']:
                    try:
                        last_value = float(vals[key])
                    except (ValueError, TypeError):
                        pass
            except (json.JSONDecodeError, TypeError):
                vals = {}
            values.append(last_value if last_value is not None else 0)
        trend_data[key] = values
    
    trend_labels = [r.timestamp.strftime('%Y-%m-%d') for r in reversed_reports] if reversed_reports else []
    
    # Report comparison logic (carry forward)
    # Show comparison if we have at least 2 reports, or show latest values if only 1 report
    comparison = {}
    if len(reports) >= 2:
        try:
            latest = json.loads(reports[0].extracted_values or '{}')
        except (json.JSONDecodeError, TypeError):
            latest = {}
        try:
            prev = json.loads(reports[1].extracted_values or '{}')
        except (json.JSONDecodeError, TypeError):
            prev = {}
        
        for key in set(latest.keys()).union(prev.keys()):
            try:
                v_new = float(latest.get(key, prev.get(key, 0))) if latest.get(key) or prev.get(key) else 0
                v_old = float(prev.get(key, latest.get(key, 0))) if prev.get(key) or latest.get(key) else 0
                if v_new > v_old:
                    status = 'worse'
                elif v_new < v_old:
                    status = 'improved'
                else:
                    status = 'no_change'
                comparison[key] = {'latest': v_new, 'previous': v_old, 'status': status}
            except (ValueError, TypeError):
                continue
    elif len(reports) == 1:
        # If only one report, show its values as "latest" with no comparison
        try:
            latest = json.loads(reports[0].extracted_values or '{}')
            for key, value in latest.items():
                try:
                    v = float(value)
                    comparison[key] = {'latest': v, 'previous': None, 'status': 'no_change'}
                except (ValueError, TypeError):
                    continue
        except (json.JSONDecodeError, TypeError):
            pass
    # Personalized diet chart based on actual medical parameters (ENHANCED)
    food_df = pd.read_csv('food_data.csv')
    param_df = pd.read_csv('medical_test_parameters.csv')
    goal = current_user.goal or 'weight_loss'
    diet_chart = []
    
    # Get latest report values
    latest_values = {}
    latest_conditions = []
    if reports:
        latest_report = reports[0]
        latest_values = latest_report.values_dict if hasattr(latest_report, 'values_dict') else json.loads(latest_report.extracted_values or '{}')
        latest_conditions = latest_report.conds_list if hasattr(latest_report, 'conds_list') else json.loads(latest_report.conditions or '[]')
    
    # Analyze medical parameters to determine specific dietary needs
    dietary_needs = analyze_dietary_needs(latest_values, param_df, current_user.gender)
    
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
    
    # Add dietary needs from parameter analysis
    if dietary_needs.get('needs_iron'):
        condition_tags.append('anemia')
    if dietary_needs.get('needs_cholesterol_control'):
        condition_tags.append('cholesterol')
    if dietary_needs.get('needs_sugar_control'):
        condition_tags.append('diabetes')
    if dietary_needs.get('needs_triglyceride_control'):
        condition_tags.append('triglycerides')
    
    # Always include goal as a tag
    if goal == 'diabetes_control':
        condition_tags.append('diabetes')
    elif goal == 'muscle_gain':
        condition_tags.append('muscle')
    elif goal == 'weight_loss':
        condition_tags.append('weight_loss')
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
        
        # Select foods for this meal - prioritize based on dietary needs
        if primary_condition and primary_condition in meal_suggestions[meal]:
            suggested_foods = meal_suggestions[meal][primary_condition]
        else:
            suggested_foods = meal_suggestions[meal]['default']
        
        # Filter and prioritize foods from CSV based on actual dietary needs
        suitable_foods_from_csv = []
        if dietary_needs.get('needs_iron'):
            # Prioritize high-iron foods
            iron_foods = food_df[food_df['iron'].astype(float) > 1.5].sort_values('iron', ascending=False)
            suitable_foods_from_csv.extend(iron_foods['food'].head(5).tolist())
        if dietary_needs.get('needs_sugar_control'):
            # Prioritize low-carb foods
            low_carb_foods = food_df[food_df['carbs'].astype(float) < 20].sort_values('carbs', ascending=True)
            suitable_foods_from_csv.extend(low_carb_foods['food'].head(5).tolist())
        if dietary_needs.get('needs_cholesterol_control'):
            # Prioritize cholesterol-friendly foods
            chol_foods = food_df[food_df['suitable_for'].str.contains('cholesterol', case=False, na=False)]
            suitable_foods_from_csv.extend(chol_foods['food'].head(5).tolist())
        if dietary_needs.get('needs_triglyceride_control'):
            # Prioritize low-calorie, low-sugar foods
            trig_foods = food_df[(food_df['calories'].astype(float) < 150) & (food_df['carbs'].astype(float) < 25)]
            suitable_foods_from_csv.extend(trig_foods['food'].head(5).tolist())
        
        # Combine suggested foods with CSV-based foods, removing duplicates
        all_suggested = list(dict.fromkeys(suggested_foods + suitable_foods_from_csv[:3]))  # Keep order, limit CSV foods
        
        # Build food list with specific reasons based on actual parameter values
        for food in all_suggested[:4]:  # Limit to 4 foods per meal
            row = food_df[food_df['food'].str.lower() == food.lower()]
            if not row.empty:
                food_data = row.iloc[0]
                suitable = food_data['suitable_for']
                
                # Generate specific reason based on actual medical parameters
                reason_parts = []
                
                # Iron-rich foods for low hemoglobin
                if dietary_needs.get('needs_iron') and float(food_data.get('iron', 0)) > 1.5:
                    reason_parts.append(f"High iron content ({food_data.get('iron', 0)}mg) to improve hemoglobin levels")
                
                # Low carb for high blood sugar
                if dietary_needs.get('needs_sugar_control') and float(food_data.get('carbs', 0)) < 20:
                    reason_parts.append(f"Low carbohydrate ({food_data.get('carbs', 0)}g) to help control blood sugar")
                
                # Heart-healthy for high cholesterol
                if dietary_needs.get('needs_cholesterol_control') and 'cholesterol' in str(suitable).lower():
                    reason_parts.append(f"Heart-healthy food to help lower cholesterol levels")
                
                # Low fat for high triglycerides
                if dietary_needs.get('needs_triglyceride_control') and float(food_data.get('calories', 0)) < 150:
                    reason_parts.append(f"Low-calorie option to help manage triglyceride levels")
                
                # High protein for muscle gain
                if goal == 'muscle_gain' and float(food_data.get('protein', 0)) > 5:
                    reason_parts.append(f"High protein ({food_data.get('protein', 0)}g) for muscle building")
                
                # Calcium for low calcium
                if dietary_needs.get('needs_calcium') and 'dairy' in food.lower() or 'cheese' in food.lower():
                    reason_parts.append(f"Rich in calcium to support bone health")
                
                # Default reasons based on condition
                if not reason_parts:
                    if primary_condition == 'diabetes':
                        reason_parts.append(f"Low glycemic index food to help control blood sugar levels")
                    elif primary_condition == 'anemia':
                        reason_parts.append(f"Rich in iron ({food_data.get('iron', 0)}mg) and nutrients to combat anemia")
                    elif primary_condition == 'cholesterol':
                        reason_parts.append(f"Heart-healthy food to help lower cholesterol")
                    else:
                        reason_parts.append(f"Balanced nutrition for overall health and {goal.replace('_', ' ')}")
                
                # Combine reason parts
                reason = '. '.join(reason_parts) if reason_parts else f"Nutritious choice for {goal.replace('_', ' ')}"
                
                foods.append({
                    'food': food_data['food'],
                    'calories': food_data['calories'],
                    'protein': food_data.get('protein', 0),
                    'iron': food_data.get('iron', 0),
                    'carbs': food_data.get('carbs', 0),
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
        
        # Combine reasons intelligently with specific parameter-based insights
        if dietary_needs.get('specific_recommendations'):
            # Use specific recommendations from parameter analysis
            meal_specific_reason = dietary_needs['specific_recommendations'][0] if dietary_needs['specific_recommendations'] else ""
            if meal_specific_reason:
                combined_reason = f"{meal_specific_reason}. This meal is designed to address your specific health parameters."
            else:
                primary_reason = foods[0]["reason"] if foods else "Balanced nutrition"
                combined_reason = f"{primary_reason}. Additional foods provide variety and essential nutrients."
        else:
            if len(set([f["reason"] for f in foods])) == 1:
                combined_reason = foods[0]["reason"]
            else:
                primary_reason = foods[0]["reason"]
                combined_reason = f"{primary_reason}. Additional foods provide variety and balanced nutrition."
        
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
    # Calculate wellness score based on medical parameters
    wellness_score = calculate_wellness_score(reports, current_user.gender)
    
    # Generate personalized wellness tips based on health conditions and score
    wellness_tips = []
    
    if reports and len(reports) > 0:
        latest_report = reports[0]
        latest_conditions = latest_report.conds_list if hasattr(latest_report, 'conds_list') else json.loads(latest_report.conditions or '[]')
        
        # Add condition-specific tips
        if any('diabetes' in c.lower() or 'sugar' in c.lower() for c in latest_conditions):
            wellness_tips.append("Monitor your blood sugar levels regularly and maintain a balanced diet.")
            wellness_tips.append("Choose low glycemic index foods to help control blood sugar.")
        if any('cholesterol' in c.lower() for c in latest_conditions):
            wellness_tips.append("Focus on heart-healthy foods and regular exercise to manage cholesterol.")
            wellness_tips.append("Include omega-3 rich foods like fish and nuts in your diet.")
        if any('anemia' in c.lower() for c in latest_conditions):
            wellness_tips.append("Include iron-rich foods like spinach, lentils, and lean meats in your meals.")
            wellness_tips.append("Pair iron-rich foods with vitamin C to enhance absorption.")
        if any('triglyceride' in c.lower() for c in latest_conditions):
            wellness_tips.append("Reduce refined sugars and processed foods to lower triglycerides.")
            wellness_tips.append("Incorporate more fiber-rich foods and healthy fats.")
    
    # Add general tips based on wellness score
    if wellness_score >= 80:
        wellness_tips.extend([
            "Great job maintaining healthy parameters! Keep up the excellent work!",
            "Continue with your current lifestyle to maintain optimal health.",
            "Stay hydrated and maintain regular physical activity."
        ])
    elif wellness_score >= 60:
        wellness_tips.extend([
            "Your health parameters are mostly good, with some areas for improvement.",
            "Focus on the parameters that are slightly out of range.",
            "Consider consulting with your healthcare provider for personalized advice."
        ])
    else:
        wellness_tips.extend([
            "Some health parameters need attention. Consider consulting your doctor.",
            "Focus on improving lifestyle factors: diet, exercise, and sleep.",
            "Small, consistent changes can lead to significant health improvements."
        ])
    
    # Add universal tips
    wellness_tips.extend([
        "Drink plenty of water throughout the day!",
        "Take a short walk every hour to stay active.",
        "Eat a variety of colorful fruits and vegetables.",
        "Prioritize 7-8 hours of sleep each night.",
        "Practice deep breathing or meditation for stress relief.",
        "Celebrate your small health wins!"
    ])
    
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
    try:
        if 'report_file' not in request.files:
            flash('No file part.', 'danger')
            return redirect(url_for('dashboard'))
        file = request.files['report_file']
        if file.filename == '':
            flash('No selected file.', 'danger')
            return redirect(url_for('dashboard'))
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            # Ensure upload folder exists
            os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
            save_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(save_path)
            print(f"File saved to: {save_path}")
            
            lang = request.form.get('ocr_language', 'eng')
            print(f"Extracting text with language: {lang}")
            
            text = extract_text_from_file(save_path, lang=lang)
            
            if not text or not text.strip():
                flash('Warning: Could not extract text from the file. The file might be corrupted or OCR libraries may not be installed.', 'warning')
                # Still create a report with empty values
                values = {}
                conditions = []
            else:
                print(f"Extracted text length: {len(text)} characters")
                values, conditions = parse_medical_values(text)
                print(f"Parsed {len(values)} values and {len(conditions)} conditions")
            
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
            
            if len(values) > 0:
                flash(f'Medical report uploaded and processed successfully! Extracted {len(values)} health parameters.', 'success')
            else:
                flash('Medical report uploaded, but no values were extracted. Please check if the file contains readable text or try a different file format.', 'warning')
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid file type. Only PDF, JPG, JPEG, PNG allowed.', 'danger')
            return redirect(url_for('dashboard'))
    except Exception as e:
        print(f"Error in upload route: {e}")
        import traceback
        traceback.print_exc()
        flash(f'Error processing file: {str(e)}', 'danger')
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
    patient = db.session.get(User, report.user_id)
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
    receiver = db.session.get(User, receiver_id)
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
        
        # Get extracted values and conditions from latest report for structured prompt
        extracted_values = {}
        conditions = []
        if latest_report:
            try:
                extracted_values = json.loads(latest_report.extracted_values or '{}')
                conditions = json.loads(latest_report.conditions or '[]')
            except Exception as e:
                print(f"Error parsing report data: {e}")

        # Get chat history from database
        chat_history = ChatHistory.query.filter_by(user_id=current_user.id)\
                .order_by(ChatHistory.timestamp.desc())\
                .limit(10).all()
        chat_history = list(reversed(chat_history))

        # System prompt: simple language, structure, under 120 words
        system_prompt = """You are an AI medical assistant helping users understand lab reports.
Explain results in very simple language for non-medical users.
Steps:
1. Explain what the test means.
2. Tell whether the value is low, normal, or high.
3. Explain possible health conditions.
4. Suggest simple diet or lifestyle improvements.
5. Avoid complex medical terminology.
Keep responses under 120 words."""

        # Structured patient data for clear AI explanation
        user_prompt = f"""
Patient Information
Name: {current_user.username}
Age: {current_user.age if current_user.age else 'N/A'}
Health Goal: {current_user.goal or 'N/A'}

Extracted Lab Results
Hemoglobin: {extracted_values.get('hemoglobin_hb', 'N/A')}
Globulin: {extracted_values.get('globulin', 'N/A')}
Uric Acid: {extracted_values.get('uric_acid', 'N/A')}

Detected Conditions
{', '.join(conditions) if conditions else "None detected"}

User Question
{user_message}

Explain the health report clearly and provide simple recommendations.
"""
        context = user_prompt
        print(f"Context length: {len(context)} characters")
        
        print(f"Calling OpenRouter API...")
        
        # Call DeepSeek LLM via OpenRouter
        headers = {
            'Authorization': f'Bearer {OPENROUTER_API_KEY}',
            'Content-Type': 'application/json',
        }
        
        data = {
            'model': 'deepseek/deepseek-chat',
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

@app.route('/check-ocr-status')
@login_required
def check_ocr_status():
    """Check if OCR libraries are available"""
    status = {
        'pytesseract_available': PYTESSERACT_AVAILABLE,
        'easyocr_available': EASYOCR_AVAILABLE,
        'ocr_available': PYTESSERACT_AVAILABLE or EASYOCR_AVAILABLE
    }
    return jsonify(status)

@app.route('/test-extraction/<int:report_id>')
@login_required
def test_extraction(report_id):
    """Test extraction on an existing report - for debugging"""
    report = HealthReport.query.filter_by(id=report_id, user_id=current_user.id).first()
    if not report:
        return jsonify({'error': 'Report not found'}), 404
    
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], report.filename)
    if not os.path.exists(filepath):
        return jsonify({'error': 'File not found on server'}), 404
    
    # Try extraction
    text = extract_text_from_file(filepath, lang='eng')
    values, conditions = parse_medical_values(text)
    
    return jsonify({
        'filename': report.filename,
        'text_length': len(text),
        'text_preview': text[:500] if len(text) > 500 else text,
        'values_extracted': len(values),
        'values': values,
        'conditions': conditions,
        'ocr_available': PYTESSERACT_AVAILABLE or EASYOCR_AVAILABLE
    })

@app.route('/')
def home():
    return redirect(url_for('login'))

@app.route('/download_report')
@login_required
def download_report():
    # Fetch all data same way as dashboard route does
    reports = HealthReport.query.filter_by(user_id=current_user.id).order_by(HealthReport.timestamp.desc()).all()
    
    # Build comparison dict (copy exact logic from dashboard route)
    comparison = {}
    latest_conditions = []
    doctor_notes = None
    report_date = "N/A"
    
    if reports:
        latest_report = reports[0]
        report_date = latest_report.timestamp.strftime("%d %b %Y")
        try:
            latest_conditions = json.loads(latest_report.conditions or '[]')
        except:
            latest_conditions = []
        doctor_notes = latest_report.doctor_comment
        
    if len(reports) >= 2:
        try:
            latest_vals = json.loads(reports[0].extracted_values or '{}')
            prev_vals = json.loads(reports[1].extracted_values or '{}')
        except:
            latest_vals, prev_vals = {}, {}
        for key in set(latest_vals.keys()).union(prev_vals.keys()):
            try:
                v_new = float(latest_vals.get(key, prev_vals.get(key, 0))) if latest_vals.get(key) or prev_vals.get(key) else 0
                v_old = float(prev_vals.get(key, latest_vals.get(key, 0))) if prev_vals.get(key) or latest_vals.get(key) else 0
                status = 'worse' if v_new > v_old else ('improved' if v_new < v_old else 'no_change')
                comparison[key] = {'latest': v_new, 'previous': v_old, 'status': status}
            except:
                continue
    elif len(reports) == 1:
        try:
            latest_vals = json.loads(reports[0].extracted_values or '{}')
            for key, value in latest_vals.items():
                try:
                    comparison[key] = {'latest': float(value), 'previous': None, 'status': 'no_change'}
                except:
                    continue
        except:
            pass
    
    # Build parameters dict from comparison
    parameters = {}
    for key, data in comparison.items():
        if key.endswith('_unit'):
            continue
        parameters[key] = {
            "value": data["latest"],
            "previous": data["previous"],
            "status": "Normal",   # default — we don't have range data here so just show value
            "change": data["status"]
        }
    
    # Get diet_chart from latest report
    diet_chart = []
    if reports:
        try:
            diet_chart = json.loads(reports[0].diet_plan or '[]')
        except:
            diet_chart = []
    
    # Get wellness score
    import pandas as pd
    param_df = pd.read_csv('medical_test_parameters.csv')
    wellness_score = calculate_wellness_score(reports, current_user.gender)
    
    # Get wellness tips (reuse same logic as dashboard)
    wellness_tips = []
    if latest_conditions:
        if any('diabetes' in c.lower() or 'sugar' in c.lower() for c in latest_conditions):
            wellness_tips.append("Monitor your blood sugar levels regularly and maintain a balanced diet.")
            wellness_tips.append("Choose low glycemic index foods to help control blood sugar.")
        if any('cholesterol' in c.lower() for c in latest_conditions):
            wellness_tips.append("Focus on heart-healthy foods and regular exercise to manage cholesterol.")
        if any('anemia' in c.lower() for c in latest_conditions):
            wellness_tips.append("Include iron-rich foods like spinach, lentils, and lean meats in your meals.")
            wellness_tips.append("Pair iron-rich foods with vitamin C to enhance absorption.")
    wellness_tips.extend([
        "Drink plenty of water throughout the day.",
        "Walk 30 minutes daily to stay active.",
        "Prioritize 7-8 hours of sleep each night.",
        "Eat a variety of colorful fruits and vegetables.",
        "Practice deep breathing for stress relief."
    ])
    
    # Activity summary
    activity_logs = ActivityLog.query.filter_by(user_id=current_user.id).all()
    activity_summary = {
        "total_steps": sum((log.steps or 0) for log in activity_logs),
        "total_calories": sum((log.calories or 0) for log in activity_logs),
        "days_logged": len(activity_logs)
    }
    
    # Build patient_data
    patient_data = {
        "name": current_user.username,
        "age": current_user.age or "N/A",
        "gender": current_user.gender or "N/A",
        "report_date": report_date,
        "parameters": parameters,
        "diet_chart": diet_chart,
        "wellness_score": wellness_score,
        "wellness_tips": wellness_tips[:6],
        "doctor_notes": doctor_notes,
        "conditions": latest_conditions,
        "activity_summary": activity_summary,
        "username": current_user.patient_id,
    }
    
    pdf_buffer = generate_patient_report(patient_data)
    filename = f"NutriPattern_Report_{current_user.username}_{datetime.now().strftime('%Y%m%d')}.pdf"
    
    return send_file(
        pdf_buffer,
        mimetype="application/pdf",
        as_attachment=True,
        download_name=filename
    )

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True, port=5001, host='127.0.0.1') 
