import sys
sys.stdout.reconfigure(encoding='utf-8')

import os
import time
from datetime import datetime, timedelta
from flask import Flask, jsonify, request
from flask_cors import CORS
import firebase_admin
from firebase_admin import credentials, firestore, auth
import re
import hashlib
import secrets
from datetime import datetime

# Import your services
from services.ocr_service import extract_ingredients, _estimate_ocr_confidence
from services.nlp_service import detector, AllergenDetector
from services.processing_service import IngredientProcessor
from services.risk_analyzer import (
    build_general_analysis,
    build_personalized_analysis as build_personalized_analysis_v2,
    parse_ingredients_input as parse_ingredients_input_v2,
)
from dietary_options import get_all_options, get_options_by_category

# Initialize Flask
app = Flask(__name__)
CORS(app)  # Enable CORS for all routes

# Initialize Firebase
try:
    firebase_admin.get_app()
except ValueError:
    cred = credentials.Certificate('serviceAccountKey.json')
    firebase_admin.initialize_app(cred)

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

def hash_password(password):
    """Hash password with salt"""
    salt = secrets.token_hex(16)
    hashed = hashlib.sha256((password + salt).encode()).hexdigest()
    return f"{hashed}:{salt}"

def verify_password(password, stored_hash):
    """Verify password against stored hash"""
    if ':' not in stored_hash:
        return False
    hashed, salt = stored_hash.split(':')
    return hashed == hashlib.sha256((password + salt).encode()).hexdigest()

def normalize_key(value):
    return str(value or '').strip().lower().replace('-', '_').replace(' ', '_')

def scan_timestamp(scan_data):
    """Return the best timestamp field while old and ERD-shaped docs coexist."""
    return scan_data.get('scan_date') or scan_data.get('scanned_at') or scan_data.get('timestamp') or ''

def parse_ingredients_input(ingredients_input):
    if isinstance(ingredients_input, list):
        return [str(item).strip().lower() for item in ingredients_input if str(item).strip()]

    text = str(ingredients_input or '')
    text = re.sub(r'INGREDIENTS:?\s*', '', text, flags=re.IGNORECASE)
    text = re.sub(r'CONTAINS:?\s*', '', text, flags=re.IGNORECASE)

    ingredients = []
    for part in re.split(r',|;|\n', text):
        for subpart in re.split(r'\s+and\s+', part, flags=re.IGNORECASE):
            ingredient = subpart.strip().lower()
            if ingredient and len(ingredient) > 1:
                ingredients.append(ingredient)
    return ingredients or [text.strip().lower()]

def allergen_rules():
    return [
        {'id': 'peanuts', 'name': 'Peanuts', 'severity': 'high', 'keywords': ['peanut', 'peanuts', 'ground nut', 'arachis']},
        {'id': 'tree_nuts', 'name': 'Tree Nuts', 'severity': 'high', 'keywords': ['almond', 'walnut', 'cashew', 'pecan', 'pistachio', 'hazelnut', 'macadamia', 'tree nut', 'tree nuts', 'coconut']},
        {'id': 'milk', 'name': 'Milk/Dairy', 'severity': 'medium', 'keywords': ['milk', 'dairy', 'whey', 'casein', 'lactose', 'butter', 'cream', 'cheese', 'yogurt', 'ghee']},
        {'id': 'eggs', 'name': 'Eggs', 'severity': 'medium', 'keywords': ['egg', 'eggs', 'albumin', 'ovalbumin', 'mayonnaise']},
        {'id': 'soy', 'name': 'Soy', 'severity': 'medium', 'keywords': ['soy', 'soya', 'tofu', 'tempeh', 'edamame', 'soy lecithin', 'soy sauce', 'miso']},
        {'id': 'wheat', 'name': 'Wheat', 'severity': 'medium', 'keywords': ['wheat', 'flour', 'semolina', 'spelt', 'durum', 'farina', 'couscous']},
        {'id': 'gluten', 'name': 'Gluten', 'severity': 'medium', 'keywords': ['gluten', 'wheat', 'barley', 'rye', 'malt', 'seitan']},
        {'id': 'fish', 'name': 'Fish', 'severity': 'high', 'keywords': ['fish', 'salmon', 'tuna', 'cod', 'mackerel', 'anchovy', 'sardine', 'trout', 'fish oil', 'fish sauce']},
        {'id': 'shellfish', 'name': 'Shellfish', 'severity': 'high', 'keywords': ['shrimp', 'prawn', 'crab', 'lobster', 'crayfish', 'shellfish', 'oyster', 'clam', 'mussel', 'scallop']},
        {'id': 'sesame', 'name': 'Sesame', 'severity': 'medium', 'keywords': ['sesame', 'tahini', 'sesamol', 'gingelly', 'sesame seed', 'sesame oil']},
    ]

def dietary_rules():
    return {
        'halal': {'name': 'Halal', 'severity': 'high', 'forbidden': ['pork', 'ham', 'bacon', 'lard', 'alcohol', 'wine', 'beer', 'gelatin']},
        'vegetarian': {'name': 'Vegetarian', 'severity': 'medium', 'forbidden': ['beef', 'chicken', 'pork', 'fish', 'meat', 'gelatin']},
        'vegan': {'name': 'Vegan', 'severity': 'medium', 'forbidden': ['milk', 'dairy', 'whey', 'casein', 'egg', 'honey', 'gelatin', 'butter', 'cheese', 'yogurt']},
        'diabetic': {'name': 'Diabetic / Low Sugar', 'severity': 'high', 'forbidden': ['sugar', 'syrup', 'honey', 'dextrose', 'corn syrup', 'glucose', 'sucrose', 'fructose', 'maltose']},
        'low_sodium': {'name': 'Low Sodium', 'severity': 'low', 'forbidden': ['salt', 'sodium', 'monosodium glutamate', 'msg']},
        'keto': {'name': 'Keto', 'severity': 'medium', 'forbidden': ['sugar', 'wheat', 'rice', 'corn', 'potato', 'starch', 'syrup', 'honey', 'bread', 'pasta']},
    }

