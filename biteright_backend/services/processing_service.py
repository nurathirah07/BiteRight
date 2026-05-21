from services.ocr_service import extract_ingredients
from services.nlp_service import detector
from services.risk_analyzer import build_personalized_analysis, parse_ingredients_input
from firebase_admin import firestore
import time
import re
import joblib
import os

class IngredientProcessor:
    def __init__(self, db):
        self.db = db
        self.detector = detector
        self.ml_model = None
        self.vectorizer = None
        self.model_loaded = False
        
    def initialize(self):
        """Load allergen data from Firestore and load ML model"""
        result = self.detector.load_allergens_from_firestore(self.db)
        self._load_ml_model()
        return result
    
    def _load_ml_model(self):
        """Load the trained Random Forest model"""
        try:
            if os.path.exists('models/random_forest.pkl'):
                self.ml_model = joblib.load('models/random_forest.pkl')
                self.vectorizer = joblib.load('models/vectorizer.pkl')
                self.model_loaded = True
                print("Random Forest model loaded successfully")
            else:
                print("No pre-trained model found. Using rule-based detection only.")
        except Exception as e:
            print(f"Error loading ML model: {e}")
            self.model_loaded = False
    
    def process_scan(self, image_bytes, user_id):
        """Complete pipeline: OCR -> NLP -> AI Classification with user profile"""
        start_time = time.time()
        
        # Step 1: OCR Extraction
        ocr_result = extract_ingredients(image_bytes)
        if not ocr_result['success']:
            return {
                'success': False,
                'error': ocr_result['error'],
                'step': 'ocr'
            }
        
        # Step 2: Get user profile from Firestore
        user_ref = self.db.collection('users').document(user_id).get()
        if not user_ref.exists:
            return {
                'success': False,
                'error': 'User not found',
                'step': 'user_profile'
            }
        
        user_data = user_ref.to_dict()
        
        # Get user's allergies and dietary restrictions separately
        user_allergies = user_data.get('allergies', [])
        user_dietary = user_data.get('dietary_restrictions', [])
        
        # Convert to list of strings
        user_allergy_strings = []
        for allergy in user_allergies:
            if isinstance(allergy, dict):
                user_allergy_strings.append(allergy.get('id', ''))
            else:
                user_allergy_strings.append(str(allergy))
        
        # Step 3: Analyze the OCR result with the same profile-aware rules used
        # by the manual edit endpoint.
        ingredients_text = ocr_result.get('cleaned_text', '')
        raw_text = ocr_result.get('raw_text', '')
        ingredient_tokens = self.detector.preprocess_ingredient_text(ingredients_text)
        raw_ingredients = ocr_result.get('ingredients_list', [])
        ingredients = parse_ingredients_input(raw_text or ingredients_text or raw_ingredients)
        analysis = build_personalized_analysis(
            ingredients,
            user_allergies,
            user_dietary,
            raw_text=raw_text,
        )
        
        # ML confidence boost (if available)
        ml_confidence = 0
        if self.model_loaded and ingredient_tokens:
            try:
                text_to_predict = ' '.join(ingredient_tokens)
                text_vec = self.vectorizer.transform([text_to_predict])
                probabilities = self.ml_model.predict_proba(text_vec)[0]
                ml_confidence = max(probabilities)
            except Exception as e:
                print(f"ML prediction error: {e}")

        if ml_confidence:
            analysis['ml_confidence'] = round(float(ml_confidence), 2)
            analysis['confidence'] = max(analysis.get('confidence', 0.0), round(float(ml_confidence), 2))
        
        processing_time = time.time() - start_time
        
        return {
            'success': True,
            'user_id': user_id,
            'ingredients': ingredients or raw_ingredients,
            'analysis': {
                **analysis,
                'detection_method': 'Profile Rules + Synonyms + Trace Detection',
                'user_profile': {
                    'allergies': user_allergy_strings,
                    'dietary_restrictions': user_dietary
                }
            },
            'raw_text': raw_text,
            'processing_time': f"{processing_time:.2f}s"
        }
    
    def _check_allergens(self, all_text, user_allergies):
        """Check for allergens that match user's allergy profile"""
        alerts = []
        risk_score = 0
        detected = []
        
        # Allergen database with severity scores
        allergen_db = {
            'peanut': {'name': 'Peanuts', 'severity_score': 100},
            'peanuts': {'name': 'Peanuts', 'severity_score': 100},
            'milk': {'name': 'Milk/Dairy', 'severity_score': 60},
            'dairy': {'name': 'Milk/Dairy', 'severity_score': 60},
            'whey': {'name': 'Milk/Dairy', 'severity_score': 60},
            'casein': {'name': 'Milk/Dairy', 'severity_score': 60},
            'lactose': {'name': 'Milk/Dairy', 'severity_score': 60},
            'egg': {'name': 'Eggs', 'severity_score': 55},
            'eggs': {'name': 'Eggs', 'severity_score': 55},
            'albumin': {'name': 'Eggs', 'severity_score': 55},
            'soy': {'name': 'Soy', 'severity_score': 45},
            'soya': {'name': 'Soy', 'severity_score': 45},
            'wheat': {'name': 'Wheat', 'severity_score': 50},
            'gluten': {'name': 'Gluten', 'severity_score': 50},
            'fish': {'name': 'Fish', 'severity_score': 90},
            'shellfish': {'name': 'Shellfish', 'severity_score': 95},
            'shrimp': {'name': 'Shellfish', 'severity_score': 95},
            'crab': {'name': 'Shellfish', 'severity_score': 95},
            'lobster': {'name': 'Shellfish', 'severity_score': 95}
        }
        
        # Check only if user has the specific allergy
        for user_allergy in user_allergies:
            user_allergy_lower = user_allergy.lower()
            
            # Check if this allergen is in the ingredient text
            for allergen_key, allergen_info in allergen_db.items():
                if allergen_key == user_allergy_lower or allergen_key in user_allergy_lower:
                    if allergen_key in all_text or user_allergy_lower in all_text:
                        alert = f"⚠️ Contains {allergen_info['name']} - matches your allergy profile!"
                        alerts.append(alert)
                        risk_score += allergen_info['severity_score']
                        detected.append({
                            'allergen': user_allergy,
                            'matched_ingredient': allergen_key,
                            'severity_score': allergen_info['severity_score']
                        })
                        break
        
        # Cap risk score at 100
        risk_score = min(risk_score, 100)
        
        return {
            'alerts': alerts,
            'risk_score': risk_score,
            'detected': detected
        }
    
    def _check_dietary_restrictions(self, all_text, user_dietary):
        """Check for violations of dietary restrictions"""
        violations = []
        risk_score = 0
        
        # Dietary restriction rules
        dietary_rules = {
            'halal': {
                'forbidden': ['pork', 'ham', 'bacon', 'alcohol', 'wine', 'beer', 'liquor', 'gelatin', 'non-halal'],
                'message': 'Contains non-Halal ingredients'
            },
            'vegetarian': {
                'forbidden': ['beef', 'chicken', 'pork', 'fish', 'meat', 'gelatin', 'rennet'],
                'message': 'Contains meat or animal-derived ingredients'
            },
            'vegan': {
                'forbidden': ['milk', 'dairy', 'whey', 'casein', 'lactose', 'egg', 'honey', 'gelatin'],
                'message': 'Contains animal products (dairy, eggs, honey)'
            },
            'keto': {
                'forbidden': ['sugar', 'wheat', 'rice', 'corn', 'potato', 'starch', 'syrup', 'honey'],
                'message': 'Contains high-carb ingredients'
            },
            'diabetic': {
                'forbidden': ['sugar', 'syrup', 'honey', 'dextrose', 'maltose', 'fructose', 'corn syrup'],
                'message': 'Contains added sugars'
            },
            'low_sodium': {
                'forbidden': ['salt', 'sodium', 'monosodium glutamate', 'msg'],
                'message': 'Contains high sodium ingredients'
            }
        }
        
        for diet in user_dietary:
            diet_lower = diet.lower()
            if diet_lower in dietary_rules:
                rules = dietary_rules[diet_lower]
                for forbidden in rules['forbidden']:
                    if forbidden in all_text:
                        violations.append(f"🚫 {rules['message']} (violates {diet} diet)")
                        risk_score += 40  # Dietary violations are serious
                        break
        
        # Cap risk score at 100
        risk_score = min(risk_score, 100)
        
        return {
            'violations': violations,
            'risk_score': risk_score
        }
    
    def save_scan_result(self, user_id, result):
        """Save scan result to user's history"""
        try:
            now = firestore.SERVER_TIMESTAMP
            risk_level = result['analysis']['risk_level']
            scan_data = {
                'user_id': user_id,
                'ingredients': result.get('ingredients', []),
                'risk_level': risk_level,
                'safety_classification': risk_level,
                'risk_score': result['analysis'].get('risk_score', 0),
                'confidence': result['analysis'].get('confidence', 0.0),
                'alerts': result['analysis']['alerts'],
                'allergen_alerts': result['analysis'].get('allergen_alerts', []),
                'dietary_alerts': result['analysis'].get('dietary_alerts', []),
                'input_image_url': result.get('input_image_url', ''),
                'scan_date': now,
                'scanned_at': now,
                'timestamp': now
            }
            
            scan_ref = self.db.collection('scan_history').add(scan_data)
            print(f"Scan saved with ID: {scan_ref[1].id}")
            return scan_ref[1].id
        except Exception as e:
            print(f"Error saving scan: {e}")
            return None
