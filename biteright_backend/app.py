import sys
sys.stdout.reconfigure(encoding='utf-8')

import json
import os
import re
import secrets
import time
import traceback
from functools import wraps
import urllib.request
from datetime import datetime, timedelta, timezone

try:
    # Load biteright_backend/.env for local development (Render sets real env vars).
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env'))
except ImportError:
    pass

from flask import Flask, g, jsonify, request
from flask_cors import CORS
from werkzeug.exceptions import HTTPException
import firebase_admin
from firebase_admin import credentials, firestore

import analytics
from security import (
    MIN_PASSWORD_LENGTH,
    RateLimiter,
    client_ip,
    hash_password,
    issue_token,
    require_user,
    verify_password,
)

# Import your services
from services.ocr_service import extract_ingredients, _estimate_ocr_confidence
from services.nlp_service import AllergenDetector
from services.processing_service import IngredientProcessor
from services.risk_analyzer import (
    build_general_analysis,
    build_personalized_analysis as build_personalized_analysis_v2,
    parse_ingredients_input as parse_ingredients_input_v2,
)
from dietary_options import get_options_by_category

# Initialize Flask
app = Flask(__name__)
# Reject uploads larger than 10 MB before they reach OCR.
app.config['MAX_CONTENT_LENGTH'] = int(os.environ.get('MAX_UPLOAD_MB', '10')) * 1024 * 1024
CORS(app)  # Enable CORS for all routes

# Debug-only endpoints (Firestore inspection, inline test analysis) are off by default.
DEBUG_ENDPOINTS_ENABLED = os.environ.get('ENABLE_DEBUG_ENDPOINTS', '').strip().lower() in ('1', 'true', 'yes')

# Brute-force protection (single gunicorn worker, so in-memory state is shared).
login_limiter = RateLimiter(max_attempts=10, window_seconds=15 * 60)
reset_request_limiter = RateLimiter(max_attempts=5, window_seconds=15 * 60)
reset_verify_limiter = RateLimiter(max_attempts=10, window_seconds=15 * 60)
MAX_RESET_CODE_ATTEMPTS = 5


def _initialize_firebase():
    """Initialize Firebase from FIREBASE_CREDENTIALS_JSON or a key file."""
    try:
        firebase_admin.get_app()
        return True
    except ValueError:
        pass

    credentials_json = os.environ.get('FIREBASE_CREDENTIALS_JSON', '').strip()
    if credentials_json:
        firebase_admin.initialize_app(credentials.Certificate(json.loads(credentials_json)))
        return True

    key_path = os.environ.get('FIREBASE_KEY_PATH', 'serviceAccountKey.json')
    if os.path.exists(key_path):
        firebase_admin.initialize_app(credentials.Certificate(key_path))
        return True

    print(f"Warning: Firebase credentials not found (checked FIREBASE_CREDENTIALS_JSON and {key_path})")
    return False


FIREBASE_READY = _initialize_firebase()

# Get Firestore client
db = firestore.client()

SCAN_HISTORY_COLLECTION = 'scan_history'
LEGACY_SCANS_COLLECTION = 'scans'
PRODUCT_INGREDIENTS_COLLECTION = 'product_ingredients'
INGREDIENT_MATCHES_COLLECTION = 'ingredient_matches'
DIETARY_RESTRICTIONS_COLLECTION = 'dietary_restrictions'

# Initialize detectors and processors
detector = AllergenDetector()
processor = IngredientProcessor(db)

# Flag to track if initialization has been done
_initialized = False

# ============= HELPER FUNCTIONS =============

EMAIL_PATTERN = re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')
BARCODE_PATTERN = re.compile(r'^\d{6,14}$')


def normalize_email(value):
    return str(value or '').strip().lower()


def find_user_by_email(email):
    """Find a user document by email, tolerating legacy mixed-case emails."""
    normalized = normalize_email(email)
    for candidate in dict.fromkeys([normalized, str(email or '').strip()]):
        if not candidate:
            continue
        matches = list(db.collection('users').where('email', '==', candidate).limit(1).stream())
        if matches:
            return matches[0]
    return None


def public_user(user_id, user_data):
    """User fields that are safe to return to the client."""
    return {
        'id': user_id,
        'username': user_data.get('username', ''),
        'email': user_data.get('email', ''),
        'allergies': user_data.get('allergies', []),
        'dietary_restrictions': user_data.get('dietary_restrictions', []),
    }


def server_error(error):
    """Log the full error server-side and return a generic message to the client."""
    if isinstance(error, HTTPException):
        return handle_http_error(error)
    print(f"Server error on {request.method} {request.path}: {error}", flush=True)
    traceback.print_exc()
    return jsonify({'error': 'Something went wrong on our side. Please try again.'}), 500


def safety_category(risk_level):
    risk_level = str(risk_level or '').lower()
    mapping = {'low_risk': 'safe', 'moderate_risk': 'caution', 'high_risk': 'unsafe'}
    if risk_level in ('unsafe', 'caution', 'safe'):
        return risk_level
    return mapping.get(risk_level, 'caution')


def log(message, *args, **kwargs):
    """Simple application logger used by API routes."""
    if args or kwargs:
        message = message % args if isinstance(message, str) and '%' in message else message
    print(message, flush=True)


def _log(message, *args, **kwargs):
    """Backward-compatible alias for log used in routed error handlers."""
    log(message, *args, **kwargs)


def dietary_rules():
    return {
        'halal': {'name': 'Halal', 'severity': 'high', 'forbidden': ['pork', 'ham', 'bacon', 'lard', 'alcohol', 'wine', 'beer', 'gelatin']},
        'vegetarian': {'name': 'Vegetarian', 'severity': 'medium', 'forbidden': ['beef', 'chicken', 'pork', 'fish', 'meat', 'gelatin']},
        'vegan': {'name': 'Vegan', 'severity': 'medium', 'forbidden': ['milk', 'dairy', 'whey', 'casein', 'egg', 'honey', 'gelatin', 'butter', 'cheese', 'yogurt']},
        'diabetic': {'name': 'Diabetic / Low Sugar', 'severity': 'high', 'forbidden': ['sugar', 'syrup', 'honey', 'dextrose', 'corn syrup', 'glucose', 'sucrose', 'fructose', 'maltose']},
        'low_sodium': {'name': 'Low Sodium', 'severity': 'low', 'forbidden': ['salt', 'sodium', 'monosodium glutamate', 'msg']},
        'keto': {'name': 'Keto', 'severity': 'medium', 'forbidden': ['sugar', 'wheat', 'rice', 'corn', 'potato', 'starch', 'syrup', 'honey', 'bread', 'pasta']},
    }

def _get_recommendations(risk_level):
    """Get recommendations based on risk level"""
    if risk_level == 'unsafe':
        return [
            'Do not consume this product - it contains allergens from your profile.',
            'Check the ingredient label carefully before purchasing.',
            'Consider contacting the manufacturer about potential cross-contamination.'
        ]
    elif risk_level == 'caution':
        return [
            'Review the flagged ingredients before consuming.',
            'Check the manufacturer allergen statement for cross-contact warnings.',
            'When in doubt, contact the manufacturer for clarification.'
        ]
    else:
        return [
            'No profile conflicts were detected in the scanned ingredients.',
            'Keep your allergy and dietary profile updated for accurate alerts.',
            'Always double-check labels as formulations can change.'
        ]


def debug_only(view):
    """Hide diagnostic endpoints unless ENABLE_DEBUG_ENDPOINTS is set."""

    @wraps(view)
    def wrapper(*args, **kwargs):
        if not DEBUG_ENDPOINTS_ENABLED:
            return jsonify({'error': 'Not found'}), 404
        return view(*args, **kwargs)

    return wrapper


@app.errorhandler(HTTPException)
def handle_http_error(error):
    """Return JSON (not HTML) for 404, 405, 413 and other HTTP errors."""
    messages = {
        413: f"Image is too large. Please upload a file under {app.config['MAX_CONTENT_LENGTH'] // (1024 * 1024)} MB.",
    }
    return jsonify({'error': messages.get(error.code, error.description)}), error.code


@app.errorhandler(Exception)
def handle_unexpected_error(error):
    return server_error(error)


@app.before_request
def initialize_once():
    """Load allergen data from Firestore before first analysis request"""
    global _initialized
    if request.path in ['/', '/health']:
        return
    if not _initialized:
        try:
            print("=" * 50)
            print("Initializing BiteRight Backend...")
            print("=" * 50)
            print("Loading allergen database...")
            detector.load_allergens_from_firestore(db)
            
            try:
                processor.initialize()
                print("Ingredient processor initialized")
            except Exception as e:
                print(f"Processor initialization warning: {e}")
            
            print("Allergen database loaded!")
            print("ML/NLP model is ACTIVE and will be used for analysis")
            print("=" * 50)
            _initialized = True
        except Exception as e:
            print(f"Initialization warning: {e}")