def selected_allergy_ids(user_allergies):
    ids = set()
    severity_by_id = {}
    for allergy in user_allergies:
        if isinstance(allergy, dict):
            allergy_id = normalize_key(allergy.get('id'))
            severity_by_id[allergy_id] = allergy.get('severity', 'medium')
        else:
            allergy_id = normalize_key(allergy)
            severity_by_id[allergy_id] = 'medium'
        ids.add(allergy_id)
    return ids, severity_by_id

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


@app.before_request
def initialize_once():
    """Load allergen data from Firestore before first request"""
    global _initialized
    if not _initialized:
        print("=" * 50)
        print("Initializing BiteRight Backend...")
        print("=" * 50)
        print("Loading allergen database...")
        detector.load_allergens_from_firestore(db)
        
        # Initialize processor if available
        try:
            processor.initialize()
            print("Ingredient processor initialized")
        except Exception as e:
            print(f"Processor initialization warning: {e}")
        
        print("Allergen database loaded!")
        print("ML/NLP model is ACTIVE and will be used for analysis")
        print("=" * 50)
        _initialized = True


# ============= API ENDPOINTS =============

@app.route('/')
def home():
    return jsonify({
        "message": "BiteRight API is running with Firebase!",
        "version": "2.0",
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
        'firebase_connected': True,
        'timestamp': datetime.now().isoformat()
    }), 200


# ============= TEST ENDPOINT =============
@app.route('/test-firebase')
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
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/test-products', methods=['GET'])
def test_products():
    try:
        products_ref = db.collection('openfoodfacts_products').limit(5).stream()
        products = []
        for product in products_ref:
            products.append(product.to_dict())
        return jsonify({'count': len(products), 'products': products})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/search-allergens/<allergen>', methods=['GET'])
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
        return jsonify({'error': str(e)}), 500


# ============= USER ENDPOINTS =============

@app.route('/users', methods=['POST'])
def create_user():
    try:
        data = request.get_json()
        if not data or not data.get('username') or not data.get('email') or not data.get('password'):
            return jsonify({'error': 'Missing username, email or password'}), 400
        
        allergies = data.get('allergies', [])
        dietary_restrictions = data.get('dietary_restrictions', [])
        
        existing_users = db.collection('users').where('email', '==', data['email']).limit(1).get()
        if len(list(existing_users)) > 0:
            return jsonify({'error': 'User with this email already exists'}), 409
        
        hashed_password = hash_password(data['password'])
        
        user_ref = db.collection('users').add({
            'username': data['username'],
            'email': data['email'],
            'password_hash': hashed_password,
            'allergies': allergies,
            'dietary_restrictions': dietary_restrictions,
            'created_at': firestore.SERVER_TIMESTAMP,
            'updated_at': firestore.SERVER_TIMESTAMP
        })
        
        return jsonify({
            'id': user_ref[1].id,
            'message': 'User created successfully',
            'user': {
                'id': user_ref[1].id,
                'username': data['username'],
                'email': data['email'],
                'allergies': allergies,
                'dietary_restrictions': dietary_restrictions
            }
        }), 201
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/login', methods=['POST'])
def login():
    try:
        data = request.get_json()
        if not data or not data.get('email') or not data.get('password'):
            return jsonify({'error': 'Missing email or password'}), 400
        
        users_ref = db.collection('users').where('email', '==', data['email']).limit(1).stream()
        user_list = list(users_ref)
        
        if not user_list:
            return jsonify({'error': 'Invalid email or password'}), 401
        
        user_doc = user_list[0]
        user_data = user_doc.to_dict()
        
        stored_hash = user_data.get('password_hash', '')
        if not verify_password(data['password'], stored_hash):
            return jsonify({'error': 'Invalid email or password'}), 401
        
        return jsonify({
            'success': True,
            'user': {
                'id': user_doc.id,
                'username': user_data.get('username', ''),
                'email': user_data.get('email', ''),
                'allergies': user_data.get('allergies', []),
                'dietary_restrictions': user_data.get('dietary_restrictions', [])
            }
        }), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/reset-password-request', methods=['POST'])
def reset_password_request():
    try:
        data = request.get_json()
        if not data or not data.get('email'):
            return jsonify({'error': 'Missing email'}), 400
        
        email = data['email'].strip().lower()
        users_ref = db.collection('users').where('email', '==', email).limit(1).stream()
        user_list = list(users_ref)
        
        if not user_list:
            return jsonify({'error': 'User with this email does not exist'}), 404
        
        user_doc = user_list[0]
        # Generate a random 6-digit OTP code using secrets
        otp_code = f"{secrets.randbelow(1000000):06d}"
        
        db.collection('users').document(user_doc.id).update({
            'reset_code': otp_code,
            'reset_code_expires': datetime.now() + timedelta(minutes=15)
        })
        
        print(f"PASSWORD RESET REQUEST: Email: {email}, Code: {otp_code}")
        
        return jsonify({
            'success': True,
            'message': 'Reset code generated successfully',
            'code': otp_code  # Return code in response for easy demo testing
        }), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/reset-password', methods=['POST'])
