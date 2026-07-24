# biteright_backend/services/processing_service.py
"""
Processing Service — Random Forest (RF) as Primary Engine

Architecture:
  - Random Forest (70%): primary verdict — trained on TF-IDF ingredient text,
    outputs a binary has_allergens probability that drives overall risk scoring.
  - Rule-based / risk_analyzer (30%): supporting role — provides per-ingredient
    allergen labels, dietary violation detail, and cross-contact warnings that
    RF (binary output) cannot supply on its own.

If the RF model files are missing, the system gracefully falls back to
rule-based analysis only.
"""

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
    # RF-primary weights — Random Forest drives the overall verdict
    ML_WEIGHT = 0.6      # Random Forest contributes 60%
    RULE_WEIGHT = 0.4    # Rule-based contributes 40%
    MIN_ML_CONFIDENCE = 0.55  # Lower threshold: engage RF more broadly

    def __init__(self, db):
        self.db = db
        self.detector = detector
        self.ml_model = None
        self.vectorizer = None
        self.model_loaded = False

    def initialize(self):
        result = self.detector.load_allergens_from_firestore(self.db)
        self._load_ml_model()
        return result

    def _load_ml_model(self):
        backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        model_path = os.path.join(backend_dir, 'models', 'random_forest.pkl')
        vectorizer_path = os.path.join(backend_dir, 'models', 'vectorizer.pkl')
        try:
            if os.path.exists(model_path) and os.path.exists(vectorizer_path):
                self.ml_model = joblib.load(model_path)
                self.vectorizer = joblib.load(vectorizer_path)
                self.model_loaded = True
                print("Random Forest model loaded")
            else:
                print("WARNING: Model files missing")
                self.model_loaded = False
        except Exception as e:
            print(f"WARNING: Error loading model: {e}")
            self.model_loaded = False

    def _ml_prediction(self, ingredients_text):
        """Run the Random Forest classifier on the given ingredient text.

        Returns a dict with:
          available          — False if model not loaded or confidence < MIN_ML_CONFIDENCE
          has_allergens      — RF binary prediction
          allergen_probability — P(class=1), i.e. probability of allergen presence
          confidence         — max class probability (certainty of the prediction)
        """
        if not self.model_loaded or self.ml_model is None:
            return {'available': False, 'has_allergens': False,
                    'allergen_probability': 0.0, 'confidence': 0.0}

        try:
            text = normalize_text(ingredients_text)
            text_vec = self.vectorizer.transform([text])
            prediction = self.ml_model.predict(text_vec)[0]
            probabilities = self.ml_model.predict_proba(text_vec)[0]
            confidence = float(max(probabilities))

            # Skip RF if it is not confident enough; fall back to rules-only
            if confidence < self.MIN_ML_CONFIDENCE:
                return {'available': False, 'has_allergens': False,
                        'allergen_probability': 0.0, 'confidence': confidence}

            allergen_probability = probabilities[1] if len(probabilities) > 1 else 0.0
            return {
                'available': True,
                'has_allergens': bool(prediction),
                'allergen_probability': round(allergen_probability, 4),
                'confidence': round(confidence, 4),
            }
        except Exception as e:
            print(f"RF prediction failed: {e}")
            return {'available': False, 'has_allergens': False,
                    'allergen_probability': 0.0, 'confidence': 0.0}

    def rf_predict(self, ingredients_text):
        """Public wrapper around _ml_prediction for direct use by app.py endpoints.

        Returns the same dict as _ml_prediction so callers can inspect
        `available`, `has_allergens`, `allergen_probability`, and `confidence`
        without going through the full analyze_ingredients() pipeline.
        """
        return self._ml_prediction(ingredients_text)

    def _risk_level_from_score(self, score):
        if score >= 50:
            return 'unsafe'
        if score >= 25:
            return 'caution'
        return 'safe'

    def analyze_ingredients(self, ingredients_input, user_allergies=None, 
                           user_dietary=None, raw_text=None):
        user_allergies = user_allergies or []
        user_dietary = user_dietary or []
        profile_aware = bool(user_allergies or user_dietary)
        source_text = raw_text if raw_text is not None else ingredients_input
        ingredients = parse_ingredients_input(source_text)
        text_for_ml = ' '.join(ingredients) if ingredients else str(source_text or '')

        # ── Step 1: Rule-based analysis (supporting role — labels + dietary detail) ──
        if profile_aware:
            rule_analysis = build_personalized_analysis(
                ingredients or source_text, user_allergies, user_dietary,
                raw_text=str(source_text or '')
            )
        else:
            rule_analysis = build_general_analysis(ingredients or source_text)

        rule_level = rule_analysis.get('risk_level', 'safe')
        rule_score = rule_analysis.get('risk_score', 0)

        # ── Step 2: Random Forest (primary — drives the overall verdict at 70%) ──
        ml_result = self._ml_prediction(text_for_ml)
        ml_score = ml_result['allergen_probability'] * 100 if ml_result['available'] else 0.0

        # ── Step 3: Combine scores — RF is the lead signal ──
        if ml_result['available'] and ml_result['confidence'] >= self.MIN_ML_CONFIDENCE:
            # RF available: RF 70% drives the verdict, rules add 30% supporting detail
            combined_score = (ml_score * self.ML_WEIGHT) + (rule_score * self.RULE_WEIGHT)
            detection_method = 'Random Forest (Primary) + Rule-Based'
        else:
            # RF unavailable or low-confidence: fall back to rules-only
            combined_score = rule_score
            detection_method = 'Rule-Based Only (RF unavailable)'

        final_risk_level = self._risk_level_from_score(combined_score)
        if profile_aware:
            if rule_level == "safe":
                combined_score = 0.0
                final_risk_level = "safe"
            else:
                # Do not force scores to arbitrary levels; use the dynamic combined score
                final_risk_level = rule_level

        # ── Step 4: Blend confidence scores ──
        rule_confidence = float(rule_analysis.get('confidence', 0.7))
        if ml_result['available'] and ml_result['confidence'] >= self.MIN_ML_CONFIDENCE:
            # RF confidence dominates (weighted average)
            confidence = (ml_result['confidence'] * self.ML_WEIGHT) + (rule_confidence * self.RULE_WEIGHT)
        else:
            confidence = rule_confidence

        # ── Step 5: Alerts — sourced from rules; RF adds a supplementary alert ──
        alerts = list(rule_analysis.get('alerts', []))
        allergens_detected = list(rule_analysis.get('allergens_detected', []))

        # RF high-confidence allergen signal with no rule-level detail → add advisory
        if (ml_result['available'] and ml_result['has_allergens']
                and ml_result['confidence'] >= 0.75 and not allergens_detected):
            alerts.append(
                "Random Forest model detected potential allergens — please verify the ingredient list"
            )

        result = {
            **rule_analysis,
            'risk_level': final_risk_level,
            'risk_score': int(round(min(max(combined_score, 0), 100))),
            'confidence': round(min(max(confidence, 0.0), 1.0), 2),
            'ml_confidence': round(ml_result.get('confidence', 0.0), 2),
            'rule_confidence': round(rule_confidence, 2),
            'allergens_detected': list(dict.fromkeys(allergens_detected)),
            'alerts': list(dict.fromkeys(alerts)),
            'detection_method': detection_method,
            'model_loaded': self.model_loaded,
            'weights': {'ml': self.ML_WEIGHT, 'rule_based': self.RULE_WEIGHT}
        }
        return result

    def process_scan(self, image_bytes, user_id):
        start_time = time.time()
        
        # OCR Extraction
        ocr_result = extract_ingredients(image_bytes)
        if not ocr_result['success']:
            return {'success': False, 'error': ocr_result['error'], 'step': 'ocr'}
        
        # Get user profile
        user_ref = self.db.collection('users').document(user_id).get()
        if not user_ref.exists:
            return {'success': False, 'error': 'User not found', 'step': 'user_profile'}
        
        user_data = user_ref.to_dict()
        user_allergies = user_data.get('allergies', [])
        user_dietary = user_data.get('dietary_restrictions', [])
        
        # Convert to strings
        user_allergy_strings = []
        for allergy in user_allergies:
            if isinstance(allergy, dict):
                user_allergy_strings.append(allergy.get('id', ''))
            else:
                user_allergy_strings.append(str(allergy))
        
        # Analyze
        ingredients_text = ocr_result.get('cleaned_text', '')
        raw_text = ocr_result.get('raw_text', '')
        raw_ingredients = ocr_result.get('ingredients_list', [])
        ingredients = parse_ingredients_input(raw_ingredients or ingredients_text or raw_text)
        
        analysis = self.analyze_ingredients(
            ingredients or raw_ingredients or ingredients_text,
            user_allergies=user_allergies,
            user_dietary=user_dietary,
            raw_text=raw_text,
        )
        
        processing_time = time.time() - start_time
        
        ocr_engine = ocr_result.get('strategy_used', 'OCR.Space API')
        ocr_confidence = ocr_result.get('ocr_confidence', 0.0)

        return {
            'success': True,
            'user_id': user_id,
            'ingredients': ingredients or raw_ingredients,
            'ocr_engine': ocr_engine,
            'ocr_confidence': ocr_confidence,
            'analysis': {
                **analysis,
                'ocr_engine': ocr_engine,
                'ocr_confidence': ocr_confidence,
                'user_profile': {
                    'allergies': user_allergy_strings,
                    'dietary_restrictions': user_dietary
                }
            },
            'raw_text': raw_text,
            'processing_time': f"{processing_time:.2f}s"
        }