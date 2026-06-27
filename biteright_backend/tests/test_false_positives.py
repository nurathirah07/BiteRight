"""
tests/test_false_positives.py
=============================================================
BiteRight NLP False-Positive & Vegan Rule Unit Tests
=============================================================

Covers all 15 false-positive cases from the evaluation report
(71.7% per-allergen precision => 15 FPs per 38 correct detections).

Categories
----------
A. Safe-ingredient false positives  (5 cases)
B. Negation false positives          (5 cases)
C. Short-token / OCR noise           (3 cases)
D. Vegan dietary rules               (2 cases)

Run with:
    cd biteright_backend
    python -m pytest tests/test_false_positives.py -v
"""

import sys
import os

_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SERVICES_DIR = os.path.join(_BACKEND_DIR, "services")
sys.path.insert(0, _BACKEND_DIR)
sys.path.insert(0, _SERVICES_DIR)

import pytest
from services.nlp_service import AllergenDetector
from services.risk_analyzer import build_personalized_analysis


@pytest.fixture(scope="module")
def detector():
    return AllergenDetector()


def _allergen_names(result):
    return set(result.get("detected_allergens", []))


def _ingredient_statuses(result):
    return {d["ingredient"].lower(): d["status"] for d in result.get("ingredient_details", [])}


# ===========================================================================
# GROUP A - Safe-ingredient false positives (5 cases)
# ===========================================================================

class TestSafeIngredientFalsePositives:
    def test_cocoa_butter_not_milk(self, detector):
        """'Cocoa butter' must NOT trigger milk/dairy allergen."""
        result = detector.analyze_ingredients("sugar, cocoa butter, cocoa mass, vanilla")
        assert "milk" not in _allergen_names(result), \
            "FALSE POSITIVE: 'cocoa butter' triggered milk allergen"

    def test_sunflower_lecithin_not_soy(self, detector):
        """'Sunflower lecithin' must NOT trigger soy."""
        result = detector.analyze_ingredients(
            "wheat flour, sugar, sunflower lecithin, salt, raising agent")
        assert "soy" not in _allergen_names(result), \
            "FALSE POSITIVE: 'sunflower lecithin' triggered soy allergen"

    def test_cream_of_tartar_not_milk(self, detector):
        """'Cream of tartar' must NOT trigger milk/dairy."""
        result = detector.analyze_ingredients(
            "sugar, egg whites, cream of tartar, vanilla extract")
        assert "milk" not in _allergen_names(result), \
            "FALSE POSITIVE: 'cream of tartar' triggered milk allergen"

    def test_water_chestnut_not_tree_nuts(self, detector):
        """'Water chestnut' must NOT trigger tree_nuts."""
        result = detector.analyze_ingredients(
            "water chestnuts, bamboo shoots, soy sauce, ginger")
        assert "tree_nuts" not in _allergen_names(result), \
            "FALSE POSITIVE: 'water chestnut' triggered tree_nuts allergen"

    def test_olive_oil_no_allergen(self, detector):
        """'Olive oil' must NOT trigger any allergen."""
        result = detector.analyze_ingredients("tomatoes, olive oil, garlic, basil, salt")
        detected = _allergen_names(result)
        assert "milk" not in detected and "tree_nuts" not in detected, \
            f"FALSE POSITIVE: 'olive oil' triggered allergens: {detected}"


# ===========================================================================
# GROUP B - Negation false positives (5 cases)
# ===========================================================================

class TestNegationFalsePositives:
    def test_contains_no_wheat(self, detector):
        result = detector.analyze_ingredients(
            "rice flour, tapioca starch, salt. Contains no wheat.")
        assert "wheat" not in _allergen_names(result), \
            "FALSE POSITIVE: 'contains no wheat' still triggered wheat"

    def test_free_from_milk(self, detector):
        result = detector.analyze_ingredients(
            "oat drink, sugar, cocoa powder. Free from milk.")
        assert "milk" not in _allergen_names(result), \
            "FALSE POSITIVE: 'free from milk' still triggered milk"

    def test_without_gluten(self, detector):
        result = detector.analyze_ingredients(
            "corn starch, potato flour, xanthan gum. Without gluten.")
        assert "gluten" not in _allergen_names(result), \
            "FALSE POSITIVE: 'without gluten' still triggered gluten"

    def test_does_not_contain_peanuts(self, detector):
        result = detector.analyze_ingredients(
            "sunflower seeds, pumpkin seeds, salt. Does not contain peanuts.")
        assert "peanuts" not in _allergen_names(result), \
            "FALSE POSITIVE: 'does not contain peanuts' still triggered peanuts"

    def test_gluten_free_label(self, detector):
        result = detector.analyze_ingredients(
            "certified gluten-free oats, brown sugar, coconut oil")
        assert "gluten" not in _allergen_names(result), \
            "FALSE POSITIVE: 'gluten-free' label triggered gluten"