def reset_password_route():
    try:
        data = request.get_json()
        if not data or not data.get('email') or not data.get('code') or not data.get('new_password'):
            return jsonify({'error': 'Missing email, code or new_password'}), 400
        
        email = data['email'].strip().lower()
        code = data['code'].strip()
        new_password = data['new_password']
        
        if len(new_password) < 6:
            return jsonify({'error': 'Password must be at least 6 characters'}), 400
            
        users_ref = db.collection('users').where('email', '==', email).limit(1).stream()
        user_list = list(users_ref)
        
        if not user_list:
            return jsonify({'error': 'User with this email does not exist'}), 404
            
        user_doc = user_list[0]
        user_data = user_doc.to_dict()
        
        stored_code = user_data.get('reset_code')
        if not stored_code or stored_code != code:
            return jsonify({'error': 'Invalid reset code'}), 400
            
        # Update the password
        hashed_password = hash_password(new_password)
        db.collection('users').document(user_doc.id).update({
            'password_hash': hashed_password,
            'reset_code': None,
            'reset_code_expires': None
        })
        
        return jsonify({
            'success': True,
            'message': 'Password has been reset successfully'
        }), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/users', methods=['GET'])
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
        return jsonify({'error': str(e)}), 500


@app.route('/users/<user_id>', methods=['GET'])
def get_user(user_id):
    try:
        user_ref = db.collection('users').document(user_id).get()
        if user_ref.exists:
            user_data = user_ref.to_dict()
            user_data.pop('password_hash', None)
            user_data['id'] = user_ref.id
            if 'created_at' in user_data:
                user_data['created_at'] = str(user_data['created_at'])
            return jsonify(user_data), 200
        else:
            return jsonify({'message': 'User not found'}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/users/<user_id>', methods=['PUT'])
def update_user(user_id):
    try:
        user_ref = db.collection('users').document(user_id)
        if user_ref.get().exists:
            data = request.get_json() or {}
            data.pop('password_hash', None)
            if data.get('password'):
                data['password_hash'] = hash_password(data.pop('password'))
            else:
                data.pop('password', None)
            data['updated_at'] = firestore.SERVER_TIMESTAMP
            user_ref.update(data)
            return jsonify({'message': 'User updated successfully'}), 200
        else:
            return jsonify({'message': 'User not found'}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/users/<user_id>', methods=['DELETE'])
def delete_user(user_id):
    try:
        user_ref = db.collection('users').document(user_id)
        if user_ref.get().exists:
            user_ref.delete()
            return jsonify({'message': 'User deleted successfully'}), 200
        else:
            return jsonify({'message': 'User not found'}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/user/<user_id>/stats', methods=['GET'])
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
        recent_scans.sort(key=lambda item: str(scan_timestamp(item)), reverse=True)
        recent_scans = recent_scans[:10]
        
        return jsonify({
            'total_scans': total_scans,
            'risk_breakdown': risk_counts,
            'recent_scans': recent_scans
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/users/<user_id>/analytics/summary', methods=['GET'])
def get_analytics_summary(user_id):
    try:
        user_ref = db.collection('users').document(user_id).get()
        if not user_ref.exists:
            return jsonify({'error': 'User not found'}), 404
        
        now = datetime.now()
        thirty_days_ago = now - timedelta(days=30)
        sixty_days_ago = now - timedelta(days=60)
        seven_days_ago = now - timedelta(days=7)
        
        scans_ref = db.collection(SCAN_HISTORY_COLLECTION).where('user_id', '==', user_id).stream()
        scans = []
        for scan in scans_ref:
            data = scan.to_dict()
            ts = data.get('scan_date') or data.get('scanned_at') or data.get('timestamp')
            scan_time = now
            if ts:
                try:
                    if hasattr(ts, 'timestamp'):
                        scan_time = datetime.fromtimestamp(ts.timestamp())
                    elif isinstance(ts, str):
                        scan_time = datetime.fromisoformat(ts.replace('Z', '+00:00'))
                except:
                    pass
            data['parsed_time'] = scan_time
            scans.append(data)
            
        scans.sort(key=lambda x: x['parsed_time'])
        total_scans = len(scans)
        
        total_safe = sum(1 for s in scans if s.get('risk_level') == 'safe')
        safety_rate = (total_safe / total_scans * 100) if total_scans > 0 else 0
        allergens_avoided = sum(1 for s in scans if s.get('risk_level') == 'unsafe')
        
        last_7_scans = [s for s in scans if s['parsed_time'] >= seven_days_ago]
        last_30_scans = [s for s in scans if s['parsed_time'] >= thirty_days_ago]
        prev_30_scans = [s for s in scans if sixty_days_ago <= s['parsed_time'] < thirty_days_ago]
        
        # Helper to categorize scans
        def process_scans(scan_list, start_time):
            filtered = [s for s in scan_list if s['parsed_time'] >= start_time]
            total = len(filtered)
            safe = sum(1 for s in filtered if s.get('risk_level') == 'safe')
            unsafe = sum(1 for s in filtered if s.get('risk_level') == 'unsafe')
            caution = sum(1 for s in filtered if s.get('risk_level') == 'caution')
            safe_pct = (safe / total * 100) if total > 0 else 0
            
            allergens = {}
            confidence_sum = 0
            categories = {}
            for s in filtered:
                confidence_sum += float(s.get('confidence', 0))
                for allergen in s.get('allergens_detected', []):
                    allergens[allergen] = allergens.get(allergen, 0) + 1
                name_words = s.get('product_name', '').split()
                if name_words and name_words[0] != 'Unknown':
                    cat = name_words[-1] if len(name_words) > 0 else 'Unknown'
                    categories[cat] = categories.get(cat, 0) + 1
                    
            top_allergen = max(allergens.items(), key=lambda x: x[1])[0] if allergens else "None"
            avg_conf = (confidence_sum / total) if total > 0 else 0
            top_categories = [k for k, v in sorted(categories.items(), key=lambda item: item[1], reverse=True)[:3]]
            
            return {
                'total': total, 'safe': safe, 'unsafe': unsafe, 'caution': caution,
                'safe_pct': safe_pct, 'top_allergen': top_allergen, 'avg_conf': avg_conf,
                'top_categories': top_categories, 'filtered_scans': filtered
            }

        week_stats = process_scans(scans, seven_days_ago)
        month_stats = process_scans(scans, thirty_days_ago)
        prev_month_stats = process_scans([s for s in scans if s['parsed_time'] < thirty_days_ago], sixty_days_ago)
        
        scans_by_day = [0] * 7
        for s in week_stats['filtered_scans']:
            days_ago = (now.date() - s['parsed_time'].date()).days
            if 0 <= days_ago < 7:
                scans_by_day[6 - days_ago] += 1
                
        scans_by_week = [0] * 4
        for s in month_stats['filtered_scans']:
            days_ago = (now.date() - s['parsed_time'].date()).days
            if 0 <= days_ago < 28:
                scans_by_week[3 - (days_ago // 7)] += 1
                
        prev_safe_pct = prev_month_stats['safe_pct']
        curr_safe_pct = month_stats['safe_pct']
        improvement = curr_safe_pct - prev_safe_pct
        prev_total = prev_month_stats['total']
        curr_total = month_stats['total']
        scans_increase = ((curr_total - prev_total) / prev_total * 100) if prev_total > 0 else (100 if curr_total > 0 else 0)
        trend = "improving" if improvement > 0 else ("stable" if improvement == 0 else "decreasing")

        # Current Streak
        current_streak = 0
        if scans:
            unique_days = sorted(list(set(s['parsed_time'].date() for s in scans)), reverse=True)
            if unique_days and (now.date() - unique_days[0]).days <= 1:
                current_streak = 1
                for i in range(1, len(unique_days)):
                    if (unique_days[i-1] - unique_days[i]).days == 1:
                        current_streak += 1
                    else:
                        break

        # Calculate unique categories and ingredients
        categories = set()
        unique_ingredients = set()
        for s in scans:
            name_words = s.get('product_name', '').split()
            if name_words and name_words[0] != 'Unknown':
                categories.add(name_words[-1])
            for ing in s.get('ingredients', []):
                unique_ingredients.add(ing.lower())

        # Load existing badges
        user_badges_ref = db.collection('user_badges').where('user_id', '==', user_id).stream()
        unlocked_badges = {}
        for b in user_badges_ref:
            data = b.to_dict()
            unlocked_badges[data['badge_id']] = data.get('unlocked_at')

        newly_unlocked = {}
        def unlock(badge_id):
            if badge_id not in unlocked_badges and badge_id not in newly_unlocked:
                newly_unlocked[badge_id] = now.isoformat()

        # Evaluate conditions
        if total_scans > 0:
            unlock("first_scan")
        if last_7_scans and all(s.get('risk_level') == 'safe' for s in last_7_scans):
            unlock("health_guardian")
        if total_scans >= 20 and safety_rate >= 80:
            unlock("consistent_chooser")
        if curr_total >= 30:
            unlock("active_scanner")
        if curr_total > 0 and prev_total > 0 and improvement >= 20:
            unlock("quick_learner")
        if len(categories) >= 10:
            unlock("label_expert")
        if current_streak >= 7:
            unlock("streak_master")
        if allergens_avoided >= 20:
            unlock("allergen_aware")
        if total_scans >= 100:
            unlock("super_scanner")
        
        weeks_with_scans = set()
        for s in last_30_scans:
            days_ago = (now.date() - s['parsed_time'].date()).days
            if 0 <= days_ago < 28:
                weeks_with_scans.add(days_ago // 7)
        if len(weeks_with_scans) == 4:
            unlock("weekly_warrior")
            
        prev_unsafe = sum(1 for s in prev_30_scans if s.get('risk_level') == 'unsafe')
        curr_unsafe = sum(1 for s in last_30_scans if s.get('risk_level') == 'unsafe')
        if prev_unsafe > 0 and curr_unsafe <= prev_unsafe * 0.5:
            unlock("improvement_badge")
            
        if len(unique_ingredients) >= 50:
            unlock("ingredient_guru")
        if len(categories) >= 5:
            unlock("diverse_scanner")
        if scans and (scans[-1]['parsed_time'] - scans[0]['parsed_time']).days >= 30:
            unlock("veteran")
        if len(unlocked_badges) + len(newly_unlocked) >= 10:
            unlock("completionist")

        # Save new badges
        if newly_unlocked:
            batch = db.batch()
            for badge_id, ts in newly_unlocked.items():
                doc_ref = db.collection('user_badges').document(f"{user_id}_{badge_id}")
                batch.set(doc_ref, {
                    'user_id': user_id,
                    'badge_id': badge_id,
                    'unlocked_at': ts
                })
                unlocked_badges[badge_id] = ts
            batch.commit()

        # Combine all badges
        ALL_BADGES = [
            {"id": "first_scan", "name": "First Scan", "icon": "🏁", "description": "Complete first product scan"},
            {"id": "health_guardian", "name": "Health Guardian", "icon": "🛡️", "description": "100% safe products for 7+ days"},
            {"id": "consistent_chooser", "name": "Consistent Chooser", "icon": "📊", "description": "80%+ safe choices over 20+ scans"},
            {"id": "active_scanner", "name": "Active Scanner", "icon": "📈", "description": "30+ scans in a single month"},
            {"id": "quick_learner", "name": "Quick Learner", "icon": "⚡", "description": "20%+ improvement in safe choices"},
            {"id": "label_expert", "name": "Label Expert", "icon": "🏷️", "description": "Scan 10+ different product categories"},
            {"id": "streak_master", "name": "Streak Master", "icon": "🔥", "description": "Scan daily for 7+ consecutive days"},
            {"id": "allergen_aware", "name": "Allergen Aware", "icon": "🎯", "description": "Correctly identify allergens 20+ times"},
            {"id": "super_scanner", "name": "Super Scanner", "icon": "🌟", "description": "Reach 100 total scans"},
            {"id": "weekly_warrior", "name": "Weekly Warrior", "icon": "📅", "description": "Scan at least once every week for 4 weeks"},
            {"id": "improvement_badge", "name": "Improvement Badge", "icon": "💪", "description": "50% reduction in unsafe products"},
            {"id": "ingredient_guru", "name": "Ingredient Guru", "icon": "🧠", "description": "Successfully identify 50+ individual ingredients"},
            {"id": "diverse_scanner", "name": "Diverse Scanner", "icon": "🌈", "description": "Scan products from 5+ different categories"},
            {"id": "completionist", "name": "Completionist", "icon": "🏆", "description": "Collect 10+ badges"},
            {"id": "veteran", "name": "Veteran", "icon": "🎖️", "description": "Use the app for 30+ days"},
        ]

        result_badges = []
        new_badge_count = 0
        first_locked = None
        for b in ALL_BADGES:
            is_unlocked = b['id'] in unlocked_badges
            unlocked_at = unlocked_badges.get(b['id'])
            is_new = False
            if unlocked_at:
                try:
                    ua_dt = datetime.fromisoformat(unlocked_at.replace('Z', '+00:00'))
                    if (now - ua_dt).days < 7:
                        is_new = True
                        new_badge_count += 1
                except:
                    pass
            
            result_badges.append({
                "id": b['id'],
                "name": b['name'],
                "icon": b['icon'],
                "description": b['description'],
                "is_unlocked": is_unlocked,
                "unlocked_at": unlocked_at,
                "is_new": is_new
            })
            if not is_unlocked and not first_locked:
                first_locked = b

        weekly_title = "Welcome"
        weekly_msg = "Scan products to get insights!"
        if week_stats['total'] > 0:
            if week_stats['safe_pct'] == 100:
                weekly_title = "Perfect Record"
                weekly_msg = "All products scanned this week are safe!"
            elif week_stats['safe_pct'] >= 80:
                weekly_title = "Great Choices"
                weekly_msg = f"{int(week_stats['safe_pct'])}% of your scans this week are safe."
            else:
                weekly_title = "Needs Attention"
                weekly_msg = "Many products this week contain allergens."

        monthly_title = "Getting Started"
        monthly_msg = "Scan more products to see your monthly trends."
        if month_stats['total'] > 0:
            if scans_increase >= 20:
                monthly_title = "Active Scanner"
                monthly_msg = f"You scanned {curr_total} products this month."
            elif improvement >= 15:
                monthly_title = "Improving"
                monthly_msg = f"Your product safety awareness improved {int(improvement)}%!"
            else:
                monthly_title = "Consistent Scanner"
                monthly_msg = f"You've scanned {curr_total} items this month."

        next_target = ((total_scans // 10) + 1) * 10
        if next_target - total_scans > 5 and total_scans % 10 >= 5:
            next_target = ((total_scans // 5) + 1) * 5
            
        recommendation_tip = f"Tip: {first_locked['description']} to unlock the '{first_locked['name']}' badge!" if first_locked else "You've unlocked all badges! Amazing job!"

        return jsonify({
            "weekly": {
                "total_scans": week_stats['total'],
                "safe_count": week_stats['safe'],
                "unsafe_count": week_stats['unsafe'],
                "caution_count": week_stats['caution'],
                "safe_percentage": week_stats['safe_pct'],
                "top_allergen": week_stats['top_allergen'],
                "avg_confidence": week_stats['avg_conf'],
                "insight_title": weekly_title,
                "insight_message": weekly_msg,
                "scans_by_day": scans_by_day
            },
            "monthly": {
                "total_scans": curr_total,
                "safe_count": month_stats['safe'],
                "unsafe_count": month_stats['unsafe'],
                "caution_count": month_stats['caution'],
                "safe_percentage": month_stats['safe_pct'],
                "improvement": improvement,
                "scans_increase": scans_increase,
                "trend": trend,
                "insight_title": monthly_title,
                "insight_message": monthly_msg,
                "scans_by_week": scans_by_week,
                "top_categories": month_stats['top_categories']
            },
            "total_scans_all_time": total_scans,
            "total_safe_scans": total_safe,
            "safety_rate": safety_rate,
            "current_streak": current_streak,
            "allergens_avoided": allergens_avoided,
            "badges": result_badges,
            "new_badge_count": new_badge_count,
            "recommendation_tip": recommendation_tip,
            "next_milestone": {
                "target": next_target,
                "current": total_scans,
                "message": f"{next_target - total_scans} more scans to reach {next_target} total scans!"
            }
        }), 200
    except Exception as e:
        print(f"Error in analytics summary: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


def evaluate_user_badges(user_id):
    try:
        now = datetime.now()
        thirty_days_ago = now - timedelta(days=30)
        sixty_days_ago = now - timedelta(days=60)
        seven_days_ago = now - timedelta(days=7)
        
        # Load scans
        scans_ref = db.collection(SCAN_HISTORY_COLLECTION).where('user_id', '==', user_id).stream()
        scans = []
        for scan in scans_ref:
            data = scan.to_dict()
            ts = data.get('scan_date') or data.get('scanned_at') or data.get('timestamp')
            scan_time = now
            if ts:
                try:
                    if hasattr(ts, 'timestamp'):
                        scan_time = datetime.fromtimestamp(ts.timestamp())
                    elif isinstance(ts, str):
                        scan_time = datetime.fromisoformat(ts.replace('Z', '+00:00'))
                except:
                    pass
            data['parsed_time'] = scan_time
            scans.append(data)
            
        scans.sort(key=lambda x: x['parsed_time'])
        total_scans = len(scans)
        if total_scans == 0:
            return []
            
        total_safe = sum(1 for s in scans if s.get('risk_level') == 'safe')
        safety_rate = (total_safe / total_scans * 100) if total_scans > 0 else 0
        allergens_avoided = sum(1 for s in scans if s.get('risk_level') == 'unsafe')
        
        last_7_scans = [s for s in scans if s['parsed_time'] >= seven_days_ago]
        last_30_scans = [s for s in scans if s['parsed_time'] >= thirty_days_ago]
        prev_30_scans = [s for s in scans if sixty_days_ago <= s['parsed_time'] < thirty_days_ago]
        
        def process_scans(scan_list, start_time):
            filtered = [s for s in scan_list if s['parsed_time'] >= start_time]
            total = len(filtered)
            safe = sum(1 for s in filtered if s.get('risk_level') == 'safe')
            safe_pct = (safe / total * 100) if total > 0 else 0
            return {'total': total, 'safe_pct': safe_pct, 'filtered_scans': filtered}
            
        week_stats = process_scans(scans, seven_days_ago)
        month_stats = process_scans(scans, thirty_days_ago)
        prev_month_stats = process_scans([s for s in scans if s['parsed_time'] < thirty_days_ago], sixty_days_ago)
        
        prev_safe_pct = prev_month_stats['safe_pct']
        curr_safe_pct = month_stats['safe_pct']
        improvement = curr_safe_pct - prev_safe_pct
        prev_total = prev_month_stats['total']
        curr_total = month_stats['total']
        
        current_streak = 0
        if scans:
            unique_days = sorted(list(set(s['parsed_time'].date() for s in scans)), reverse=True)
            if unique_days and (now.date() - unique_days[0]).days <= 1:
                current_streak = 1
                for i in range(1, len(unique_days)):
                    if (unique_days[i-1] - unique_days[i]).days == 1:
                        current_streak += 1
                    else:
                        break
                        
        categories = set()
        unique_ingredients = set()
        for s in scans:
            name_words = s.get('product_name', '').split()
            if name_words and name_words[0] != 'Unknown':
                categories.add(name_words[-1])
            for ing in s.get('ingredients', []):
                unique_ingredients.add(ing.lower())
                
        # Load existing badges
        user_badges_ref = db.collection('user_badges').where('user_id', '==', user_id).stream()
        unlocked_badges = {}
        for b in user_badges_ref:
            data = b.to_dict()
            unlocked_badges[data['badge_id']] = data.get('unlocked_at')
            
        newly_unlocked = {}
        def unlock(badge_id):
            if badge_id not in unlocked_badges and badge_id not in newly_unlocked:
                newly_unlocked[badge_id] = now.isoformat()
                
        # Evaluate conditions
        if total_scans > 0:
            unlock("first_scan")
        if last_7_scans and all(s.get('risk_level') == 'safe' for s in last_7_scans):
            unlock("health_guardian")
        if total_scans >= 20 and safety_rate >= 80:
            unlock("consistent_chooser")
        if curr_total >= 30:
            unlock("active_scanner")
        if curr_total > 0 and prev_total > 0 and improvement >= 20:
            unlock("quick_learner")
        if len(categories) >= 10:
            unlock("label_expert")
        if current_streak >= 7:
            unlock("streak_master")
        if allergens_avoided >= 20:
            unlock("allergen_aware")
        if total_scans >= 100:
            unlock("super_scanner")
            
        weeks_with_scans = set()
        for s in last_30_scans:
            days_ago = (now.date() - s['parsed_time'].date()).days
            if 0 <= days_ago < 28:
                weeks_with_scans.add(days_ago // 7)
        if len(weeks_with_scans) == 4:
            unlock("weekly_warrior")
            
        prev_unsafe = sum(1 for s in prev_30_scans if s.get('risk_level') == 'unsafe')
        curr_unsafe = sum(1 for s in last_30_scans if s.get('risk_level') == 'unsafe')
        if prev_unsafe > 0 and curr_unsafe <= prev_unsafe * 0.5:
            unlock("improvement_badge")
            
        if len(unique_ingredients) >= 50:
            unlock("ingredient_guru")
        if len(categories) >= 5:
            unlock("diverse_scanner")
        if scans and (scans[-1]['parsed_time'] - scans[0]['parsed_time']).days >= 30:
            unlock("veteran")
        if len(unlocked_badges) + len(newly_unlocked) >= 10:
            unlock("completionist")
            
        ALL_BADGES = {
            "first_scan": {"name": "First Scan", "icon": "🏁", "description": "Complete first product scan"},
            "health_guardian": {"name": "Health Guardian", "icon": "🛡️", "description": "100% safe products for 7+ days"},
            "consistent_chooser": {"name": "Consistent Chooser", "icon": "📊", "description": "80%+ safe choices over 20+ scans"},
            "active_scanner": {"name": "Active Scanner", "icon": "📈", "description": "30+ scans in a single month"},
            "quick_learner": {"name": "Quick Learner", "icon": "⚡", "description": "20%+ improvement in safe choices"},
            "label_expert": {"name": "Label Expert", "icon": "🏷️", "description": "Scan 10+ different product categories"},
            "streak_master": {"name": "Streak Master", "icon": "🔥", "description": "Scan daily for 7+ consecutive days"},
            "allergen_aware": {"name": "Allergen Aware", "icon": "🎯", "description": "Correctly identify allergens 20+ times"},
            "super_scanner": {"name": "Super Scanner", "icon": "🌟", "description": "Reach 100 total scans"},
            "weekly_warrior": {"name": "Weekly Warrior", "icon": "📅", "description": "Scan at least once every week for 4 weeks"},
            "improvement_badge": {"name": "Improvement Badge", "icon": "💪", "description": "50% reduction in unsafe products"},
            "ingredient_guru": {"name": "Ingredient Guru", "icon": "🧠", "description": "Successfully identify 50+ individual ingredients"},
            "diverse_scanner": {"name": "Diverse Scanner", "icon": "🌈", "description": "Scan products from 5+ different categories"},
            "completionist": {"name": "Completionist", "icon": "🏆", "description": "Collect 10+ badges"},
            "veteran": {"name": "Veteran", "icon": "🎖️", "description": "Use the app for 30+ days"}
        }
        
        new_badges_list = []
        if newly_unlocked:
            batch = db.batch()
            for badge_id, ts in newly_unlocked.items():
                doc_ref = db.collection('user_badges').document(f"{user_id}_{badge_id}")
                batch.set(doc_ref, {
                    'user_id': user_id,
                    'badge_id': badge_id,
                    'unlocked_at': ts
                })
                badge_info = ALL_BADGES.get(badge_id, {"name": badge_id, "icon": "🏅", "description": ""})
                new_badges_list.append({
                    "id": badge_id,
                    "name": badge_info["name"],
                    "icon": badge_info["icon"],
                    "description": badge_info["description"]
                })
            batch.commit()
            
        return new_badges_list
    except Exception as e:
        print(f"Error evaluating badges: {e}")
        return []


# ============= SCAN ENDPOINTS =============

@app.route('/users/<user_id>/scans', methods=['POST'])
def add_scan(user_id):
    try:
        data = request.get_json()
        user_ref = db.collection('users').document(user_id)
        if not user_ref.get().exists:
            return jsonify({'message': 'User not found'}), 404
        
        confidence = data.get('confidence', 0.0)
        if confidence == 0.0:
            confidence = data.get('ml_confidence', 0.0)
        if confidence == 0.0 and (data.get('ingredients') or data.get('raw_text')):
            confidence = 0.85
        
        now = firestore.SERVER_TIMESTAMP
        safety_classification = data.get('safety_classification', data.get('risk_level', 'unknown'))
        
        ingredients_list = data.get('ingredients', [])
        allergens_list = data.get('allergens_detected', [])
        
        scan_ref = db.collection(SCAN_HISTORY_COLLECTION).add({
            'user_id': user_id,
            'product_name': data.get('product_name', 'Unknown Product'),
            'ingredients': ingredients_list,
            'ingredient_count': len(ingredients_list),
            'ingredient_details': data.get('ingredient_details', []),
            'risk_level': data.get('risk_level', 'unknown'),
            'safety_classification': safety_classification,
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
            'input_image_url': data.get('input_image_url', data.get('image_url', '')),
            'processing_time_ms': data.get('processing_time_ms', 0),
            'scan_date': now,
            'scanned_at': now,
            'timestamp': now
        })
        scan_id = scan_ref[1].id

        for ingredient in data.get('ingredient_details', []):
            related_allergens = [
                match.get('name', '')
                for match in ingredient.get('matches', [])
                if match.get('type') == 'allergen' and match.get('name')
            ]
            ingredient_ref = db.collection(PRODUCT_INGREDIENTS_COLLECTION).add({
                'scan_id': scan_id,
                'user_id': user_id,
                'ingredient_name': ingredient.get('ingredient', ''),
                'normalized_name': ingredient.get('normalized', ''),
                'related_allergens': related_allergens,
                'status': ingredient.get('status', 'safe'),
                'confidence': ingredient.get('confidence', 0.0),
                'created_at': now,
            })

            for match in ingredient.get('matches', []):
                db.collection(INGREDIENT_MATCHES_COLLECTION).add({
                    'scan_id': scan_id,
                    'ingredient_id': ingredient_ref[1].id,
                    'user_id': user_id,
                    'match_type': match.get('type', ''),
                    'restriction_id': match.get('id', ''),
                    'restriction_name': match.get('name', ''),
                    'allergen_keyword': match.get('keyword', ''),
                    'keyword': match.get('keyword', ''),
                    'severity': match.get('severity', ''),
                    'match_timestamp': now,
                })
        
        # Evaluate badges
        newly_unlocked_badges = evaluate_user_badges(user_id)
        
        return jsonify({
            'scan_id': scan_id, 
            'message': 'Scan recorded successfully',
            'newly_unlocked_badges': newly_unlocked_badges
        }), 201
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/users/<user_id>/scans', methods=['GET'])
def get_user_scans(user_id):
    """Get user's scan history with proper error handling"""
    try:
        user_ref = db.collection('users').document(user_id).get()
        if not user_ref.exists:
            return jsonify({'error': 'User not found'}), 404
        
        scans = []
        seen_ids = set()
        
        for collection_name in (SCAN_HISTORY_COLLECTION, LEGACY_SCANS_COLLECTION):
            try:
                scans_ref = db.collection(collection_name).where('user_id', '==', user_id).stream()
                for scan in scans_ref:
                    if scan.id in seen_ids:
                        continue
                    scan_data = scan.to_dict()
                    scan_data['id'] = scan.id
                    scan_data['source_collection'] = collection_name
                    scans.append(scan_data)
                    seen_ids.add(scan.id)
            except Exception as e:
                print(f"Error querying '{collection_name}': {e}")
        
        scans.sort(key=lambda x: str(scan_timestamp(x)), reverse=True)
        
        for scan in scans:
            for timestamp_field in ('scan_date', 'scanned_at', 'timestamp'):
                if timestamp_field in scan and scan[timestamp_field]:
                    if hasattr(scan[timestamp_field], 'isoformat'):
                        scan[timestamp_field] = scan[timestamp_field].isoformat()
                    else:
                        scan[timestamp_field] = str(scan[timestamp_field])
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
        print(f"Error in get_user_scans: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@app.route('/users/<user_id>/scans/<scan_id>', methods=['DELETE'])
def delete_scan(user_id, scan_id):
    """Delete a scan from history"""
    try:
        for collection_name in (SCAN_HISTORY_COLLECTION, LEGACY_SCANS_COLLECTION):
            scan_ref = db.collection(collection_name).document(scan_id).get()
            if scan_ref.exists:
                db.collection(collection_name).document(scan_id).delete()
        return jsonify({'success': True, 'message': 'Scan deleted successfully'}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ============= SCAN FOR USER ENDPOINT =============
@app.route('/scan/<user_id>', methods=['POST'])
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
        return jsonify({'error': str(e)}), 500


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
        return jsonify({'error': str(e)}), 500


# ============= ANALYZE WITH PROFILE ENDPOINT - FULLY FIXED =============

@app.route('/analyze-with-profile', methods=['POST'])
def analyze_with_profile():
    """Analyze ingredients text against user's profile.

    Detection pipeline (RF-primary 70/30):
      1. Random Forest (70%) — primary verdict (has_allergens probability)
      2. Rule-based / risk_analyzer (30%) — allergen labels + dietary detail
      3. build_personalized_analysis_v2 — per-ingredient detail labels for UI only
    """
    try:
        data = request.get_json()

        # Handle different possible input formats
        ingredients_input = data.get('ingredients_text') or data.get('ingredients')
        user_id = data.get('user_id')

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
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


# ============= TEST-ONLY INLINE ANALYSIS ENDPOINT =============

@app.route('/test/analyze', methods=['POST'])
def test_analyze_inline():
    """
    Accuracy-testing endpoint: accepts allergies/dietary inline, no Firestore lookup.
    NOT intended for production use — only for the test suite.
    """
    try:
        data = request.get_json()
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
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


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
        data = request.get_json()
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
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


# ============= DIETARY OPTIONS ENDPOINTS =============

@app.route('/dietary-options', methods=['GET'])
def get_dietary_options():
    try:
        options = get_options_by_category()
        return jsonify({'success': True, 'options': options}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/dietary-options/allergens', methods=['GET'])
def get_allergen_options():
    try:
        from dietary_options import ALLERGEN_OPTIONS
        return jsonify({'success': True, 'allergens': ALLERGEN_OPTIONS}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/dietary-options/dietary', methods=['GET'])
def get_dietary_only_options():
    try:
        from dietary_options import DIETARY_OPTIONS
        return jsonify({'success': True, 'dietary': DIETARY_OPTIONS}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ============= USER PROFILE CRUD ENDPOINTS =============

@app.route('/users/<user_id>/profile', methods=['GET'])
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
        return jsonify({'error': str(e)}), 500


@app.route('/users/<user_id>/profile', methods=['PUT'])
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
        return jsonify({'error': str(e)}), 500


@app.route('/users/<user_id>/profile/restrictions', methods=['POST'])
def add_restriction(user_id):
    try:
        data = request.get_json()
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
        return jsonify({'error': str(e)}), 500


@app.route('/users/<user_id>/profile/restrictions/<restriction_id>', methods=['DELETE'])
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
        return jsonify({'error': str(e)}), 500


@app.route('/users/<user_id>/profile/check', methods=['POST'])
def check_ingredients_against_profile(user_id):
    try:
        data = request.get_json()
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
        return jsonify({'error': str(e)}), 500


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