# ============= API ENDPOINTS =============

@app.route('/')
def home():
    return jsonify({
        "message": "BiteRight API is running with Firebase!",
        "version": "2.1",
        "authentication": "Send 'Authorization: Bearer <token>' from /login or /users (POST) to user-scoped endpoints",
        "nlp_status": "active",
        "detection_method": "ML/NLP Pattern Matching",
        "endpoints": {
            "/": "This help message",
            "/test-firebase": "Test Firebase connection",
            "/health": "Health check endpoint",
            "/users (GET)": "Get all users",
            "/users (POST)": "Create a new user",
            "/login (POST)": "Login with email and password",
            "/users/<user_id> (GET)": "Get specific user",
            "/users/<user_id> (PUT)": "Update user",
            "/users/<user_id> (DELETE)": "Delete user",
            "/users/<user_id>/scans (GET)": "Get user's scan history",
            "/users/<user_id>/scans (POST)": "Add scan to history",
            "/scan/<user_id> (POST)": "Scan food label for specific user",
            "/scan (POST)": "Basic scan without user profile",
            "/extract-ingredients (POST)": "Extract and process ingredients from image",
            "/analyze-ingredients (POST)": "Analyze ingredients for allergens",
            "/analyze-with-profile (POST)": "Analyze ingredients against user profile",
            "/dietary-options (GET)": "Get all dietary options"
        }
    })


@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({
        'status': 'healthy',
        'nlp_loaded': True,
        'ml_active': processor.model_loaded,
        'rf_primary': processor.model_loaded,
        'rf_weights': {
            'random_forest': processor.ML_WEIGHT,
            'rule_based': processor.RULE_WEIGHT
        },
        'firebase_connected': FIREBASE_READY,
        'allergen_data_loaded': _initialized,
        'timestamp': datetime.now().isoformat()
    }), 200


# ============= TEST ENDPOINT =============
@app.route('/test-firebase')
@debug_only
def test_firebase():
    try:
        collections = db.collections()
        collection_names = [col.id for col in collections]
        return jsonify({
            "status": "success",
            "message": "Firebase connected successfully!",
            "collections": collection_names
        })
    except Exception as e:
        return server_error(e)


@app.route('/test-products', methods=['GET'])
@debug_only
def test_products():
    try:
        products_ref = db.collection('openfoodfacts_products').limit(5).stream()
        products = []
        for product in products_ref:
            products.append(product.to_dict())
        return jsonify({'count': len(products), 'products': products})
    except Exception as e:
        return server_error(e)


@app.route('/search-allergens/<allergen>', methods=['GET'])
@debug_only
def search_by_allergen(allergen):
    try:
        products_ref = db.collection('openfoodfacts_products')\
            .where('allergens', 'array_contains', allergen)\
            .limit(20)\
            .stream()
        products = []
        for product in products_ref:
            products.append(product.to_dict())
        return jsonify({'allergen': allergen, 'count': len(products), 'products': products})
    except Exception as e:
        return server_error(e)


# ============= USER ENDPOINTS =============

@app.route('/users', methods=['POST'])
def create_user():
    try:
        data = request.get_json(silent=True) or {}
        username = str(data.get('username') or '').strip()
        email = normalize_email(data.get('email'))
        password = str(data.get('password') or '')

        if not username or not email or not password:
            return jsonify({'error': 'Missing username, email or password'}), 400
        if len(username) < 3:
            return jsonify({'error': 'Name must be at least 3 characters'}), 400
        if not EMAIL_PATTERN.match(email):
            return jsonify({'error': 'Invalid email address'}), 400
        if len(password) < MIN_PASSWORD_LENGTH:
            return jsonify({'error': f'Password must be at least {MIN_PASSWORD_LENGTH} characters'}), 400

        allergies = data.get('allergies', [])
        dietary_restrictions = data.get('dietary_restrictions', [])
        if not isinstance(allergies, list) or not isinstance(dietary_restrictions, list):
            return jsonify({'error': 'Allergies and dietary restrictions must be lists'}), 400

        if find_user_by_email(email) is not None:
            return jsonify({'error': 'An account with this email already exists'}), 409

        user_data = {
            'username': username,
            'email': email,
            'password_hash': hash_password(password),
            'allergies': allergies,
            'dietary_restrictions': dietary_restrictions,
            'created_at': firestore.SERVER_TIMESTAMP,
            'updated_at': firestore.SERVER_TIMESTAMP
        }
        user_ref = db.collection('users').add(user_data)
        user_id = user_ref[1].id

        return jsonify({
            'id': user_id,
            'message': 'User created successfully',
            'token': issue_token(user_id),
            'user': public_user(user_id, user_data),
        }), 201
    except Exception as e:
        return server_error(e)


@app.route('/login', methods=['POST'])
def login():
    try:
        data = request.get_json(silent=True) or {}
        email = normalize_email(data.get('email'))
        password = str(data.get('password') or '')
        if not email or not password:
            return jsonify({'error': 'Missing email or password'}), 400

        limiter_key = f"{client_ip()}|{email}"
        if not login_limiter.allow(limiter_key):
            return jsonify({'error': 'Too many sign-in attempts. Please wait 15 minutes and try again.'}), 429

        user_doc = find_user_by_email(email)
        if user_doc is None:
            return jsonify({'error': 'Invalid email or password'}), 401

        user_data = user_doc.to_dict()
        is_valid, needs_rehash = verify_password(password, user_data.get('password_hash', ''))
        if not is_valid:
            return jsonify({'error': 'Invalid email or password'}), 401

        login_limiter.reset(limiter_key)
        updates = {'last_login_at': firestore.SERVER_TIMESTAMP}
        if needs_rehash:
            # Upgrade legacy SHA-256 hashes to scrypt on successful login.
            updates['password_hash'] = hash_password(password)
        if user_data.get('email') != email:
            updates['email'] = email
        try:
            db.collection('users').document(user_doc.id).update(updates)
        except Exception as update_error:
            print(f"Login bookkeeping warning: {update_error}")

        return jsonify({
            'success': True,
            'token': issue_token(user_doc.id),
            'user': public_user(user_doc.id, user_data),
        }), 200
    except Exception as e:
        return server_error(e)


import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

def send_reset_email(to_email, otp_code):
    sender_email = os.environ.get('SENDER_EMAIL', 'athirahazmi77@gmail.com').strip()
    api_key = (os.environ.get('BREVO_API_KEY') or os.environ.get('MAIL_API_KEY') or '').strip().strip('"').strip("'")

    # Method 1: HTTPS REST API (Port 443 - Never blocked by Render firewall)
    if api_key:
        try:
            url = "https://api.brevo.com/v3/smtp/email"
            headers = {
                "accept": "application/json",
                "api-key": api_key,
                "content-type": "application/json"
            }
            payload = {
                "sender": {"name": "BiteRight Security", "email": sender_email},
                "to": [{"email": to_email}],
                "subject": "🔑 BiteRight — Password Reset Code",
                "htmlContent": f"""
                <div style="font-family: Arial, sans-serif; padding: 24px; color: #1A1814; max-width: 500px; margin: 0 auto; border: 1px solid #E5E0D8; border-radius: 16px;">
                    <h2 style="color: #2A6E54; margin-top: 0;">BiteRight Security</h2>
                    <p style="font-size: 15px; color: #5A5754;">You requested a password reset for your BiteRight account.</p>
                    <div style="background: #F4F8F6; padding: 18px; border-radius: 12px; text-align: center; margin: 20px 0; border: 1px solid #2A6E54;">
                        <span style="font-size: 32px; font-weight: bold; letter-spacing: 6px; color: #2A6E54;">{otp_code}</span>
                    </div>
                    <p style="font-size: 13px; color: #7A7771;">This code expires in 15 minutes. If you did not request a password reset, please ignore this email.</p>
                </div>
                """
            }
            req = urllib.request.Request(url, data=json.dumps(payload).encode('utf-8'), headers=headers)
            with urllib.request.urlopen(req, timeout=15) as resp:
                if resp.status in (200, 201):
                    print(f"✓ Reset email sent successfully via HTTPS API to {to_email}")
                    return True
        except Exception as e:
            print(f"HTTP Email API failed: {e}")

    # Method 2: Standard SMTP (Port 587)
    smtp_server = os.environ.get('SMTP_SERVER', 'smtp.gmail.com')
    smtp_port = int(os.environ.get('SMTP_PORT', 587))
    sender_password = os.environ.get('SENDER_PASSWORD', '')

    if not sender_email or not sender_password:
        print("SMTP Info: SENDER_EMAIL or SENDER_PASSWORD not set; reset email not sent.")
        return False

    try:
        msg = MIMEMultipart('alternative')
        msg['Subject'] = '🔑 BiteRight — Password Reset Code'
        msg['From'] = f"BiteRight <{sender_email}>"
        msg['To'] = to_email

        html_content = f"""
        <div style="font-family: Arial, sans-serif; padding: 24px; color: #1A1814; max-width: 500px; margin: 0 auto; border: 1px solid #E5E0D8; border-radius: 16px;">
            <h2 style="color: #2A6E54; margin-top: 0;">BiteRight Security</h2>
            <p style="font-size: 15px; color: #5A5754;">You requested a password reset for your BiteRight account.</p>
            <div style="background: #F4F8F6; padding: 18px; border-radius: 12px; text-align: center; margin: 20px 0; border: 1px solid #2A6E54;">
                <span style="font-size: 32px; font-weight: bold; letter-spacing: 6px; color: #2A6E54;">{otp_code}</span>
            </div>
            <p style="font-size: 13px; color: #7A7771;">This code expires in 15 minutes. If you did not request a password reset, please ignore this email.</p>
        </div>
        """
        msg.attach(MIMEText(html_content, 'html'))

        server = smtplib.SMTP(smtp_server, smtp_port, timeout=15)
        server.starttls()
        server.login(sender_email, sender_password)
        server.sendmail(sender_email, to_email, msg.as_string())
        server.quit()
        print(f"✓ Reset email sent successfully to {to_email}")
        return True
    except Exception as e:
        print(f"✗ Failed to send reset email: {e}")
        return False