# ===========================================================================
# GROUP C - Short-token / OCR noise (3 cases)
# ===========================================================================

class TestShortTokenNoise:
    def test_two_char_noise_no_egg_alert(self, detector):
        """2-char OCR noise 'eg' must NOT trigger eggs."""
        result = detector.analyze_ingredients(
            "sugar, glucose syrup, eg stabiliser, natural flavour")
        assert "eggs" not in _allergen_names(result), \
            "FALSE POSITIVE: 2-char 'eg' triggered eggs allergen"

    def test_two_char_noise_no_soy_alert(self, detector):
        """2-char OCR noise 'oy' must NOT trigger soy."""
        result = detector.analyze_ingredients(
            "water, salt, oy flavouring, acidity regulator")
        assert "soy" not in _allergen_names(result), \
            "FALSE POSITIVE: 2-char 'oy' triggered soy allergen"

    def test_whitelisted_short_token_egg_fires(self, detector):
        """'egg' (whitelisted, 3 chars) SHOULD still fire."""
        result = detector.analyze_ingredients(
            "wheat flour, sugar, egg, butter, vanilla")
        assert "eggs" in _allergen_names(result), \
            "REGRESSION: whitelisted token 'egg' no longer detected"


# ===========================================================================
# GROUP D - Vegan dietary rules (2 cases)
# ===========================================================================

class TestVeganDietaryRules:
    def _vegan_check(self, ingredients_str):
        user_dietary = [{"id": "vegan"}]
        ingredients = [i.strip() for i in ingredients_str.split(",")]
        return build_personalized_analysis(
            ingredients=ingredients,
            user_allergies=[],
            user_dietary=user_dietary,
        )

    def test_olive_oil_is_safe_for_vegan(self):
        """Olive oil is plant-based -> must NOT be flagged for vegans."""
        result = self._vegan_check("tomatoes, olive oil, garlic, basil, salt")
        statuses = _ingredient_statuses(result)
        olive_status = statuses.get("olive oil", "safe")
        assert olive_status == "safe", \
            f"VEGAN FALSE POSITIVE: 'olive oil' was flagged as '{olive_status}'"

    def test_seitan_is_unsafe_for_vegan(self):
        """Seitan is in the vegan forbidden list -> must be flagged."""
        result = self._vegan_check("seitan, soy sauce, ginger, garlic")
        statuses = _ingredient_statuses(result)
        seitan_status = statuses.get("seitan", "safe")
        assert seitan_status in ("unsafe", "caution"), \
            f"VEGAN MISS: 'seitan' was not flagged (status='{seitan_status}')"


# ===========================================================================
# Regression - real allergens must still fire
# ===========================================================================

class TestRegressionRealAllergens:
    def test_real_milk_detected(self, detector):
        result = detector.analyze_ingredients("whole milk, sugar, cocoa powder, butter")
        assert "milk" in _allergen_names(result)

    def test_real_peanut_detected(self, detector):
        result = detector.analyze_ingredients("roasted peanuts, salt, palm oil")
        assert "peanuts" in _allergen_names(result)

    def test_real_soy_detected(self, detector):
        result = detector.analyze_ingredients("water, soybean, salt, sugar")
        assert "soy" in _allergen_names(result)

    def test_real_wheat_detected(self, detector):
        result = detector.analyze_ingredients("wheat flour, yeast, salt, water")
        assert "wheat" in _allergen_names(result)

    def test_real_egg_detected(self, detector):
        result = detector.analyze_ingredients("whole wheat flour, eggs, butter, sugar")
        assert "eggs" in _allergen_names(result)
