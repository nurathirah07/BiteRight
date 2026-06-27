"""
test_nlp_accuracy.py
====================
Comprehensive NLP Accuracy Testing Script for BiteRight.

Uses test_data/ground_truth.csv together with the allergy profiles defined in
test_data/annotation_reference.txt to measure:
  - Binary Safe/Unsafe classification accuracy
  - Precision, Recall, F1-Score (binary and per-allergen)
  - Per-profile accuracy
  - Confusion matrix

How it works
------------
Instead of looking up users in Firestore (the real profiles TEST_PROFILE_1..5
are NOT real Firebase users) the script hits the dedicated inline-analysis
endpoint  POST /test/analyze  which accepts allergies directly in the request
body and bypasses any database lookup.  This endpoint is already implemented in
app.py and is the correct one to use for automated accuracy tests.

Usage
-----
  # Start the backend first:
  python app.py

  # Run full test suite:
  python test_nlp_accuracy.py

  # Test a single image:
  python test_nlp_accuracy.py --image "almond milk.jpg"
"""

import sys
import os
import json
import argparse
import requests
import pandas as pd
from datetime import datetime
from typing import Dict, List, Optional

# Prevent encoding issues with Unicode checkmarks on Windows console
sys.stdout.reconfigure(encoding='utf-8')


# ---------------------------------------------------------------------------
# Profile definitions  (from test_data/annotation_reference.txt)
# ---------------------------------------------------------------------------

PROFILE_ALLERGIES: Dict[str, List[Dict]] = {
    "TEST_PROFILE_1": [
        {"id": "peanuts",  "severity": "high"},
        {"id": "soy",      "severity": "medium"},
        {"id": "eggs",     "severity": "medium"},
    ],
    "TEST_PROFILE_2": [
        {"id": "milk",      "severity": "high"},
        {"id": "tree_nuts", "severity": "high"},
        {"id": "shellfish", "severity": "high"},
    ],
    "TEST_PROFILE_3": [
        {"id": "peanuts",   "severity": "high"},
        {"id": "sesame",    "severity": "medium"},
        {"id": "tree_nuts", "severity": "high"},
        {"id": "fish",      "severity": "high"},
    ],
    "TEST_PROFILE_4": [
        {"id": "shellfish", "severity": "high"},
        {"id": "peanuts",   "severity": "high"},
        {"id": "eggs",      "severity": "medium"},
    ],
    "TEST_PROFILE_5": [
        {"id": "eggs",   "severity": "medium"},
        {"id": "fish",   "severity": "high"},
        {"id": "soy",    "severity": "medium"},
        {"id": "gluten", "severity": "medium"},
    ],
}

# Allergen normalization so detected names match profile allergy IDs
ALLERGEN_NORMALIZATION_MAP = {
    "tree nuts":      "tree_nuts",
    "tree_nuts":      "tree_nuts",
    "peanuts":        "peanuts",
    "peanut":         "peanuts",
    "milk":           "milk",
    "dairy":          "milk",
    "eggs":           "eggs",
    "egg":            "eggs",
    "soy":            "soy",
    "soybeans":       "soy",
    "wheat":          "wheat",
    "gluten":         "gluten",
    "fish":           "fish",
    "shellfish":      "shellfish",
    "sesame":         "sesame",
    "sesame-seeds":   "sesame",
    "mustard":        "mustard",
    "celery":         "celery",
    "sulphites":      "sulphites",
    "coconut":        "tree_nuts",
    "oats":           "gluten",
    "barley":         "gluten",
    "rye":            "gluten",
    "almond":         "tree_nuts",
    "walnut":         "tree_nuts",
    "cashew":         "tree_nuts",
    "pecan":          "tree_nuts",
    "pistachio":      "tree_nuts",
    "hazelnut":       "tree_nuts",
    "macadamia":      "tree_nuts",
}


# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------

def normalize_allergen(allergen: str) -> str:
    """Normalise an allergen name to its canonical form."""
    return ALLERGEN_NORMALIZATION_MAP.get(allergen.lower().strip(),
                                          allergen.lower().strip())