@app.route('/reset-password-request', methods=['POST'])
def reset_password_request():
    try:
        data = request.get_json(silent=True) or {}
        email = normalize_email(data.get('email'))
        if not email or not EMAIL_PATTERN.match(email):
            return jsonify({'error': 'Please enter a valid email address'}), 400

        if not reset_request_limiter.allow(f"{client_ip()}|{email}"):
            return jsonify({'error': 'Too many reset requests. Please wait 15 minutes and try again.'}), 429

        # Same response whether or not the account exists, so the endpoint
        # cannot be used to discover which emails are registered.
        generic_response = jsonify({
            'success': True,
            'message': 'If an account exists for this email, a 6-digit reset code has been sent.'
        }), 200

        user_doc = find_user_by_email(email)
        if user_doc is None:
            return generic_response

        otp_code = f"{secrets.randbelow(1000000):06d}"
        db.collection('users').document(user_doc.id).update({
            'reset_code_hash': hash_password(otp_code),
            'reset_code': firestore.DELETE_FIELD,
            'reset_code_expires': datetime.now(timezone.utc) + timedelta(minutes=15),
            'reset_code_attempts': 0,
        })

        if os.environ.get('LOG_RESET_CODES', '').strip().lower() in ('1', 'true', 'yes'):
            print(f"PASSWORD RESET CODE for {email}: {otp_code}")

        if not send_reset_email(email, otp_code):
            return jsonify({
                'error': 'We could not send the reset email right now. Please try again later.'
            }), 503

        return generic_response
    except Exception as e:
        return server_error(e)


@app.route('/reset-password', methods=['POST'])
def reset_password_route():
    try:
        data = request.get_json(silent=True) or {}
        email = normalize_email(data.get('email'))
        code = str(data.get('code') or '').strip()
        new_password = str(data.get('new_password') or '')
        if not email or not code or not new_password:
            return jsonify({'error': 'Missing email, code or new_password'}), 400
        if len(new_password) < MIN_PASSWORD_LENGTH:
            return jsonify({'error': f'Password must be at least {MIN_PASSWORD_LENGTH} characters'}), 400

        if not reset_verify_limiter.allow(f"{client_ip()}|{email}"):
            return jsonify({'error': 'Too many attempts. Please wait 15 minutes and try again.'}), 429

        invalid = (jsonify({'error': 'Invalid or expired reset code'}), 400)
        user_doc = find_user_by_email(email)
        if user_doc is None:
            return invalid

        user_ref = db.collection('users').document(user_doc.id)
        user_data = user_doc.to_dict()
        code_hash = user_data.get('reset_code_hash')
        expires = analytics.parse_datetime(user_data.get('reset_code_expires'))
        attempts = int(user_data.get('reset_code_attempts') or 0)

        if not code_hash or expires is None or attempts >= MAX_RESET_CODE_ATTEMPTS:
            return invalid
        if datetime.now() > expires:
            return invalid

        code_ok, _ = verify_password(code, code_hash)
        if not code_ok:
            user_ref.update({'reset_code_attempts': attempts + 1})
            return invalid

        user_ref.update({
            'password_hash': hash_password(new_password),
            'reset_code_hash': firestore.DELETE_FIELD,
            'reset_code_expires': firestore.DELETE_FIELD,
            'reset_code_attempts': firestore.DELETE_FIELD,
            'updated_at': firestore.SERVER_TIMESTAMP,
        })

        return jsonify({
            'success': True,
            'message': 'Password has been reset successfully'
        }), 200
    except Exception as e:
        return server_error(e)


# ============= BARCODE & PANTRY ENDPOINTS =============

def _fetch_open_food_facts(barcode_code):
    """Return product info from Open Food Facts, or None if unavailable."""
    url = f"https://world.openfoodfacts.org/api/v2/product/{barcode_code}.json"
    req = urllib.request.Request(url, headers={'User-Agent': 'BiteRight-App/2.1 (contact@biteright.app)'})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            if resp.status != 200:
                return None
            off_data = json.loads(resp.read().decode('utf-8'))
    except Exception as off_err:
        _log(f"Open Food Facts lookup warning: {off_err}")
        return None

    if off_data.get('status') != 1 or 'product' not in off_data:
        return None
    prod = off_data['product']
    return {
        'name': prod.get('product_name') or prod.get('product_name_en') or f"Barcode {barcode_code}",
        'brand': (prod.get('brands') or '').split(',')[0].strip(),
        'ingredients_text': (prod.get('ingredients_text') or prod.get('ingredients_text_en')
                             or prod.get('ingredients_text_with_allergens') or '').strip(),
        'image_url': prod.get('image_front_url') or prod.get('image_url') or '',
    }


def _timestamp_to_string(value):
    if value is None:
        return ''
    if hasattr(value, 'isoformat'):
        return value.isoformat()
    return str(value)


@app.route('/barcode/<barcode_code>', methods=['GET'])
@require_user
def lookup_barcode(barcode_code):
    """Look up a product on Open Food Facts and analyse it against the user's profile."""
    try:
        barcode_code = barcode_code.strip()
        if not BARCODE_PATTERN.match(barcode_code):
            return jsonify({'found': False, 'error': 'Barcodes must be 6 to 14 digits.'}), 400

        user_id = g.get('user_id') or ''
        log(f"Barcode lookup for: {barcode_code}, user: {user_id}")

        product = _fetch_open_food_facts(barcode_code)
        if not product or not product['ingredients_text']:
            return jsonify({
                'found': False,
                'barcode': barcode_code,
                'message': 'This product is not in the Open Food Facts database or has no ingredient list. '
                           'Try scanning the ingredient label instead.'
            }), 404

        user_allergies, user_diets = [], []
        if user_id:
            user_doc = db.collection('users').document(user_id).get()
            if user_doc.exists:
                profile = user_doc.to_dict()
                user_allergies = profile.get('allergies', [])
                user_diets = profile.get('dietary_restrictions', profile.get('diets', []))

        ingredients_text = product['ingredients_text']
        combined = processor.analyze_ingredients(
            ingredients_text,
            user_allergies=user_allergies,
            user_dietary=user_diets,
            raw_text=ingredients_text,
        )
        if user_allergies or user_diets:
            detail = build_personalized_analysis_v2(ingredients_text, user_allergies, user_diets, ingredients_text)
        else:
            detail = build_general_analysis(ingredients_text)

        risk_level = combined.get('risk_level', 'safe')
        product_name = ' - '.join(part for part in (product['brand'], product['name']) if part)

        analysis = {
            'risk_level': risk_level,
            'risk_score': combined.get('risk_score', 0),
            'confidence': combined.get('confidence', 0.7),
            'alerts': combined.get('alerts', []),
            'allergens_detected': combined.get('allergens_detected', []),
            'ingredients': parse_ingredients_input_v2(ingredients_text),
            'ingredient_details': detail.get('ingredient_details', []),
            'recommendations': _get_recommendations(risk_level),
            'detection_method': combined.get('detection_method', 'Random Forest (Primary) + Rule-Based'),
        }

        result_payload = {
            'found': True,
            'success': True,
            'barcode': barcode_code,
            'product_name': product_name,
            'brand': product['brand'],
            'image_url': product['image_url'],
            'ingredients_text': ingredients_text,
            'raw_text': ingredients_text,
            'verdict': risk_level,
            'safety_category': safety_category(risk_level),
            **analysis,
            'analysis': analysis,
        }

        if user_id:
            try:
                db.collection('users').document(user_id).collection('pantry').document(f"barcode_{barcode_code}").set({
                    'product_name': product_name,
                    'brand': product['brand'],
                    'barcode': barcode_code,
                    'image_url': product['image_url'],
                    'ingredients_text': ingredients_text,
                    'verdict': risk_level,
                    'safety_category': result_payload['safety_category'],
                    **analysis,
                    'analysis': analysis,
                    'scanned_at': firestore.SERVER_TIMESTAMP,
                }, merge=True)
            except Exception as pantry_error:
                _log(f"Pantry save warning: {pantry_error}")

            try:
                scan_id, new_badges = record_scan(user_id, {
                    **analysis,
                    'product_name': product_name,
                    'raw_text': ingredients_text,
                    'input_image_url': product['image_url'],
                    'detection_method': f"Barcode lookup + {analysis['detection_method']}",
                })
                result_payload['id'] = scan_id
                result_payload['scan_id'] = scan_id
                result_payload['newly_unlocked_badges'] = new_badges
            except Exception as history_error:
                _log(f"Scan history save warning: {history_error}")

        return jsonify(result_payload), 200
    except Exception as e:
        return server_error(e)


