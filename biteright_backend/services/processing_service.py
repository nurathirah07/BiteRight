from services.ocr_service import extract_ingredients
from services.nlp_service import detector
from services.risk_analyzer import (
    build_general_analysis,
    build_personalized_analysis,
    parse_ingredients_input,
    normalize_text,
)
from firebase_admin import firestore
import time
import joblib
import os

class IngredientProcessor:
    ML_WEIGHT = 0.6
    RULE_WEIGHT = 0.4

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
        backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        model_path = os.path.join(backend_dir, 'models', 'random_forest.pkl')
        vectorizer_path = os.path.join(backend_dir, 'models', 'vectorizer.pkl')
        try:
            if os.path.exists(model_path) and os.path.exists(vectorizer_path):
                self.ml_model = joblib.load(model_path)
                self.vectorizer = joblib.load(vectorizer_path)
                self.model_loaded = True
                print("Random Forest model loaded successfully")
            else:
                print("WARNING: Random Forest model files missing. Using rule-based detection only.")
        except Exception as e:
            print(f"WARNING: Error loading Random Forest model: {e}. Using rule-based detection only.")
            self.ml_model = None
            self.vectorizer = None
            self.model_loaded = False

    def _profile_allergy_labels(self, user_allergies):
        labels = []
        for allergy in user_allergies or []:
            if isinstance(allergy, dict):
                labels.append(str(allergy.get('id') or allergy.get('label') or allergy.get('name') or ''))
            else:
                labels.append(str(allergy))
        return [label for label in labels if label]

    def _prediction_probability(self, probabilities):
        classes = list(getattr(self.ml_model, 'classes_', []))
        if 1 in classes:
            return float(probabilities[classes.index(1)])
        if True in classes:
            return float(probabilities[classes.index(True)])
        return float(max(probabilities))

    def _ml_prediction(self, ingredients_text):
        """Return Random Forest allergen probability. Falls back cleanly if unavailable."""
        if not self.model_loaded or self.ml_model is None or self.vectorizer is None:
            return {
                'available': False,
                'has_allergens': False,
                'allergen_probability': 0.0,
                'confidence': 0.0,
                'warning': 'Random Forest model unavailable; rule-based detection used only.'
            }

        try:
            text = normalize_text(ingredients_text)
            text_vec = self.vectorizer.transform([text])
            prediction = self.ml_model.predict(text_vec)[0]
            probabilities = self.ml_model.predict_proba(text_vec)[0]
            allergen_probability = self._prediction_probability(probabilities)
            return {
                'available': True,
                'has_allergens': bool(prediction),
                'allergen_probability': round(allergen_probability, 4),
                'confidence': round(float(max(probabilities)), 4),
            }
        except Exception as e:
            print(f"WARNING: Random Forest prediction failed: {e}. Using rule-based detection only.")
            return {
                'available': False,
                'has_allergens': False,
                'allergen_probability': 0.0,
                'confidence': 0.0,
                'warning': f'Random Forest prediction failed; rule-based detection used only: {e}'
            }

    def _risk_level_from_score(self, score):
        if score >= 40:
            return 'unsafe'
        if score >= 20:
            return 'caution'
        return 'safe'

    def _recommendations(self, risk_level, profile_aware):
        if risk_level == 'unsafe':
            return [
                'Do not consume this product unless the label is verified by a trusted source.',
                'Choose an alternative without the flagged allergen or dietary conflict.',
            ]
        if risk_level == 'caution':
            return [
                'Review the flagged ingredients and allergen statement before consuming.',
                'Confirm with the manufacturer if this product may affect your profile.',
            ] if profile_aware else [
                'Review the ingredient list and allergen statement before consuming.',
                'Create or update a profile for allergy-specific recommendations.',
            ]
        return [
            'No conflicts were detected for the current profile.' if profile_aware else 'No common allergen signal was detected.',
            'Keep the ingredient text and profile updated for the most accurate result.',
        ]

    def analyze_ingredients(self, ingredients_input, user_allergies=None, user_dietary=None, raw_text=None):
        """Analyze ingredients using Random Forest as the primary classifier plus rules."""
        user_allergies = user_allergies or []
        user_dietary = user_dietary or []
        profile_aware = bool(user_allergies or user_dietary)
        source_text = raw_text if raw_text is not None else ingredients_input
        ingredients = parse_ingredients_input(source_text)
        text_for_ml = ' '.join(ingredients) if ingredients else str(source_text or '')

        if profile_aware:
            rule_analysis = build_personalized_analysis(
                ingredients or source_text,
                user_allergies,
                user_dietary,
                raw_text=str(source_text or ''),
            )
        else:
            rule_analysis = build_general_analysis(ingredients or source_text)

        ml_result = self._ml_prediction(text_for_ml)
        ml_score = ml_result['allergen_probability'] * 100 if ml_result['available'] else 0.0

        rule_level = rule_analysis.get('risk_level', 'safe')
        rule_score = float(rule_analysis.get('hazard_score', 0))
        if not rule_score:
            rule_score = {'unsafe': 100.0, 'caution': 50.0, 'safe': 0.0}.get(rule_level, 0.0)

        if ml_result['available']:
            combined_score = (ml_score * self.ML_WEIGHT) + (rule_score * self.RULE_WEIGHT)
            ml_confidence = float(ml_result['confidence'])
        else:
            combined_score = rule_score
            ml_confidence = 0.0

        final_risk_level = self._risk_level_from_score(combined_score)
        rule_confidence = float(rule_analysis.get('confidence', 0.0))
        confidence = (
            (ml_confidence * self.ML_WEIGHT) + (rule_confidence * self.RULE_WEIGHT)
            if ml_result['available']
            else rule_confidence
        )

        alerts = list(rule_analysis.get('alerts', []))
        allergens_detected = list(rule_analysis.get('allergens_detected', []))
        if ml_result['available'] and ml_result['has_allergens'] and ml_score >= 50:
            profile_labels = self._profile_allergy_labels(user_allergies)
            if profile_labels and not allergens_detected:
                alerts.append(
                    'Random Forest detected an allergen signal; review against your selected allergies: '
                    + ', '.join(profile_labels)
                )
            elif not profile_labels:
                alerts.append('Random Forest detected a common allergen signal in this product.')

        if not ml_result['available'] and ml_result.get('warning'):
            alerts.append(ml_result['warning'])

        result = {
            **rule_analysis,
            'risk_level': final_risk_level,
            'risk_score': int(round(min(max(combined_score, 0), 100))),
            'confidence': round(min(max(confidence, 0.0), 1.0), 2),
            'ml_confidence': round(ml_confidence, 2),
            'rule_confidence': round(rule_confidence, 2),
            'ml_allergen_probability': round(float(ml_result.get('allergen_probability', 0.0)), 2),
            'rule_risk_score': int(round(min(max(rule_score, 0), 100))),
            'allergens_detected': list(dict.fromkeys(allergens_detected)),
            'alerts': list(dict.fromkeys(alerts)),
            'recommendations': self._recommendations(final_risk_level, profile_aware),
            'detection_method': (
                'Random Forest Primary Classifier + Profile Rules'
                if ml_result['available']
                else 'Profile Rules Only (Random Forest unavailable)'
            ),
            'model_loaded': self.model_loaded,
            'weights': {
                'ml': self.ML_WEIGHT if ml_result['available'] else 0.0,
                'rule_based': self.RULE_WEIGHT if ml_result['available'] else 1.0,
            },
        }
        return result
    
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
        raw_ingredients = ocr_result.get('ingredients_list', [])
        ingredients = parse_ingredients_input(raw_text or ingredients_text or raw_ingredients)
        analysis = self.analyze_ingredients(
            ingredients or raw_ingredients or ingredients_text,
            user_allergies=user_allergies,
            user_dietary=user_dietary,
            raw_text=raw_text,
        )
        
        processing_time = time.time() - start_time
        
        return {
            'success': True,
            'user_id': user_id,
            'ingredients': ingredients or raw_ingredients,
            'analysis': {
                **analysis,
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
