# biteright_backend/app.py
import os
from flask import Flask, jsonify, request
from flask_cors import CORS
import firebase_admin
from firebase_admin import credentials, firestore, auth
import re
import hashlib
import secrets

# Import your services
from services.ocr_service import extract_ingredients
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
        {'id': 'tree_nuts', 'name': 'Tree Nuts', 'severity': 'high', 'keywords': ['almond', 'walnut', 'cashew', 'pecan', 'pistachio', 'hazelnut', 'macadamia', 'tree nut', 'tree nuts']},
        {'id': 'milk', 'name': 'Milk/Dairy', 'severity': 'medium', 'keywords': ['milk', 'dairy', 'whey', 'casein', 'lactose', 'butter', 'cream', 'cheese', 'yogurt']},
        {'id': 'eggs', 'name': 'Eggs', 'severity': 'medium', 'keywords': ['egg', 'eggs', 'albumin', 'ovalbumin']},
        {'id': 'soy', 'name': 'Soy', 'severity': 'medium', 'keywords': ['soy', 'soya', 'tofu', 'tempeh', 'edamame', 'soy lecithin']},
        {'id': 'wheat', 'name': 'Wheat', 'severity': 'medium', 'keywords': ['wheat', 'flour', 'semolina', 'spelt', 'durum']},
        {'id': 'gluten', 'name': 'Gluten', 'severity': 'medium', 'keywords': ['gluten', 'wheat', 'barley', 'rye', 'malt']},
        {'id': 'fish', 'name': 'Fish', 'severity': 'high', 'keywords': ['fish', 'salmon', 'tuna', 'cod', 'mackerel', 'anchovy']},
        {'id': 'shellfish', 'name': 'Shellfish', 'severity': 'high', 'keywords': ['shrimp', 'prawn', 'crab', 'lobster', 'crayfish', 'shellfish']},
        {'id': 'sesame', 'name': 'Sesame', 'severity': 'medium', 'keywords': ['sesame', 'tahini', 'sesamol', 'gingelly']},
    ]