def parse_expected_allergens(row: pd.Series, profile_id: str) -> List[str]:
    """
    Derive the allergens that make this product *unsafe* for a given profile.

    Logic:
      - If the product is safe for the profile → no allergens apply.
      - Otherwise, find the intersection between the allergens present in the
        product and the allergens the profile is allergic to.
    """
    safe_col = f"safe_for_{profile_id}"
    safe_val = row.get(safe_col, True)

    # Treat 'TRUE' string as True
    if str(safe_val).upper() == "TRUE":
        return []

    # Product is unsafe → determine which of the profile's allergens are present
    actual_allergens_text = str(row.get("actual_allergens_present", "")).lower()
    profile_allergy_ids = {a["id"] for a in PROFILE_ALLERGIES.get(profile_id, [])}

    # Map between canonical allergen IDs and keywords to search for in the text
    allergen_keywords: Dict[str, List[str]] = {
        "peanuts":   ["peanut"],
        "tree_nuts": ["tree nut", "almond", "walnut", "cashew", "coconut",
                      "pecan", "pistachio", "hazelnut", "macadamia"],
        "milk":      ["milk", "dairy", "whey", "casein"],
        "eggs":      ["egg"],
        "soy":       ["soy"],
        "wheat":     ["wheat"],
        "gluten":    ["gluten", "wheat", "barley", "rye", "malt", "oat"],
        "fish":      ["fish"],
        "shellfish": ["shellfish", "shrimp", "crab", "prawn", "lobster"],
        "sesame":    ["sesame"],
        "mustard":   ["mustard"],
        "celery":    ["celery"],
        "sulphites": ["sulphite", "sulfite", "sulphur dioxide", "sulfur dioxide"],
    }

    triggered = []
    for allergy_id in profile_allergy_ids:
        for kw in allergen_keywords.get(allergy_id, [allergy_id]):
            if kw in actual_allergens_text:
                triggered.append(allergy_id)
                break

    return list(set(triggered))


def calculate_metrics(expected: List[str], detected: List[str]) -> Dict:
    """Return TP / FP / FN counts plus precision and recall."""
    exp_set = set(expected)
    det_set = set(detected)

    tp = len(exp_set & det_set)
    fp = len(det_set - exp_set)
    fn = len(exp_set - det_set)

    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall    = tp / (tp + fn) if (tp + fn) > 0 else 0.0

    return {
        "true_positives":  tp,
        "false_positives": fp,
        "false_negatives": fn,
        "precision": precision,
        "recall":    recall,
    }


# ---------------------------------------------------------------------------
# Main tester class
# ---------------------------------------------------------------------------