@app.route('/users/<user_id>/pantry', methods=['GET'])
@require_user
def get_user_pantry(user_id):
    """Products saved from barcode lookups, newest first."""
    try:
        items = []
        for item in db.collection('users').document(user_id).collection('pantry').stream():
            data = item.to_dict()
            data['id'] = item.id
            data['scanned_at'] = _timestamp_to_string(data.get('scanned_at'))
            data['safety_category'] = safety_category(data.get('safety_category') or data.get('risk_level'))
            items.append(data)
        items.sort(key=lambda d: d.get('scanned_at', ''), reverse=True)
        return jsonify(items), 200
    except Exception as e:
        return server_error(e)


@app.route('/users/<user_id>/pantry/<item_id>', methods=['DELETE'])
@require_user
def delete_pantry_item(user_id, item_id):
    """Remove item from user pantry"""
    try:
        db.collection('users').document(user_id).collection('pantry').document(item_id).delete()
        return jsonify({'success': True, 'message': 'Pantry item deleted'}), 200
    except Exception as e:
        return server_error(e)


@app.route('/users', methods=['GET'])
@debug_only
def get_users():
    try:
        users_ref = db.collection('users').stream()
        users = []
        for user in users_ref:
            user_data = user.to_dict()
            user_data.pop('password_hash', None)
            user_data['id'] = user.id
            if 'created_at' in user_data:
                user_data['created_at'] = str(user_data['created_at'])
            users.append(user_data)
        return jsonify(users), 200
    except Exception as e:
        return server_error(e)


@app.route('/users/<user_id>', methods=['GET'])
@require_user
def get_user(user_id):
    try:
        user_ref = db.collection('users').document(user_id).get()
        if not user_ref.exists:
            return jsonify({'message': 'User not found'}), 404
        user_data = user_ref.to_dict()
        return jsonify({
            **public_user(user_ref.id, user_data),
            'created_at': _timestamp_to_string(user_data.get('created_at')),
        }), 200
    except Exception as e:
        return server_error(e)


@app.route('/users/<user_id>', methods=['PUT'])
@require_user
def update_user(user_id):
    """Alias of PUT /users/<user_id>/profile with the same validation."""
    return update_user_profile(user_id=user_id)


def _delete_query(query, batch_size=200):
    """Delete every document matched by a Firestore query, in batches."""
    while True:
        docs = list(query.limit(batch_size).stream())
        if not docs:
            return
        batch = db.batch()
        for doc in docs:
            batch.delete(doc.reference)
        batch.commit()


@app.route('/users/<user_id>', methods=['DELETE'])
@require_user
def delete_user(user_id):
    """Delete the account together with its scans, badges and pantry."""
    try:
        user_ref = db.collection('users').document(user_id)
        if not user_ref.get().exists:
            return jsonify({'message': 'User not found'}), 404

        for collection_name in (SCAN_HISTORY_COLLECTION, LEGACY_SCANS_COLLECTION,
                                PRODUCT_INGREDIENTS_COLLECTION, INGREDIENT_MATCHES_COLLECTION,
                                DIETARY_RESTRICTIONS_COLLECTION, analytics.USER_BADGES_COLLECTION):
            _delete_query(db.collection(collection_name).where('user_id', '==', user_id))
        _delete_query(user_ref.collection('pantry'))
        user_ref.delete()
        return jsonify({'message': 'User deleted successfully'}), 200
    except Exception as e:
        return server_error(e)


@app.route('/user/<user_id>/stats', methods=['GET'])
@require_user
def get_user_stats(user_id):
    try:
        scans_ref = db.collection(SCAN_HISTORY_COLLECTION).where('user_id', '==', user_id).stream()
        scans = list(scans_ref)
        total_scans = len(scans)
        
        risk_counts = {'safe': 0, 'caution': 0, 'unsafe': 0}
        for scan in scans:
            risk_level = scan.to_dict().get('risk_level', 'unknown')
            if risk_level in risk_counts:
                risk_counts[risk_level] += 1
        
        recent_scans = []
        for scan in scans:
            scan_data = scan.to_dict()
            scan_data['id'] = scan.id
            recent_scans.append(scan_data)
        recent_scans.sort(key=lambda item: analytics.scan_time(item, datetime.min), reverse=True)
        recent_scans = recent_scans[:10]
        
        return jsonify({
            'total_scans': total_scans,
            'risk_breakdown': risk_counts,
            'recent_scans': recent_scans
        })
    except Exception as e:
        return server_error(e)