def dietary_rules():
    return {
        'halal': {'name': 'Halal', 'severity': 'high', 'forbidden': ['pork', 'ham', 'bacon', 'lard', 'alcohol', 'wine', 'beer', 'gelatin']},
        'vegetarian': {'name': 'Vegetarian', 'severity': 'medium', 'forbidden': ['beef', 'chicken', 'pork', 'fish', 'meat', 'gelatin']},
        'vegan': {'name': 'Vegan', 'severity': 'medium', 'forbidden': ['milk', 'dairy', 'whey', 'casein', 'egg', 'honey', 'gelatin', 'butter', 'cheese']},
        'diabetic': {'name': 'Diabetic / Low Sugar', 'severity': 'high', 'forbidden': ['sugar', 'syrup', 'honey', 'dextrose', 'corn syrup', 'glucose', 'sucrose', 'fructose']},
        'low_sodium': {'name': 'Low Sodium', 'severity': 'low', 'forbidden': ['salt', 'sodium', 'monosodium glutamate', 'msg']},
        'keto': {'name': 'Keto', 'severity': 'medium', 'forbidden': ['sugar', 'wheat', 'rice', 'corn', 'potato', 'starch', 'syrup', 'honey']},
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

# ============= FIXED build_personalized_analysis FUNCTION WITH DYNAMIC CONFIDENCE =============
def build_personalized_analysis(ingredients, user_allergies, user_dietary):
    """
    Build personalized analysis with DYNAMIC confidence scores based on risk level
    """
    allergy_ids, allergy_severity = selected_allergy_ids(user_allergies)
    dietary_ids = {normalize_key(item) for item in user_dietary}
    details = []
    alerts = []
    allergen_alerts = []
    dietary_alerts = []
    detected_allergens = set()
    risk_score = 0
    
    # Track match confidence factors
    total_confidence_sum = 0
    ingredient_count = max(len(ingredients), 1)

    for ingredient in ingredients:
        ingredient_lower = ingredient.lower()
        status = 'safe'
        reasons = []
        matches = []
        
        # Base confidence starts at 0.5 (50%)
        ingredient_confidence = 0.5
        match_found = False
        is_high_severity_match = False

        # Check allergens first
        for rule in allergen_rules():
            rule_profile_keys = {rule['id'], normalize_key(rule['name'])}
            rule_profile_keys.update(normalize_key(keyword) for keyword in rule['keywords'])
            if allergy_ids.isdisjoint(rule_profile_keys):
                continue

            matched_keyword = next((keyword for keyword in rule['keywords'] if keyword in ingredient_lower), None)
            if matched_keyword:
                match_found = True
                severity = allergy_severity.get(rule['id'], rule['severity'])
                status = 'unsafe'
                
                if severity == 'high':
                    is_high_severity_match = True
                
                # Higher confidence for exact matches
                if matched_keyword == ingredient_lower:
                    ingredient_confidence = max(ingredient_confidence, 0.95)
                elif len(matched_keyword) > 3:
                    ingredient_confidence = max(ingredient_confidence, 0.90)
                else:
                    ingredient_confidence = max(ingredient_confidence, 0.85)
                
                detected_allergens.add(rule['name'])
                reason = f"{ingredient} matches your {rule['name']} allergy"
                reasons.append(reason)
                matches.append({
                    'type': 'allergen',
                    'id': rule['id'],
                    'name': rule['name'],
                    'keyword': matched_keyword,
                    'severity': severity,
                })
                allergen_alerts.append(reason)
                risk_score += 50 if severity == 'high' else 35

        # Check dietary restrictions
        for diet_id, rule in dietary_rules().items():
            if diet_id not in dietary_ids:
                continue

            matched_keyword = next((keyword for keyword in rule['forbidden'] if keyword in ingredient_lower), None)
            if matched_keyword:
                match_found = True
                
                # Diabetic with sugar = unsafe
                if diet_id == 'diabetic':
                    status = 'unsafe'
                    is_high_severity_match = True
                elif rule['severity'] == 'high':
                    status = 'unsafe'
                    is_high_severity_match = True
                elif status != 'unsafe':
                    status = 'caution'
                
                if matched_keyword == ingredient_lower:
                    ingredient_confidence = max(ingredient_confidence, 0.92)
                else:
                    ingredient_confidence = max(ingredient_confidence, 0.85)
                
                reason = f"{ingredient} may violate your {rule['name']} restriction"
                reasons.append(reason)
                matches.append({
                    'type': 'dietary',
                    'id': diet_id,
                    'name': rule['name'],
                    'keyword': matched_keyword,
                    'severity': rule['severity'],
                })
                dietary_alerts.append(reason)
                risk_score += 40 if rule['severity'] == 'high' or diet_id == 'diabetic' else 25
        
        # DYNAMIC CONFIDENCE ADJUSTMENT based on match quality
        if match_found:
            if is_high_severity_match:
                # High severity matches = HIGH confidence (95%)
                ingredient_confidence = max(ingredient_confidence, 0.95)
            else:
                ingredient_confidence = max(ingredient_confidence, 0.85)
        else:
            # No matches = lower confidence (65%)
            ingredient_confidence = 0.65
        
        total_confidence_sum += ingredient_confidence
        
        details.append({
            'ingredient': ingredient,
            'normalized': ingredient_lower,
            'status': status,
            'confidence': round(ingredient_confidence, 2),
            'reasons': reasons,
            'matches': matches,
        })

    alerts = list(dict.fromkeys(allergen_alerts + dietary_alerts))
    risk_score = min(risk_score, 100)
    
    # Determine risk level
    has_unsafe = False
    has_caution = False
    
    for item in details:
        if item['status'] == 'unsafe':
            has_unsafe = True
            break
        elif item['status'] == 'caution':
            has_caution = True
    
    # Also check dietary alerts directly
    if dietary_alerts:
        for alert in dietary_alerts:
            if 'diabetic' in alert.lower() or 'sugar' in alert.lower():
                has_unsafe = True
                break
            else:
                has_caution = True
    
    # Set final risk level
    if has_unsafe:
        risk_level = 'unsafe'
        # Lower risk score for unsafe
        if risk_score > 60:
            risk_score = 35
        # DYNAMIC CONFIDENCE: Unsafe products get LOWER confidence (more uncertainty = 70-75%)
        base_confidence = 0.72
    elif has_caution or dietary_alerts:
        risk_level = 'caution'
        if risk_score > 70:
            risk_score = 55
        # DYNAMIC CONFIDENCE: Caution products get MEDIUM confidence (80%)
        base_confidence = 0.80
    else:
        risk_level = 'safe'
        # DYNAMIC CONFIDENCE: Safe products get HIGHER confidence (88-92%)
        base_confidence = 0.90
    
    # Calculate final confidence - blend ingredient confidence with risk-based confidence
    avg_ingredient_confidence = round(total_confidence_sum / ingredient_count, 2) if details else 0.85
    
    # DYNAMIC FINAL CONFIDENCE based on risk level and ingredient matches
    if risk_level == 'unsafe':
        # Unsafe: Weighted more toward ingredient matches (detection certainty)
        final_confidence = round((avg_ingredient_confidence * 0.7 + base_confidence * 0.3), 2)
    elif risk_level == 'caution':
        # Caution: Balanced confidence
        final_confidence = round((avg_ingredient_confidence * 0.5 + base_confidence * 0.5), 2)
    else:
        # Safe: Higher overall confidence
        final_confidence = round((avg_ingredient_confidence * 0.4 + base_confidence * 0.6), 2)
    
    # Ensure confidence is within reasonable range based on risk level
    if risk_level == 'unsafe':
        final_confidence = max(0.65, min(0.85, final_confidence))
    elif risk_level == 'caution':
        final_confidence = max(0.70, min(0.88, final_confidence))
    else:
        final_confidence = max(0.75, min(0.95, final_confidence))

    # Recommendations
    if risk_level == 'unsafe':
        recommendations = [
            'Do not consume this product unless the label is verified by a trusted source.',
            'Choose an alternative without the flagged allergen or dietary conflict.',
        ]
    elif risk_level == 'caution':
        recommendations = [
            'Review the flagged ingredients before consuming.',
            'Check the manufacturer allergen statement for cross-contact warnings.',
        ]
    else:
        recommendations = [
            'No profile conflicts were detected in the scanned ingredients.',
            'Keep your allergy and dietary profile updated for accurate alerts.',
        ]

    print(f"=== CONFIDENCE CALCULATION ===")
    print(f"Risk Level: {risk_level}")
    print(f"Avg Ingredient Confidence: {avg_ingredient_confidence}")
    print(f"Base Confidence: {base_confidence}")
    print(f"Final Confidence: {final_confidence}")
    print(f"Risk Score: {risk_score}")
    print(f"==============================")

    return {
        'risk_level': risk_level,
        'risk_score': risk_score,
        'confidence': final_confidence,
        'alerts': alerts,
        'allergen_alerts': list(dict.fromkeys(allergen_alerts)),
        'dietary_alerts': list(dict.fromkeys(dietary_alerts)),
        'allergens_detected': sorted(detected_allergens),
        'ingredient_details': details,
        'recommendations': recommendations,
    }

@app.before_request
def initialize_once():
    """Load allergen data from Firestore before first request"""
    global _initialized
    if not _initialized:
        print("Loading allergen database...")
        detector.load_allergens_from_firestore(db)
        processor.initialize()
        print("Allergen database loaded!")
        print("Random Forest model loaded successfully" if processor.model_loaded else "No ML model found, using rule-based only")
        _initialized = True

@app.route('/')
def home():
    return jsonify({
        "message": "BiteRight API is running with Firebase!",
        "endpoints": {
            "/": "This help message",
            "/test-firebase": "Test Firebase connection",
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
            confidence = 0.72
        
        now = firestore.SERVER_TIMESTAMP
        safety_classification = data.get('safety_classification', data.get('risk_level', 'unknown'))
        
        scan_ref = db.collection(SCAN_HISTORY_COLLECTION).add({
            'user_id': user_id,
            'product_name': data.get('product_name', 'Unknown Product'),
            'ingredients': data.get('ingredients', []),
            'ingredient_details': data.get('ingredient_details', []),
            'risk_level': data.get('risk_level', 'unknown'),
            'safety_classification': safety_classification,
            'risk_score': data.get('risk_score', 0),
            'alerts': data.get('alerts', []),
            'recommendations': data.get('recommendations', []),
            'confidence': confidence,
            'detection_method': data.get('detection_method', 'AI Analysis'),
            'allergens_detected': data.get('allergens_detected', []),
            'raw_text': data.get('raw_text', ''),
            'input_image_url': data.get('input_image_url', data.get('image_url', '')),
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
        
        return jsonify({'scan_id': scan_id, 'message': 'Scan recorded successfully'}), 201
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
            scan.setdefault('risk_level', 'unknown')
            scan.setdefault('safety_classification', scan.get('risk_level', 'unknown'))
            scan.setdefault('risk_score', 0)
            scan.setdefault('alerts', [])
            scan.setdefault('confidence', 0.0)
        
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
    try:
        if 'image' not in request.files:
            return jsonify({'error': 'No image uploaded'}), 400
        
        image_file = request.files['image']
        image_bytes = image_file.read()
        
        result = processor.process_scan(image_bytes, user_id)
        if not result['success']:
            return jsonify({'error': result['error']}), 500
        
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
        
        scan_data = {
            'user_id': user_id,
            'product_name': scan_result.get('product_name', 'Unknown Product'),
            'ingredients': scan_result.get('ingredients', []),
            'risk_level': risk_level,
            'safety_classification': risk_level,
            'risk_score': analysis.get('risk_score', 0),
            'alerts': analysis.get('alerts', []),
            'confidence': confidence,
            'input_image_url': scan_result.get('input_image_url', ''),
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
        
        ingredients_text = raw_text or ' '.join(raw_ingredients)
        parsed_ingredients = parse_ingredients_input_v2(ingredients_text)
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
            'ocr_confidence': ocr_result.get('ocr_confidence', 0.0),
            'ocr_strategy': ocr_result.get('strategy_used', ''),
            'processed_count': len(parsed_ingredients or cleaned_ingredients),
            'raw_count': len(raw_ingredients)
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ============= ANALYZE WITH PROFILE ENDPOINT =============

@app.route('/analyze-with-profile', methods=['POST'])
def analyze_with_profile():
    """Analyze ingredients text against user's profile"""
    try:
        data = request.get_json()
        ingredients_text = data.get('ingredients_text', '')
        user_id = data.get('user_id')
        
        if not ingredients_text:
            return jsonify({'error': 'No ingredients provided'}), 400
        
        if not user_id:
            return jsonify({'error': 'No user ID provided'}), 400
        
        user_ref = db.collection('users').document(user_id).get()
        if not user_ref.exists:
            return jsonify({'error': 'User not found'}), 404
        
        user_data = user_ref.to_dict()
        user_allergies = user_data.get('allergies', [])
        user_dietary = user_data.get('dietary_restrictions', [])

        analysis = processor.analyze_ingredients(
            ingredients_text,
            user_allergies=user_allergies,
            user_dietary=user_dietary,
            raw_text=ingredients_text,
        )
        ingredients = analysis.get('ingredients') or parse_ingredients_input_v2(ingredients_text)

        user_allergy_strings = []
        for allergy in user_allergies:
            if isinstance(allergy, dict):
                user_allergy_strings.append(allergy.get('id', ''))
            else:
                user_allergy_strings.append(str(allergy))

        print(f"=== FINAL ANALYSIS RESULT ===")
        print(f"Risk Level: {analysis['risk_level']}")
        print(f"Risk Score: {analysis['risk_score']}")
        print(f"Confidence: {analysis['confidence']}")
        print(f"Alerts: {analysis['alerts']}")
        print(f"=============================")

        return jsonify({
            'success': True,
            'ingredients': ingredients,
            'detection_method': analysis.get('detection_method', 'Random Forest Primary Classifier + Profile Rules'),
            **analysis,
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

# ============= BASIC ANALYZE ENDPOINT =============

@app.route('/analyze-ingredients', methods=['POST'])
def analyze_ingredients():
    """Basic analyze without user profile"""
    try:
        data = request.get_json()
        ingredients_input = data.get('ingredients_text') or data.get('ingredients')
        
        if not ingredients_input:
            return jsonify({'error': 'No ingredients provided'}), 400
        
        analysis = processor.analyze_ingredients(ingredients_input)
        
        return jsonify({
            'success': True,
            'detection_method': analysis.get('detection_method', 'Random Forest Primary Classifier + Common Allergen Rules'),
            **analysis,
            'message': 'Create a user profile for personalized allergen detection based on your specific allergies'
        }), 200
        
    except Exception as e:
        print(f"Error in analyze_ingredients: {e}")
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
        
        analysis = build_personalized_analysis(ingredients, user_allergies, user_dietary)
        
        return jsonify({
            'success': True,
            'risk_level': analysis['risk_level'],
            'risk_score': analysis['risk_score'],
            'alerts': analysis['alerts'],
            'allergen_alerts': analysis['allergen_alerts'],
            'dietary_alerts': analysis['dietary_alerts'],
            'allergens_detected': analysis['allergens_detected'],
            'confidence': analysis['confidence'],
            'ingredients_checked': ingredients
        }), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    print("=" * 50)
    print("BiteRight API Starting...")
    print("=" * 50)
    print("Root endpoint: http://127.0.0.1:5000/")
    print("Test Firebase: http://127.0.0.1:5000/test-firebase")
    print("Dietary options: http://127.0.0.1:5000/dietary-options")
    print("Extract ingredients: http://127.0.0.1:5000/extract-ingredients")
    print("Analyze ingredients: http://127.0.0.1:5000/analyze-ingredients")
    print("Analyze with profile: http://127.0.0.1:5000/analyze-with-profile")
    print("=" * 50)
    app.run(host='0.0.0.0', port=5000, debug=True)