class NLPAccuracyTester:
    """
    Runs NLP accuracy tests against the /test/analyze endpoint.

    This endpoint is specifically designed for testing — it accepts allergies
    and dietary restrictions inline (no Firestore user lookup required).
    """

    TEST_ENDPOINT = "/test/analyze"

    def __init__(self, api_url: str = "http://127.0.0.1:5000"):
        self.api_url = api_url.rstrip("/")
        self.results: List[Dict] = []

    # ------------------------------------------------------------------
    # Core per-test method
    # ------------------------------------------------------------------

    def test_single_product(
        self,
        product_name: str,
        ingredients_text: str,
        profile_id: str,
        expected_safe: bool,
        expected_risk: str,
        expected_allergens: List[str],
        expected_score: float,
    ) -> Dict:
        """
        Send one product + one profile to the backend and compare the result
        against the ground-truth expectation.
        """
        allergies = PROFILE_ALLERGIES.get(profile_id, [])
        dietary   = []  # test profiles don't have dietary restrictions

        try:
            response = requests.post(
                f"{self.api_url}{self.TEST_ENDPOINT}",
                json={
                    "ingredients_text":    ingredients_text,
                    "allergies":           allergies,
                    "dietary_restrictions": dietary,
                },
                timeout=30,
            )

            if response.status_code != 200:
                return {
                    "success":      False,
                    "error":        f"HTTP {response.status_code}: {response.text[:300]}",
                    "product_name": product_name,
                    "profile_id":   profile_id,
                }

            data = response.json()

            if "error" in data:
                return {
                    "success":      False,
                    "error":        data["error"],
                    "product_name": product_name,
                    "profile_id":   profile_id,
                }

            # --- Extract predictions ---
            predicted_risk  = data.get("risk_level", "unknown")
            predicted_score = data.get("risk_score", 0)

            # Detected allergens that belong to this user's profile
            raw_personal = data.get("personal_allergens_detected") or \
                           data.get("personal_allergens") or []
            # Also look at detected allergens (all of them)
            raw_detected = data.get("allergens_detected") or []

            # Normalise
            personal_norm = [normalize_allergen(str(a)) for a in raw_personal if a]
            detected_norm = [normalize_allergen(str(a)) for a in raw_detected  if a]

            # Binary safe/unsafe
            # "caution" means allergens were found but none match the profile
            #  → for the user it is effectively "safe" from a personal standpoint.
            # But if risk_level is "unsafe" it means personal allergens were hit.
            predicted_safe = predicted_risk in ("safe", "caution")
            # Ground truth: expected_safe == True means the product is safe
            # for THIS profile (no matching allergens).

            # Per-allergen metrics
            metrics = calculate_metrics(expected_allergens, personal_norm)

            return {
                "success":          True,
                "product_name":     product_name,
                "profile_id":       profile_id,
                "expected_safe":    expected_safe,
                "predicted_safe":   predicted_safe,
                "expected_risk":    expected_risk,
                "predicted_risk":   predicted_risk,
                "expected_score":   expected_score,
                "predicted_score":  predicted_score,
                "expected_allergens":  expected_allergens,
                "detected_allergens":  personal_norm,  # personal allergens
                "all_detected_allergens": detected_norm,
                "correct":          predicted_safe == expected_safe,
                "risk_match":       predicted_risk == expected_risk,
                "metrics":          metrics,
                "has_personal_allergens": data.get("has_personal_allergens", False),
            }

        except requests.exceptions.ConnectionError:
            return {
                "success":  False,
                "error":    "Cannot connect to Flask server. Make sure it is running: python app.py",
                "product_name": product_name,
                "profile_id": profile_id,
            }
        except Exception as exc:
            return {
                "success":      False,
                "error":        str(exc),
                "product_name": product_name,
                "profile_id":   profile_id,
            }

    # ------------------------------------------------------------------
    # Batch runner
    # ------------------------------------------------------------------

    def run_tests_from_ground_truth(self, ground_truth_csv: str) -> List[Dict]:
        """
        Iterate over every row in ground_truth.csv and every TEST_PROFILE_*
        column, call the NLP backend, and store results.
        """
        df = pd.read_csv(ground_truth_csv)

        # Identify which profiles are present in the CSV
        profile_ids = sorted(
            col.replace("safe_for_", "")
            for col in df.columns
            if col.startswith("safe_for_")
        )

        # Only test profiles that we have allergy definitions for
        known_profiles = [p for p in profile_ids if p in PROFILE_ALLERGIES]
        unknown_profiles = [p for p in profile_ids if p not in PROFILE_ALLERGIES]
        if unknown_profiles:
            print(f"\n⚠️  Skipping unknown profiles (not in annotation_reference): "
                  f"{', '.join(unknown_profiles)}")

        print("=" * 70)
        print("NLP ACCURACY TEST SUITE")
        print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 70)
        print(f"\n📊 Products in ground truth : {len(df)}")
        print(f"📊 Profiles to test         : {len(known_profiles)}")
        print(f"   {', '.join(known_profiles)}")
        print()

        self.results = []
        total = 0
        successful = 0

        for _, row in df.iterrows():
            img_filename = str(row.get("image_filename", "Unknown"))
            product_name = (
                img_filename
                .replace(".jpg", "")
                .replace(".jpeg", "")
                .replace(".png", "")
            )
            ingredients = row.get("actual_ingredients", "")

            if pd.isna(ingredients) or not str(ingredients).strip():
                print(f"\n⚠️  No ingredients for '{product_name}' — skipping")
                continue

            ingredients = str(ingredients).strip()
            print(f"\n📝 {product_name}")
            print(f"   Ingredients: {ingredients[:80]}{'...' if len(ingredients) > 80 else ''}")

            for profile_id in known_profiles:
                safe_col  = f"safe_for_{profile_id}"
                risk_col  = f"expected_risk_{profile_id}"
                score_col = f"expected_risk_score_{profile_id}"

                if safe_col not in row:
                    continue

                safe_val     = row[safe_col]
                expected_safe = str(safe_val).upper() == "TRUE"
                expected_risk = str(row.get(risk_col,
                                            "safe" if expected_safe else "unsafe"))
                expected_score = float(row.get(score_col, 0) or 0)

                expected_allergens = parse_expected_allergens(row, profile_id)

                total += 1
                result = self.test_single_product(
                    product_name   = product_name,
                    ingredients_text = ingredients,
                    profile_id     = profile_id,
                    expected_safe  = expected_safe,
                    expected_risk  = expected_risk,
                    expected_allergens = expected_allergens,
                    expected_score = expected_score,
                )

                if result["success"]:
                    successful += 1
                    icon = "✅" if result["correct"] else "❌"
                    exp_label  = "SAFE"   if expected_safe           else "UNSAFE"
                    pred_label = "SAFE"   if result["predicted_safe"] else "UNSAFE"
                    print(f"   {icon} [{profile_id}] "
                          f"Expected={exp_label}  Got={pred_label}  "
                          f"(risk={result['predicted_risk']}, "
                          f"score={result['predicted_score']})")

                    if not result["correct"]:
                        print(f"      ↳ Expected personal allergens : {result['expected_allergens']}")
                        print(f"      ↳ Detected personal allergens : {result['detected_allergens']}")
                        print(f"      ↳ All detected allergens      : {result['all_detected_allergens']}")
                else:
                    print(f"   💥 [{profile_id}] ERROR — {result.get('error', 'Unknown error')}")

                self.results.append(result)

        print(f"\n{'─'*70}")
        print(f"Test run complete: {successful}/{total} API calls succeeded")
        return self.results

    # ------------------------------------------------------------------
    # Report generator
    # ------------------------------------------------------------------

    def generate_report(self) -> Dict:
        """Print and save a comprehensive accuracy report."""

        successful = [r for r in self.results if r.get("success", False)]
        failed     = [r for r in self.results if not r.get("success", False)]

        if not successful:
            print("\n❌ No successful test results to report.")
            return {}

        total   = len(successful)
        correct = sum(1 for r in successful if r.get("correct", False))
        overall_accuracy = correct / total if total else 0.0

        # --- Binary classification (Safe vs Unsafe) ---
        # Confusion matrix: "positive" = UNSAFE, "negative" = SAFE
        tn = fp = fn = tp = 0
        for r in successful:
            exp_safe  = r["expected_safe"]
            pred_safe = r["predicted_safe"]
            if     exp_safe and     pred_safe: tn += 1   # correctly safe
            elif   exp_safe and not pred_safe: fp += 1   # false unsafe
            elif not exp_safe and     pred_safe: fn += 1  # missed unsafe
            elif not exp_safe and not pred_safe: tp += 1  # correctly unsafe

        bin_precision = tp / (tp + fp) if (tp + fp) else 0.0
        bin_recall    = tp / (tp + fn) if (tp + fn) else 0.0
        bin_f1 = (2 * bin_precision * bin_recall / (bin_precision + bin_recall)
                  if (bin_precision + bin_recall) else 0.0)

        # --- Per-allergen detection metrics ---
        total_tp = sum(r["metrics"]["true_positives"]  for r in successful)
        total_fp = sum(r["metrics"]["false_positives"] for r in successful)
        total_fn = sum(r["metrics"]["false_negatives"] for r in successful)

        alg_precision = total_tp / (total_tp + total_fp) if (total_tp + total_fp) else 0.0
        alg_recall    = total_tp / (total_tp + total_fn) if (total_tp + total_fn) else 0.0
        alg_f1 = (2 * alg_precision * alg_recall / (alg_precision + alg_recall)
                  if (alg_precision + alg_recall) else 0.0)

        # --- Risk level accuracy ---
        risk_match_count = sum(1 for r in successful if r.get("risk_match", False))
        risk_accuracy = risk_match_count / total if total else 0.0

        # --- Risk score MAE ---
        score_errors = [abs(r.get("expected_score", 0) - r.get("predicted_score", 0))
                        for r in successful]
        avg_score_mae = sum(score_errors) / len(score_errors) if score_errors else 0.0

        # --- Per-profile metrics ---
        profile_stats: Dict[str, Dict] = {}
        for r in successful:
            pid = r["profile_id"]
            if pid not in profile_stats:
                profile_stats[pid] = {
                    "correct": 0, "total": 0,
                    "tp": 0, "fp": 0, "fn": 0, "tn": 0,
                }
            profile_stats[pid]["total"] += 1
            if r["correct"]:
                profile_stats[pid]["correct"] += 1
            m = r["metrics"]
            profile_stats[pid]["tp"] += m["true_positives"]
            profile_stats[pid]["fp"] += m["false_positives"]
            profile_stats[pid]["fn"] += m["false_negatives"]

        for pid, stats in profile_stats.items():
            acc = stats["correct"] / stats["total"] if stats["total"] else 0.0
            tp_ = stats["tp"]; fp_ = stats["fp"]; fn_ = stats["fn"]
            prec = tp_ / (tp_ + fp_) if (tp_ + fp_) else 0.0
            rec  = tp_ / (tp_ + fn_) if (tp_ + fn_) else 0.0
            f1_  = 2*prec*rec/(prec+rec) if (prec+rec) else 0.0
            stats["accuracy"]           = acc
            stats["allergen_precision"] = prec
            stats["allergen_recall"]    = rec
            stats["allergen_f1"]        = f1_

        # --- Products with most errors ---
        product_errors: Dict[str, List] = {}
        for r in successful:
            if not r["correct"]:
                pn = r["product_name"]
                product_errors.setdefault(pn, []).append({
                    "profile":   r["profile_id"],
                    "expected":  r["expected_allergens"],
                    "detected":  r["detected_allergens"],
                    "exp_risk":  r["expected_risk"],
                    "pred_risk": r["predicted_risk"],
                })

        # =================== PRINT REPORT ===================
        print("\n" + "=" * 70)
        print("NLP ACCURACY REPORT")
        print("=" * 70)

        print(f"\n📊 TEST STATISTICS")
        print(f"   Total API calls attempted : {len(self.results)}")
        print(f"   Successful responses      : {total}")
        print(f"   Failed / connection errors: {len(failed)}")

        print(f"\n🎯 BINARY CLASSIFICATION  (Safe vs Unsafe per profile)")
        print(f"   Overall accuracy  : {overall_accuracy:.2%}  ({correct}/{total})")
        print()

        print(f"📈 CONFUSION MATRIX")
        print(f"   True  Negatives (correctly predicted SAFE)  : {tn}")
        print(f"   False Positives (predicted UNSAFE, was SAFE) : {fp}")
        print(f"   False Negatives (predicted SAFE,  was UNSAFE): {fn}")
        print(f"   True  Positives (correctly predicted UNSAFE)  : {tp}")

        print(f"\n🎯 BINARY CLASSIFICATION METRICS")
        print(f"   Precision : {bin_precision:.2%}")
        print(f"   Recall    : {bin_recall:.2%}")
        print(f"   F1-Score  : {bin_f1:.2%}")

        print(f"\n🔬 PER-ALLERGEN DETECTION  (personal allergens only)")
        print(f"   True  Positives : {total_tp}")
        print(f"   False Positives : {total_fp}")
        print(f"   False Negatives : {total_fn}")
        print(f"   Precision       : {alg_precision:.2%}")
        print(f"   Recall          : {alg_recall:.2%}")
        print(f"   F1-Score        : {alg_f1:.2%}")

        print(f"\n⚠️  RISK ASSESSMENT")
        print(f"   Risk level accuracy      : {risk_accuracy:.2%}")
        print(f"   Risk score MAE           : {avg_score_mae:.1f} pts")

        print(f"\n👤 PER-PROFILE BREAKDOWN")
        print(f"   {'Profile':<20} {'Accuracy':>10} {'Correct':>10} "
              f"{'Alg-Prec':>10} {'Alg-Rec':>10} {'Alg-F1':>10}")
        print(f"   {'─'*70}")
        for pid, st in sorted(profile_stats.items()):
            allergies_str = ", ".join(a["id"] for a in PROFILE_ALLERGIES.get(pid, []))
            print(f"   {pid:<20} {st['accuracy']:>10.2%} "
                  f"{st['correct']:>4}/{st['total']:<5} "
                  f"{st['allergen_precision']:>10.2%} "
                  f"{st['allergen_recall']:>10.2%} "
                  f"{st['allergen_f1']:>10.2%}")
            print(f"   {'':20}  Allergies: {allergies_str}")

        if product_errors:
            print(f"\n⚠️  PRODUCTS WITH MOST ERRORS")
            for product, errors in sorted(product_errors.items(),
                                          key=lambda x: -len(x[1]))[:5]:
                print(f"\n   📦 {product}  ({len(errors)} profile(s) wrong)")
                for e in errors[:3]:
                    print(f"      [{e['profile']}] "
                          f"Expected {e['exp_risk'].upper()}, "
                          f"Got {e['pred_risk'].upper()}")
                    print(f"        Expected allergens : {e['expected']}")
                    print(f"        Detected allergens : {e['detected']}")

        if failed:
            print(f"\n💥 FAILED CALLS  ({len(failed)} total)")
            for f in failed[:5]:
                print(f"   {f['product_name']} / {f['profile_id']}: {f.get('error', '?')}")

        # =================== SAVE JSON ===================
        os.makedirs("test_results", exist_ok=True)
        report_path = "test_results/nlp_accuracy_report.json"
        with open(report_path, "w") as fh:
            json.dump(
                {
                    "generated_at": datetime.now().isoformat(),
                    "summary": {
                        "total_tests":         total,
                        "overall_accuracy":    overall_accuracy,
                        "binary_precision":    bin_precision,
                        "binary_recall":       bin_recall,
                        "binary_f1":           bin_f1,
                        "allergen_precision":  alg_precision,
                        "allergen_recall":     alg_recall,
                        "allergen_f1":         alg_f1,
                        "risk_level_accuracy": risk_accuracy,
                        "avg_score_mae":       avg_score_mae,
                        "confusion_matrix":    {"tn": tn, "fp": fp,
                                                "fn": fn, "tp": tp},
                    },
                    "per_profile": profile_stats,
                    "product_errors": {
                        k: v for k, v in sorted(
                            product_errors.items(), key=lambda x: -len(x[1])
                        )
                    },
                    "details": self.results,
                },
                fh,
                indent=2,
                default=str,
            )

        print(f"\n📁 Full results saved to: {report_path}")

        return {
            "overall_accuracy":   overall_accuracy,
            "binary_precision":   bin_precision,
            "binary_recall":      bin_recall,
            "binary_f1":          bin_f1,
            "allergen_precision": alg_precision,
            "allergen_recall":    alg_recall,
            "allergen_f1":        alg_f1,
            "risk_accuracy":      risk_accuracy,
        }