@app.route('/users/<user_id>/analytics/summary', methods=['GET'])
@require_user
def get_analytics_summary(user_id):
    try:
        user_ref = db.collection('users').document(user_id).get()
        if not user_ref.exists:
            return jsonify({'error': 'User not found'}), 404

        now = datetime.now()
        scans = analytics.load_user_scans(db, SCAN_HISTORY_COLLECTION, user_id, now)
        stats = analytics.compute_stats(scans, now)
        unlocked, _ = analytics.evaluate_badges(db, user_id, stats, now)
        badges, new_badge_count, first_locked = analytics.badge_list(unlocked, now)

        week = stats['week']
        month = stats['month']
        total_scans = stats['total']

        scans_by_day = [0] * 7
        for s in week['scans']:
            days_ago = (now.date() - s['parsed_time'].date()).days
            if 0 <= days_ago < 7:
                scans_by_day[6 - days_ago] += 1

        scans_by_week = [0] * 4
        for s in month['scans']:
            days_ago = (now.date() - s['parsed_time'].date()).days
            if 0 <= days_ago < 28:
                scans_by_week[3 - (days_ago // 7)] += 1

        weekly_title = "Welcome"
        weekly_msg = "Scan products to get insights!"
        if week['total'] > 0:
            if week['safe_pct'] == 100:
                weekly_title = "Perfect Record"
                weekly_msg = "All products scanned this week are safe!"
            elif week['safe_pct'] >= 80:
                weekly_title = "Great Choices"
                weekly_msg = f"{int(week['safe_pct'])}% of your scans this week are safe."
            else:
                weekly_title = "Needs Attention"
                weekly_msg = "Many products this week contain allergens."

        monthly_title = "Getting Started"
        monthly_msg = "Scan more products to see your monthly trends."
        if month['total'] > 0:
            if stats['scans_increase'] >= 20:
                monthly_title = "Active Scanner"
                monthly_msg = f"You scanned {month['total']} products this month."
            elif stats['improvement'] >= 15:
                monthly_title = "Improving"
                monthly_msg = f"Your product safety awareness improved {int(stats['improvement'])}%!"
            else:
                monthly_title = "Consistent Scanner"
                monthly_msg = f"You've scanned {month['total']} items this month."

        next_target = ((total_scans // 10) + 1) * 10
        if next_target - total_scans > 5 and total_scans % 10 >= 5:
            next_target = ((total_scans // 5) + 1) * 5

        if first_locked:
            recommendation_tip = f"Tip: {first_locked['description']} to unlock the '{first_locked['name']}' badge!"
        else:
            recommendation_tip = "You've unlocked all badges! Amazing job!"

        return jsonify({
            "weekly": {
                "total_scans": week['total'],
                "safe_count": week['safe'],
                "unsafe_count": week['unsafe'],
                "caution_count": week['caution'],
                "safe_percentage": week['safe_pct'],
                "top_allergen": week['top_allergen'],
                "avg_confidence": week['avg_conf'],
                "insight_title": weekly_title,
                "insight_message": weekly_msg,
                "scans_by_day": scans_by_day
            },
            "monthly": {
                "total_scans": month['total'],
                "safe_count": month['safe'],
                "unsafe_count": month['unsafe'],
                "caution_count": month['caution'],
                "safe_percentage": month['safe_pct'],
                "improvement": stats['improvement'],
                "scans_increase": stats['scans_increase'],
                "trend": stats['trend'],
                "insight_title": monthly_title,
                "insight_message": monthly_msg,
                "scans_by_week": scans_by_week,
                "top_categories": month['top_categories']
            },
            "total_scans_all_time": total_scans,
            "total_safe_scans": stats['total_safe'],
            "safety_rate": stats['safety_rate'],
            "current_streak": stats['current_streak'],
            "allergens_avoided": stats['allergens_avoided'],
            "badges": badges,
            "new_badge_count": new_badge_count,
            "recommendation_tip": recommendation_tip,
            "next_milestone": {
                "target": next_target,
                "current": total_scans,
                "message": f"{next_target - total_scans} more scans to reach {next_target} total scans!"
            }
        }), 200
    except Exception as e:
        return server_error(e)


def evaluate_user_badges(user_id):
    """Unlock badges earned after a new scan. Returns the newly unlocked badges."""
    try:
        now = datetime.now()
        scans = analytics.load_user_scans(db, SCAN_HISTORY_COLLECTION, user_id, now)
        if not scans:
            return []
        stats = analytics.compute_stats(scans, now)
        _, newly_unlocked = analytics.evaluate_badges(db, user_id, stats, now)
        return newly_unlocked
    except Exception as e:
        print(f"Error evaluating badges: {e}")
        return []


# ============= SCAN ENDPOINTS =============

FIRESTORE_BATCH_LIMIT = 450


class _ChunkedBatch:
    """Firestore write batch that commits automatically before hitting the 500-op limit."""

    def __init__(self):
        self._batch = db.batch()
        self._count = 0

    def set(self, ref, data):
        self._batch.set(ref, data)
        self._count += 1
        if self._count >= FIRESTORE_BATCH_LIMIT:
            self.commit()

    def commit(self):
        if self._count:
            self._batch.commit()
        self._batch = db.batch()
        self._count = 0


def record_scan(user_id, data):
    """Persist a scan plus its per-ingredient detail rows.

    Returns ``(scan_id, newly_unlocked_badges)``.
    """
    confidence = data.get('confidence') or data.get('ml_confidence') or 0.0
    if not confidence and (data.get('ingredients') or data.get('raw_text')):
        confidence = 0.85

    now = firestore.SERVER_TIMESTAMP
    risk_level = data.get('risk_level', 'unknown')
    ingredients_list = data.get('ingredients') or []
    allergens_list = data.get('allergens_detected') or []
    ingredient_details = data.get('ingredient_details') or []
    product_name = str(data.get('product_name') or '').strip() or 'Scanned Product'

    scan_ref = db.collection(SCAN_HISTORY_COLLECTION).document()
    scan_ref.set({
        'user_id': user_id,
        'product_name': product_name[:120],
        'ingredients': ingredients_list,
        'ingredient_count': len(ingredients_list),
        'ingredient_details': ingredient_details,
        'risk_level': risk_level,
        'safety_classification': data.get('safety_classification', risk_level),
        'risk_score': data.get('risk_score', 0),
        'alerts': data.get('alerts', []),
        'recommendations': data.get('recommendations', []),
        'confidence': confidence,
        'image_quality_score': confidence,
        'detection_method': data.get('detection_method', 'ML/NLP Analysis'),
        'allergens_detected': allergens_list,
        'allergen_count': len(allergens_list),
        'personal_allergens_detected': data.get('personal_allergens_detected', []),
        'raw_text': data.get('raw_text', ''),
        'was_edited': bool(data.get('was_edited', False)),
        'input_image_url': data.get('input_image_url', data.get('image_url', '')),
        'processing_time_ms': data.get('processing_time_ms', 0),
        'scan_date': now,
        'scanned_at': now,
        'timestamp': now
    })
    scan_id = scan_ref.id

    batch = _ChunkedBatch()
    for ingredient in ingredient_details:
        if not isinstance(ingredient, dict):
            continue
        matches = [m for m in ingredient.get('matches', []) if isinstance(m, dict)]
        ingredient_ref = db.collection(PRODUCT_INGREDIENTS_COLLECTION).document()
        batch.set(ingredient_ref, {
            'scan_id': scan_id,
            'user_id': user_id,
            'ingredient_name': ingredient.get('ingredient', ''),
            'normalized_name': ingredient.get('normalized', ''),
            'related_allergens': [m.get('name', '') for m in matches
                                  if m.get('type') == 'allergen' and m.get('name')],
            'status': ingredient.get('status', 'safe'),
            'confidence': ingredient.get('confidence', 0.0),
            'created_at': now,
        })
        for match in matches:
            batch.set(db.collection(INGREDIENT_MATCHES_COLLECTION).document(), {
                'scan_id': scan_id,
                'ingredient_id': ingredient_ref.id,
                'user_id': user_id,
                'match_type': match.get('type', ''),
                'restriction_id': match.get('id', ''),
                'restriction_name': match.get('name', ''),
                'allergen_keyword': match.get('keyword', ''),
                'keyword': match.get('keyword', ''),
                'severity': match.get('severity', ''),
                'match_timestamp': now,
            })
    batch.commit()

    return scan_id, evaluate_user_badges(user_id)


@app.route('/users/<user_id>/scans', methods=['POST'])
@require_user
def add_scan(user_id):
    try:
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            return jsonify({'error': 'Scan data must be a JSON object'}), 400
        if not db.collection('users').document(user_id).get().exists:
            return jsonify({'message': 'User not found'}), 404

        scan_id, newly_unlocked_badges = record_scan(user_id, data)
        return jsonify({
            'scan_id': scan_id,
            'message': 'Scan recorded successfully',
            'newly_unlocked_badges': newly_unlocked_badges
        }), 201
    except Exception as e:
        return server_error(e)


@app.route('/users/<user_id>/scans', methods=['GET'])
@require_user
def get_user_scans(user_id):
    """Get the user's scan history, newest first."""
    try:
        user_ref = db.collection('users').document(user_id).get()
        if not user_ref.exists:
            return jsonify({'error': 'User not found'}), 404

        scans = []
        seen_ids = set()

        for collection_name in (SCAN_HISTORY_COLLECTION, LEGACY_SCANS_COLLECTION):
            try:
                for scan in db.collection(collection_name).where('user_id', '==', user_id).stream():
                    if scan.id in seen_ids:
                        continue
                    scan_data = scan.to_dict()
                    scan_data['id'] = scan.id
                    scan_data['source_collection'] = collection_name
                    scans.append(scan_data)
                    seen_ids.add(scan.id)
            except Exception as e:
                print(f"Error querying '{collection_name}': {e}")

        scans.sort(key=lambda x: analytics.scan_time(x, datetime.min), reverse=True)

        for scan in scans:
            for timestamp_field in ('scan_date', 'scanned_at', 'timestamp'):
                if scan.get(timestamp_field):
                    scan[timestamp_field] = _timestamp_to_string(scan[timestamp_field])
            scan.setdefault('scanned_at', scan.get('scan_date', scan.get('timestamp', '')))
            scan.setdefault('product_name', 'Unknown Product')
            scan.setdefault('ingredients', [])
            scan.setdefault('ingredient_count', len(scan.get('ingredients', [])))
            scan.setdefault('risk_level', 'unknown')
            scan.setdefault('safety_classification', scan.get('risk_level', 'unknown'))
            scan.setdefault('risk_score', 0)
            scan.setdefault('alerts', [])
            scan.setdefault('confidence', 0.0)
            scan.setdefault('image_quality_score', scan.get('confidence', 0.0))
            scan.setdefault('allergens_detected', [])
            scan.setdefault('allergen_count', len(scan.get('allergens_detected', [])))
            scan.setdefault('detection_method', 'ML/NLP Analysis')
            scan.setdefault('processing_time_ms', 0)

        return jsonify(scans), 200
    except Exception as e:
        return server_error(e)


@app.route('/users/<user_id>/scans/<scan_id>', methods=['DELETE'])
@require_user
def delete_scan(user_id, scan_id):
    """Delete one of the user's scans and its ingredient detail rows."""
    try:
        deleted = False
        for collection_name in (SCAN_HISTORY_COLLECTION, LEGACY_SCANS_COLLECTION):
            scan_ref = db.collection(collection_name).document(scan_id)
            snapshot = scan_ref.get()
            if not snapshot.exists:
                continue
            if (snapshot.to_dict() or {}).get('user_id') != user_id:
                return jsonify({'error': 'Scan not found'}), 404
            scan_ref.delete()
            deleted = True

        if not deleted:
            return jsonify({'error': 'Scan not found'}), 404

        for collection_name in (PRODUCT_INGREDIENTS_COLLECTION, INGREDIENT_MATCHES_COLLECTION):
            _delete_query(db.collection(collection_name)
                          .where('scan_id', '==', scan_id)
                          .where('user_id', '==', user_id))

        return jsonify({'success': True, 'message': 'Scan deleted successfully'}), 200
    except Exception as e:
        return server_error(e)


# ============= SCAN FOR USER ENDPOINT =============
@app.route('/scan/<user_id>', methods=['POST'])
@require_user
def scan_for_user(user_id):
    """Scan food label for a specific user"""
    start_time = time.time()
    try:
        if 'image' not in request.files:
            return jsonify({'error': 'No image uploaded'}), 400
        
        image_file = request.files['image']
        image_bytes = image_file.read()
        
        result = processor.process_scan(image_bytes, user_id)
        if not result['success']:
            return jsonify({'error': result['error']}), 500
            
        processing_time_ms = int((time.time() - start_time) * 1000)
        result['processing_time_ms'] = processing_time_ms
        
        scan_id = save_scan_history(user_id, result)
        if scan_id:
            result['scan_id'] = scan_id
        
        similar_products = find_similar_products(result.get('ingredients', []))
        if similar_products:
            result['similar_products'] = similar_products
        
        return jsonify(result), 200
    except Exception as e:
        return server_error(e)


def save_scan_history(user_id, scan_result):
    try:
        analysis = scan_result.get('analysis', {})
        confidence = analysis.get('confidence', 0.0)
        now = firestore.SERVER_TIMESTAMP
        risk_level = analysis.get('risk_level', 'unknown')
        
        ingredients_list = scan_result.get('ingredients', [])
        allergens_list = scan_result.get('allergens_detected', analysis.get('allergens_detected', []))
        
        scan_data = {
            'user_id': user_id,
            'product_name': scan_result.get('product_name', 'Unknown Product'),
            'ingredients': ingredients_list,
            'ingredient_count': len(ingredients_list),
            'risk_level': risk_level,
            'safety_classification': risk_level,
            'risk_score': analysis.get('risk_score', 0),
            'alerts': analysis.get('alerts', []),
            'confidence': confidence,
            'image_quality_score': confidence,
            'detection_method': scan_result.get('detection_method', analysis.get('detection_method', 'ML/NLP Analysis')),
            'allergens_detected': allergens_list,
            'allergen_count': len(allergens_list),
            'input_image_url': scan_result.get('input_image_url', ''),
            'processing_time_ms': scan_result.get('processing_time_ms', 0),
            'scan_date': now,
            'scanned_at': now,
            'timestamp': now
        }
        scan_ref = db.collection(SCAN_HISTORY_COLLECTION).add(scan_data)
        return scan_ref[1].id
    except Exception as e:
        print(f"Error saving scan: {e}")
        return None


def find_similar_products(ingredients):
    try:
        products_ref = db.collection('openfoodfacts_products').limit(5).stream()
        products = []
        for product in products_ref:
            products.append(product.to_dict())
        return products
    except Exception as e:
        print(f"Error finding similar products: {e}")
        return []


# ============= EXTRACT INGREDIENTS ENDPOINT =============

@app.route('/extract-ingredients', methods=['POST'])
def extract_ingredients_only():
    try:
        if 'image' not in request.files:
            return jsonify({'error': 'No image uploaded'}), 400
        
        image_file = request.files['image']
        image_bytes = image_file.read()
        
        ocr_result = extract_ingredients(image_bytes)
        if not ocr_result['success']:
            return jsonify({'error': ocr_result['error']}), 400
        
        raw_text = ocr_result.get('raw_text', '')
        raw_ingredients = ocr_result.get('ingredients_list', [])
        
        if raw_ingredients:
            parsed_ingredients = raw_ingredients
        else:
            parsed_ingredients = parse_ingredients_input_v2(raw_text)
        processed_tokens = detector.preprocess_ingredient_text(' '.join(parsed_ingredients))
        
        seen = set()
        cleaned_ingredients = []
        for token in processed_tokens:
            if token not in seen and len(token) > 2:
                seen.add(token)
                cleaned_ingredients.append(token)
        
        return jsonify({
            'success': True,
            'ingredients': parsed_ingredients or cleaned_ingredients,
            'raw_ingredients': raw_ingredients,
            'raw_text': raw_text,
            'cleaned_text': ocr_result.get('cleaned_text', ''),
            'ocr_confidence': ocr_result.get('ocr_confidence', 0.0),
            'ocr_strategy': ocr_result.get('strategy_used', ''),
            'processed_count': len(parsed_ingredients or cleaned_ingredients),
            'raw_count': len(raw_ingredients)
        }), 200
        
    except Exception as e:
        return server_error(e)


# ============= ANALYZE WITH PROFILE ENDPOINT - FULLY FIXED =============

@app.route('/analyze-with-profile', methods=['POST'])
@require_user
def analyze_with_profile():
    """Analyze ingredients text against user's profile.

    Detection pipeline (RF-primary 70/30):
      1. Random Forest (70%) — primary verdict (has_allergens probability)
      2. Rule-based / risk_analyzer (30%) — allergen labels + dietary detail
      3. build_personalized_analysis_v2 — per-ingredient detail labels for UI only
    """
    try:
        data = request.get_json(silent=True) or {}

        # Handle different possible input formats
        ingredients_input = data.get('ingredients_text') or data.get('ingredients')
        user_id = data.get('user_id') or g.get('user_id')

        # CRITICAL FIX: Extract string from nested dictionary
        if isinstance(ingredients_input, dict):
            ingredients_text = (
                ingredients_input.get('text') or
                ingredients_input.get('ingredients') or
                ingredients_input.get('content') or
                ingredients_input.get('value') or
                str(ingredients_input)
            )
        elif isinstance(ingredients_input, list):
            ingredients_text = ', '.join(str(item) for item in ingredients_input if item)
        else:
            ingredients_text = str(ingredients_input) if ingredients_input else ''

        # Clean up any dictionary artifacts
        if ingredients_text.startswith('{') and ingredients_text.endswith('}'):
            try:
                import ast
                parsed = ast.literal_eval(ingredients_text)
                if isinstance(parsed, dict):
                    ingredients_text = parsed.get('text', parsed.get('ingredients', str(parsed)))
            except:
                pass

        # Final validation
        if not ingredients_text or ingredients_text == '{}' or ingredients_text == "{'text': ''}":
            return jsonify({'error': 'No valid ingredients provided'}), 400

        if not user_id:
            return jsonify({'error': 'No user ID provided'}), 400

        # Get user from database
        user_ref = db.collection('users').document(user_id).get()
        if not user_ref.exists:
            return jsonify({'error': 'User not found'}), 404

        user_data = user_ref.to_dict()
        user_allergies = user_data.get('allergies', [])
        user_dietary  = user_data.get('dietary_restrictions', [])

        print(f"\n=== ANALYZE WITH PROFILE (RF-PRIMARY) ===")
        print(f"Input type: {type(ingredients_input)}")
        print(f"Extracted text: {ingredients_text[:100]}...")
        print(f"User allergies: {user_allergies}")
        print(f"User dietary:   {user_dietary}")

        # ── PRIMARY: Random Forest (70%) + Rule-based (30%) via processor ──
        combined = processor.analyze_ingredients(
            ingredients_text,
            user_allergies=user_allergies,
            user_dietary=user_dietary,
            raw_text=ingredients_text,
        )

        risk_level  = combined.get('risk_level', 'safe')
        risk_score  = combined.get('risk_score', 0)
        confidence  = combined.get('confidence', 0.7)
        all_alerts  = combined.get('alerts', [])
        allergens_detected  = combined.get('allergens_detected', [])
        detection_method    = combined.get('detection_method', 'Random Forest (Primary) + Rule-Based')

        # ── SUPPORTING: per-ingredient detail labels for UI (rules only — RF is binary) ──
        ingredients = parse_ingredients_input_v2(ingredients_text)
        detail_analysis  = build_personalized_analysis_v2(
            ingredients_text, user_allergies, user_dietary, ingredients_text
        )
        ingredient_details = detail_analysis.get('ingredient_details', [])

        print(f"Detection Method: {detection_method}")
        print(f"RF Weights: ML={processor.ML_WEIGHT}, Rules={processor.RULE_WEIGHT}")
        print(f"Risk Level: {risk_level}")
        print(f"Risk Score: {risk_score}")
        print(f"Confidence: {confidence}")
        print(f"Allergens:  {allergens_detected}")
        print(f"==========================================")

        recommendations = _get_recommendations(risk_level)

        user_allergy_strings = []
        for allergy in user_allergies:
            if isinstance(allergy, dict):
                user_allergy_strings.append(allergy.get('id', ''))
            else:
                user_allergy_strings.append(str(allergy))

        ocr_conf = float(data.get('ocr_confidence') or combined.get('ocr_confidence') or 0.0)
        if ocr_conf <= 0.0 and ingredients_text:
            ocr_conf = _estimate_ocr_confidence(ingredients_text, ingredients)
        ocr_eng = data.get('ocr_engine') or data.get('ocr_strategy') or combined.get('ocr_engine') or 'OCR.Space API'

        return jsonify({
            'success': True,
            'ingredients': ingredients,
            'ingredient_details': ingredient_details,
            'detection_method': detection_method,
            'risk_level': risk_level,
            'risk_score': risk_score,
            'confidence': confidence,
            'alerts': all_alerts,
            'allergens_detected': allergens_detected,
            'has_allergens': len(allergens_detected) > 0,
            'has_personal_allergens': any(
                a in [str(u.get('id', u) if isinstance(u, dict) else u)
                      for u in user_allergies]
                for a in allergens_detected
            ),
            'recommendations': recommendations,
            'model_info': {
                'rf_loaded': processor.model_loaded,
                'weights': {'random_forest': processor.ML_WEIGHT, 'rule_based': processor.RULE_WEIGHT},
                'ml_confidence': combined.get('ml_confidence', 0.0),
                'rule_confidence': combined.get('rule_confidence', 0.0),
                'ocr_engine': ocr_eng,
                'ocr_confidence': round(ocr_conf, 2),
            },
            'user_profile': {
                'allergies': user_allergy_strings,
                'dietary_restrictions': user_dietary
            }
        }), 200

    except Exception as e:
        print(f"Error in analyze_with_profile: {e}")
        traceback.print_exc()
        return server_error(e)


# ============= TEST-ONLY INLINE ANALYSIS ENDPOINT =============

@app.route('/test/analyze', methods=['POST'])
@debug_only
def test_analyze_inline():
    """
    Accuracy-testing endpoint: accepts allergies/dietary inline, no Firestore lookup.
    NOT intended for production use — only for the test suite.
    """
    try:
        data = request.get_json(silent=True) or {}
        ingredients_text = data.get('ingredients_text', '')
        allergies = data.get('allergies', [])          # list of str or {id, severity}
        dietary = data.get('dietary_restrictions', []) # list of str

        if not ingredients_text:
            return jsonify({'error': 'No ingredients_text provided'}), 400

        # Run NLP analysis with supplied allergies
        nlp_result = detector.analyze_ingredients(ingredients_text, allergies)

        detected_allergens = nlp_result.get('detected_allergens', []) or []
        personal_allergens = nlp_result.get('personal_allergens', []) or []
        risk_level = nlp_result.get('risk_level', 'safe')
        risk_score = nlp_result.get('risk_score', 0)
        confidence = nlp_result.get('confidence', 0.85)
        nlp_alerts = nlp_result.get('alerts', []) or []

        # Check dietary restrictions
        dietary_alerts = []
        if dietary:
            text_lower = ingredients_text.lower()
            for diet_id in dietary:
                if diet_id in dietary_rules():
                    rule = dietary_rules()[diet_id]
                    for forbidden in rule['forbidden']:
                        if forbidden in text_lower:
                            dietary_alerts.append(
                                f"Contains {forbidden} which may violate {rule['name']}"
                            )
        all_alerts = nlp_alerts + dietary_alerts

        # Build ingredient-level details and use combined processing (RF + rules)
        combined = processor.analyze_ingredients(
            ingredients_text,
            user_allergies=allergies,
            user_dietary=dietary,
            raw_text=ingredients_text,
        )
        ingredient_details = combined.get('ingredient_details', [])
        risk_level = combined.get('risk_level', risk_level)
        risk_score = combined.get('risk_score', risk_score)
        all_alerts = combined.get('alerts', all_alerts)
        confidence = combined.get('confidence', confidence)

        return jsonify({
            'success': True,
            'risk_level': risk_level,
            'risk_score': risk_score,
            'confidence': confidence,
            'alerts': all_alerts,
            'allergens_detected': detected_allergens,
            'personal_allergens_detected': personal_allergens,
            'has_allergens': len(detected_allergens) > 0,
            'has_personal_allergens': len(personal_allergens) > 0,
            'ingredient_details': ingredient_details,
            'detection_method': combined.get('detection_method', 'Random Forest (Primary) + Rule-Based'),
        }), 200

    except Exception as e:
        traceback.print_exc()
        return server_error(e)


# ============= BASIC ANALYZE ENDPOINT - FULLY FIXED =============

@app.route('/analyze-ingredients', methods=['POST'])
def analyze_ingredients():
    """Analyze ingredients (no user profile).

    Detection pipeline (RF-primary 70/30):
      1. Random Forest (70%) — primary verdict
      2. Rule-based (30%) — allergen labels + detail
      3. build_general_analysis — per-ingredient labels for UI only
    """
    try:
        data = request.get_json(silent=True) or {}
        ingredients_input = data.get('ingredients_text') or data.get('ingredients')

        if not ingredients_input:
            return jsonify({'error': 'No ingredients provided'}), 400

        # CRITICAL FIX: Extract string from nested dictionary
        if isinstance(ingredients_input, dict):
            ingredients_text = (
                ingredients_input.get('text') or
                ingredients_input.get('ingredients') or
                ingredients_input.get('content') or
                str(ingredients_input)
            )
        elif isinstance(ingredients_input, list):
            ingredients_text = ', '.join(str(item) for item in ingredients_input if item)
        else:
            ingredients_text = str(ingredients_input)

        # Clean up
        if ingredients_text.startswith('{') and ingredients_text.endswith('}'):
            try:
                import ast
                parsed = ast.literal_eval(ingredients_text)
                if isinstance(parsed, dict):
                    ingredients_text = parsed.get('text', parsed.get('ingredients', str(parsed)))
            except:
                pass

        if not ingredients_text or ingredients_text == '{}':
            return jsonify({'error': 'No valid ingredients provided'}), 400

        # ── PRIMARY: Random Forest (70%) + Rule-based (30%) via processor ──
        combined = processor.analyze_ingredients(ingredients_text)

        risk_level         = combined.get('risk_level', 'safe')
        risk_score         = combined.get('risk_score', 0)
        confidence         = combined.get('confidence', 0.7)
        alerts             = combined.get('alerts', [])
        allergens_detected = combined.get('allergens_detected', [])
        detection_method   = combined.get('detection_method', 'Random Forest (Primary) + Rule-Based')

        # ── SUPPORTING: per-ingredient detail labels for UI (rules only — RF is binary) ──
        ingredients = parse_ingredients_input_v2(ingredients_text)
        detail_analysis  = build_general_analysis(ingredients_text)
        ingredient_details = detail_analysis.get('ingredient_details', [])

        print(f"\n=== ANALYZE INGREDIENTS (RF-PRIMARY) ===")
        print(f"Input type: {type(ingredients_input)}")
        print(f"Extracted text: {ingredients_text[:100]}...")
        print(f"Detection Method: {detection_method}")
        print(f"RF Weights: ML={processor.ML_WEIGHT}, Rules={processor.RULE_WEIGHT}")
        print(f"Risk Level: {risk_level}")
        print(f"Allergens: {allergens_detected}")
        print(f"Confidence: {confidence}")
        print(f"=========================================")

        recommendations = _get_recommendations(risk_level)

        ocr_conf = float(data.get('ocr_confidence') or combined.get('ocr_confidence') or 0.0)
        if ocr_conf <= 0.0 and ingredients_text:
            ocr_conf = _estimate_ocr_confidence(ingredients_text, ingredients)
        ocr_eng = data.get('ocr_engine') or data.get('ocr_strategy') or combined.get('ocr_engine') or 'OCR.Space API'

        return jsonify({
            'success': True,
            'ingredients': ingredients,
            'ingredient_details': ingredient_details,
            'detection_method': detection_method,
            'risk_level': risk_level,
            'risk_score': risk_score,
            'confidence': confidence,
            'alerts': alerts,
            'allergens_detected': allergens_detected,
            'has_allergens': len(allergens_detected) > 0,
            'model_info': {
                'rf_loaded': processor.model_loaded,
                'weights': {'random_forest': processor.ML_WEIGHT, 'rule_based': processor.RULE_WEIGHT},
                'ml_confidence': combined.get('ml_confidence', 0.0),
                'rule_confidence': combined.get('rule_confidence', 0.0),
                'ocr_engine': ocr_eng,
                'ocr_confidence': round(ocr_conf, 2),
            },
            'recommendations': recommendations,
            'message': 'Create a user profile for personalized allergen detection based on your specific allergies'
        }), 200

    except Exception as e:
        print(f"Error in analyze_ingredients: {e}")
        traceback.print_exc()
        return server_error(e)


# ============= DIETARY OPTIONS ENDPOINTS =============

@app.route('/dietary-options', methods=['GET'])
def get_dietary_options():
    try:
        options = get_options_by_category()
        return jsonify({'success': True, 'options': options}), 200
    except Exception as e:
        return server_error(e)


@app.route('/dietary-options/allergens', methods=['GET'])
def get_allergen_options():
    try:
        from dietary_options import ALLERGEN_OPTIONS
        return jsonify({'success': True, 'allergens': ALLERGEN_OPTIONS}), 200
    except Exception as e:
        return server_error(e)


@app.route('/dietary-options/dietary', methods=['GET'])
def get_dietary_only_options():
    try:
        from dietary_options import DIETARY_OPTIONS
        return jsonify({'success': True, 'dietary': DIETARY_OPTIONS}), 200
    except Exception as e:
        return server_error(e)


# ============= USER PROFILE CRUD ENDPOINTS =============

@app.route('/users/<user_id>/profile', methods=['GET'])
@require_user
def get_user_profile(user_id):
    try:
        user_ref = db.collection('users').document(user_id).get()
        if not user_ref.exists:
            return jsonify({'message': 'User not found'}), 404
        
        user_data = user_ref.to_dict()
        profile = {
            'user_id': user_id,
            'username': user_data.get('username', ''),
            'email': user_data.get('email', ''),
            'allergies': user_data.get('allergies', []),
            'dietary_restrictions': user_data.get('dietary_restrictions', []),
            'created_at': str(user_data.get('created_at', '')),
            'updated_at': str(user_data.get('updated_at', '')) if 'updated_at' in user_data else None
        }
        return jsonify({'success': True, 'profile': profile}), 200
    except Exception as e:
        return server_error(e)


@app.route('/users/<user_id>/profile', methods=['PUT'])
@require_user
def update_user_profile(user_id):
    """Update user's account information and dietary profile."""
    try:
        data = request.get_json() or {}
        user_ref = db.collection('users').document(user_id)
        if not user_ref.get().exists:
            return jsonify({'message': 'User not found'}), 404
        
        update_data = {}
        
        if 'allergies' in data:
            allergies = data['allergies']
            if not isinstance(allergies, list):
                return jsonify({'error': 'Allergies must be a list'}), 400
            update_data['allergies'] = allergies
        
        if 'dietary_restrictions' in data:
            restrictions = data['dietary_restrictions']
            if not isinstance(restrictions, list):
                return jsonify({'error': 'Dietary restrictions must be a list'}), 400
            update_data['dietary_restrictions'] = restrictions

        if 'username' in data:
            username = str(data.get('username', '')).strip()
            if len(username) < 3:
                return jsonify({'error': 'Name must be at least 3 characters'}), 400
            update_data['username'] = username

        if 'email' in data:
            email = str(data.get('email', '')).strip().lower()
            if not re.match(r'^[^@\s]+@[^@\s]+\.[^@\s]+$', email):
                return jsonify({'error': 'Invalid email address'}), 400
            matching_users = db.collection('users').where('email', '==', email).limit(2).get()
            for user_doc in matching_users:
                if user_doc.id != user_id:
                    return jsonify({'error': 'Email is already in use'}), 409
            update_data['email'] = email

        if data.get('password'):
            password = str(data.get('password'))
            if len(password) < 6:
                return jsonify({'error': 'Password must be at least 6 characters'}), 400
            update_data['password_hash'] = hash_password(password)
        
        update_data['updated_at'] = firestore.SERVER_TIMESTAMP
        user_ref.update(update_data)
        
        updated_user = user_ref.get().to_dict()
        return jsonify({
            'success': True,
            'message': 'Profile updated successfully',
            'profile': {
                'user_id': user_id,
                'username': updated_user.get('username', ''),
                'email': updated_user.get('email', ''),
                'allergies': updated_user.get('allergies', []),
                'dietary_restrictions': updated_user.get('dietary_restrictions', [])
            }
        }), 200
        
    except Exception as e:
        return server_error(e)


@app.route('/users/<user_id>/profile/restrictions', methods=['POST'])
@require_user
def add_restriction(user_id):
    try:
        data = request.get_json(silent=True) or {}
        restriction_type = data.get('type')
        restriction_id = data.get('id')
        
        if not restriction_type or not restriction_id:
            return jsonify({'error': 'Missing type or id'}), 400
        
        user_ref = db.collection('users').document(user_id)
        user_data = user_ref.get().to_dict()
        if not user_data:
            return jsonify({'message': 'User not found'}), 404
        
        field = 'allergies' if restriction_type == 'allergy' else 'dietary_restrictions'
        current_list = user_data.get(field, [])
        
        if restriction_id not in current_list:
            current_list.append(restriction_id)
            user_ref.update({field: current_list, 'updated_at': firestore.SERVER_TIMESTAMP})

        restriction_doc_id = f"{user_id}_{restriction_type}_{restriction_id}"
        db.collection(DIETARY_RESTRICTIONS_COLLECTION).document(restriction_doc_id).set({
            'user_id': user_id,
            'restriction_name': restriction_id,
            'restriction_type': restriction_type,
            'status': 'active',
            'updated_at': firestore.SERVER_TIMESTAMP,
        }, merge=True)
        
        return jsonify({'success': True, 'message': f'Added {restriction_id} to {field}', field: current_list}), 200
    except Exception as e:
        return server_error(e)


@app.route('/users/<user_id>/profile/restrictions/<restriction_id>', methods=['DELETE'])
@require_user
def remove_restriction(user_id, restriction_id):
    try:
        restriction_type = request.args.get('type', 'allergy')
        user_ref = db.collection('users').document(user_id)
        user_data = user_ref.get().to_dict()
        if not user_data:
            return jsonify({'message': 'User not found'}), 404
        
        field = 'allergies' if restriction_type == 'allergy' else 'dietary_restrictions'
        current_list = user_data.get(field, [])
        
        if restriction_id in current_list:
            current_list.remove(restriction_id)
            user_ref.update({field: current_list, 'updated_at': firestore.SERVER_TIMESTAMP})

        restriction_doc_id = f"{user_id}_{restriction_type}_{restriction_id}"
        db.collection(DIETARY_RESTRICTIONS_COLLECTION).document(restriction_doc_id).set({
            'user_id': user_id,
            'restriction_name': restriction_id,
            'restriction_type': restriction_type,
            'status': 'inactive',
            'updated_at': firestore.SERVER_TIMESTAMP,
        }, merge=True)
        
        return jsonify({'success': True, 'message': f'Removed {restriction_id} from {field}', field: current_list}), 200
    except Exception as e:
        return server_error(e)


@app.route('/users/<user_id>/profile/check', methods=['POST'])
@require_user
def check_ingredients_against_profile(user_id):
    try:
        data = request.get_json(silent=True) or {}
        ingredients = data.get('ingredients', [])
        if not ingredients:
            return jsonify({'error': 'No ingredients provided'}), 400
        
        user_ref = db.collection('users').document(user_id).get()
        if not user_ref.exists:
            return jsonify({'message': 'User not found'}), 404
        
        user_data = user_ref.to_dict()
        user_allergies = user_data.get('allergies', [])
        user_dietary = user_data.get('dietary_restrictions', [])
        
        # Convert ingredients list to text for NLP
        ingredients_text = ', '.join(ingredients) if isinstance(ingredients, list) else str(ingredients)
        
        # Use ML/NLP detector
        nlp_result = detector.analyze_ingredients(ingredients_text, user_allergies)
        
        # Get results
        risk_level = nlp_result.get('risk_level', 'safe')
        risk_score = nlp_result.get('risk_score', 0)
        confidence = nlp_result.get('confidence', 0.85)
        alerts = nlp_result.get('alerts', [])
        detected_allergens = nlp_result.get('detected_allergens', [])
        personal_allergens = nlp_result.get('personal_allergens', [])
        
        # Check dietary restrictions
        dietary_alerts = []
        if user_dietary:
            ingredients_lower = ingredients_text.lower()
            for diet_id in user_dietary:
                if diet_id in dietary_rules():
                    rule = dietary_rules()[diet_id]
                    for forbidden in rule['forbidden']:
                        if forbidden in ingredients_lower:
                            dietary_alerts.append(f"Contains {forbidden} which may violate {rule['name']}")
        
        all_alerts = alerts + dietary_alerts
        
        return jsonify({
            'success': True,
            'risk_level': risk_level,
            'risk_score': risk_score,
            'confidence': confidence,
            'alerts': all_alerts,
            'allergen_alerts': alerts,
            'dietary_alerts': dietary_alerts,
            'allergens_detected': detected_allergens,
            'personal_allergens_detected': personal_allergens,
            'ingredients_checked': ingredients
        }), 200
    except Exception as e:
        return server_error(e)


if __name__ == '__main__':
    print("=" * 50)
    print("BiteRight API Starting...")
    print("=" * 50)
    print("Root endpoint: http://127.0.0.1:5000/")
    print("Health check: http://127.0.0.1:5000/health")
    print("Test Firebase: http://127.0.0.1:5000/test-firebase")
    print("Dietary options: http://127.0.0.1:5000/dietary-options")
    print("Extract ingredients: http://127.0.0.1:5000/extract-ingredients")
    print("Analyze ingredients: http://127.0.0.1:5000/analyze-ingredients")
    print("Analyze with profile: http://127.0.0.1:5000/analyze-with-profile")
    print("=" * 50)
    print("ML/NLP Model: ACTIVE")
    print("Detection Method: Pattern Matching + Keyword Analysis")
    print("=" * 50)
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)