# ---------------------------------------------------------------------------
# Top-level runners
# ---------------------------------------------------------------------------

def run_nlp_accuracy_tests(ground_truth_path: str = "test_data/ground_truth.csv"):
    """Full test suite entry point."""

    # 1. Verify Flask is up
    try:
        r = requests.get("http://127.0.0.1:5000/health", timeout=5)
        if r.status_code == 200:
            print("✅ Flask API is running (health check OK)")
        else:
            print(f"⚠️  Flask responded with HTTP {r.status_code}")
    except Exception:
        print("❌ Flask API is NOT running!")
        print("   Please start the backend first:  python app.py")
        return None

    # 2. Verify /test/analyze endpoint exists
    try:
        probe = requests.post(
            "http://127.0.0.1:5000/test/analyze",
            json={"ingredients_text": "water", "allergies": [], "dietary_restrictions": []},
            timeout=5,
        )
        if probe.status_code == 200:
            print("✅ /test/analyze endpoint is available")
        else:
            print(f"⚠️  /test/analyze returned HTTP {probe.status_code} — "
                  "check app.py has the endpoint")
    except Exception as exc:
        print(f"⚠️  Could not probe /test/analyze: {exc}")

    # 3. Verify ground truth exists
    if not os.path.exists(ground_truth_path):
        print(f"❌ Ground truth CSV not found: {ground_truth_path}")
        return None
    print(f"✅ Ground truth CSV found: {ground_truth_path}")

    # 4. Run tests
    tester = NLPAccuracyTester()
    tester.run_tests_from_ground_truth(ground_truth_path)
    results = tester.generate_report()

    # 5. Interpretation guide
    print("\n" + "=" * 70)
    print("INTERPRETATION GUIDE")
    print("=" * 70)

    accuracy = results.get("overall_accuracy", 0)
    if accuracy >= 0.90:
        print(f"✅ EXCELLENT: {accuracy:.2%} overall accuracy — production-ready")
    elif accuracy >= 0.80:
        print(f"👍 GOOD     : {accuracy:.2%} overall accuracy — minor improvements possible")
    elif accuracy >= 0.70:
        print(f"⚠️  FAIR     : {accuracy:.2%} overall accuracy — needs improvement")
    else:
        print(f"❌ POOR     : {accuracy:.2%} overall accuracy — significant work required")

    f1 = results.get("binary_f1", 0)
    if f1 >= 0.85:
        print(f"✅ Excellent binary F1    : {f1:.2%}")
    elif f1 >= 0.70:
        print(f"👍 Good binary F1         : {f1:.2%}")
    else:
        print(f"⚠️  Low binary F1          : {f1:.2%} — check false-safe predictions")

    alg_f1 = results.get("allergen_f1", 0)
    if alg_f1 >= 0.80:
        print(f"✅ Excellent allergen F1  : {alg_f1:.2%}")
    elif alg_f1 >= 0.65:
        print(f"👍 Good allergen F1       : {alg_f1:.2%}")
    else:
        print(f"⚠️  Low allergen F1        : {alg_f1:.2%} — "
              "NLP is missing or over-detecting allergens")

    return results


def test_single_image(image_name: str,
                      ground_truth_path: str = "test_data/ground_truth.csv"):
    """Run all profiles against a single image to quickly debug it."""

    if not os.path.exists(ground_truth_path):
        print(f"❌ Ground truth not found: {ground_truth_path}")
        return

    df = pd.read_csv(ground_truth_path)
    matches = df[df["image_filename"] == image_name]

    if matches.empty:
        print(f"❌ '{image_name}' not found in ground truth")
        print("   Available filenames:")
        for fn in df["image_filename"].tolist():
            print(f"     {fn}")
        return

    row = matches.iloc[0]
    ingredients = str(row.get("actual_ingredients", "")).strip()
    actual_allergens = row.get("actual_allergens_present", "N/A")

    print(f"\n{'='*60}")
    print(f"📷 Image       : {image_name}")
    print(f"🧪 Allergens   : {actual_allergens}")
    print(f"📝 Ingredients : {ingredients[:120]}{'...' if len(ingredients)>120 else ''}")
    print(f"{'='*60}")

    for profile_id, allergies in PROFILE_ALLERGIES.items():
        safe_col     = f"safe_for_{profile_id}"
        expected_safe = str(row.get(safe_col, "TRUE")).upper() == "TRUE"

        try:
            resp = requests.post(
                "http://127.0.0.1:5000/test/analyze",
                json={
                    "ingredients_text": ingredients,
                    "allergies": allergies,
                    "dietary_restrictions": [],
                },
                timeout=30,
            )

            if resp.status_code == 200:
                data = resp.json()
                pred_risk  = data.get("risk_level", "unknown")
                pred_score = data.get("risk_score", 0)
                personal   = data.get("personal_allergens_detected", [])
                all_det    = data.get("allergens_detected", [])

                pred_safe = pred_risk in ("safe", "caution")
                icon = "✅" if pred_safe == expected_safe else "❌"
                exp_lbl  = "SAFE"   if expected_safe else "UNSAFE"
                pred_lbl = "SAFE"   if pred_safe     else "UNSAFE"

                allergy_ids = [a["id"] for a in allergies]
                print(f"\n{icon} {profile_id}  [{', '.join(allergy_ids)}]")
                print(f"   Expected  : {exp_lbl}")
                print(f"   Predicted : {pred_lbl}  (risk={pred_risk}, score={pred_score})")
                print(f"   Personal allergens detected : {personal}")
                print(f"   All allergens detected      : {all_det}")
            else:
                print(f"\n💥 {profile_id}: HTTP {resp.status_code}")

        except Exception as exc:
            print(f"\n💥 {profile_id}: {exc}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="BiteRight NLP Accuracy Test — uses /test/analyze endpoint"
    )
    parser.add_argument(
        "--image", "-i",
        type=str,
        help='Test a single image filename (e.g. "almond milk.jpg")',
    )
    parser.add_argument(
        "--ground-truth", "-g",
        type=str,
        default="test_data/ground_truth.csv",
        help="Path to ground_truth.csv (default: test_data/ground_truth.csv)",
    )
    args = parser.parse_args()

    if args.image:
        test_single_image(args.image, args.ground_truth)
    else:
        run_nlp_accuracy_tests(args.ground_truth)