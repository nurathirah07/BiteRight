"""
BiteRight Accuracy Test Suite
==============================
Tests 20 images × N profiles from ground_truth.csv using:
  - Pure OCR extraction (no manual fallbacks)
  - Inline profile injection via /test/analyze (no Firestore user needed)
  - Correct risk score direction: 0 = safest, 60-100 = dangerous
  - 3-class evaluation: safe / caution / unsafe

Setup:
  1. python setup_test_data.py        ← creates folders + template files
  2. Fill test_data/ground_truth.csv  ← one row per image
  3. Fill test_data/test_profiles.json← define allergy profiles
  4. Add images to test_data/images/
  5. python test_accuracy.py          ← run tests
"""

import sys
import json
import requests
import os
import time
import csv
from datetime import datetime

# Prevent encoding issues with Unicode checkmarks on Windows console
sys.stdout.reconfigure(encoding='utf-8')


API_URL = "http://127.0.0.1:5000"
GROUND_TRUTH_PATH = "test_data/ground_truth.csv"
PROFILES_PATH = "test_data/test_profiles.json"
IMAGES_DIR = "test_data/images"
RESULTS_DIR = "test_results"


# ── Risk score helpers (new system: 0 = safest, 100 = most dangerous) ──────────

def score_to_label(risk_score: int) -> str:
    """Convert numeric risk score to a human label."""
    if risk_score >= 60:
        return "unsafe"
    if risk_score >= 30:
        return "caution"
    return "safe"


def label_to_binary(label: str) -> int:
    """1 = has risk (caution or unsafe), 0 = safe."""
    return 0 if label == "safe" else 1


# ── Main tester class ───────────────────────────────────────────────────────────

class AccuracyTester:
    def __init__(self, api_url: str = API_URL):
        self.api_url = api_url
        self.results: list[dict] = []
        self.ground_truth: list[dict] = []
        self.profiles: list[dict] = []
        self.profile_ids: list[str] = []

    # ── Data loaders ─────────────────────────────────────────────────────────

    def load_ground_truth(self) -> bool:
        if not os.path.exists(GROUND_TRUTH_PATH):
            print(f"✗ ERROR: {GROUND_TRUTH_PATH} not found! Run setup_test_data.py first.")
            return False

        with open(GROUND_TRUTH_PATH, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            fieldnames = reader.fieldnames or []

            # Detect profile IDs from expected_risk_score_* columns
            risk_cols = [c for c in fieldnames if c.startswith("expected_risk_score_")]
            if not risk_cols:
                # Fallback: detect from safe_for_* columns (old format)
                safe_cols = [c for c in fieldnames if c.startswith("safe_for_")]
                self.profile_ids = [c.replace("safe_for_", "") for c in safe_cols]
            else:
                self.profile_ids = [c.replace("expected_risk_score_", "") for c in risk_cols]

            for row in reader:
                for pid in self.profile_ids:
                    risk_col   = f"expected_risk_{pid}"
                    score_col  = f"expected_risk_score_{pid}"
                    safe_col   = f"safe_for_{pid}"

                    # Normalise risk level — prefer explicit expected_risk_*, fall back to safe_for_*
                    if risk_col in row and row.get(risk_col, "").strip().lower() in ("safe", "caution", "unsafe"):
                        row[risk_col] = row[risk_col].strip().lower()
                    elif safe_col in row:
                        safe_val = str(row.get(safe_col, "TRUE")).strip().upper()
                        row[risk_col] = "safe" if safe_val == "TRUE" else "unsafe"
                    else:
                        row[risk_col] = "safe"

                    # Normalise risk score
                    raw_score = str(row.get(score_col, "")).strip()
                    try:
                        row[score_col] = int(float(raw_score))
                    except (ValueError, TypeError):
                        row[score_col] = {"safe": 0, "caution": 40, "unsafe": 70}.get(row[risk_col], 0)

                self.ground_truth.append(row)

        print(f"✓ Loaded {len(self.ground_truth)} ground truth entries")
        print(f"✓ Profile IDs detected in CSV: {', '.join(self.profile_ids)}")
        return True

    def load_profiles(self) -> bool:
        if not os.path.exists(PROFILES_PATH):
            print(f"✗ ERROR: {PROFILES_PATH} not found! Run setup_test_data.py first.")
            return False

        with open(PROFILES_PATH, "r", encoding="utf-8") as f:
            all_profiles = json.load(f)

        # Try exact ID match first
        matched = [p for p in all_profiles if p["profile_id"] in self.profile_ids]

        if not matched:
            # Positional fallback: the CSV may use generic names (TEST_PROFILE_1 … N)
            # Map them positionally to whatever profiles exist in the JSON
            print(f"⚠  Profile IDs in CSV ({self.profile_ids}) don't match JSON profile_ids.")
            print(f"   Falling back to positional mapping against {len(all_profiles)} profiles in JSON.")
            # Re-map CSV profile_ids to the actual JSON profile_ids
            mapped_ids = []
            for i, csv_pid in enumerate(self.profile_ids):
                if i < len(all_profiles):
                    json_pid = all_profiles[i]["profile_id"]
                    mapped_ids.append(json_pid)
                    # Rename keys in ground_truth for this pid
                    for row in self.ground_truth:
                        for suffix in ("expected_risk_", "expected_risk_score_", "safe_for_"):
                            old_key = f"{suffix}{csv_pid}"
                            new_key = f"{suffix}{json_pid}"
                            if old_key in row:
                                row[new_key] = row.pop(old_key)
            self.profile_ids = mapped_ids
            matched = all_profiles[:len(self.profile_ids)]

        self.profiles = matched

        # Print mapping table
        print(f"✓ Profile mapping ({len(self.profiles)} profiles):")
        for p in self.profiles:
            allergies = ", ".join(
                (a["id"] if isinstance(a, dict) else str(a)) for a in p.get("allergies", [])
            ) or "(none)"
            dietary = ", ".join(p.get("dietary_restrictions", [])) or "(none)"
            print(f"   {p['profile_id']:25s}  allergies={allergies}  dietary={dietary}")

        if not self.profiles:
            print("✗ No profiles could be matched — cannot run tests.")
            return False
        return True

    # ── API calls ─────────────────────────────────────────────────────────────

    def extract_ingredients(self, image_path: str) -> dict:
        """OCR extraction — calls /extract-ingredients."""
        try:
            with open(image_path, "rb") as f:
                response = requests.post(
                    f"{self.api_url}/extract-ingredients",
                    files={"image": f},
                    timeout=200,
                )
            if response.status_code != 200:
                return {"success": False, "error": f"HTTP {response.status_code}: {response.text[:200]}"}

            data = response.json()
            ingredients = data.get("ingredients", [])
            if not ingredients:
                return {"success": False, "error": "No ingredients extracted from image"}

            ingredients_text = (
                ", ".join(ingredients) if isinstance(ingredients, list) else str(ingredients)
            )
            return {
                "success": True,
                "ingredients_text": ingredients_text,
                "extracted_ingredients": ingredients,
                "ocr_confidence": data.get("ocr_confidence", 0.0),
                "raw_text": data.get("raw_text", ""),
            }
        except requests.exceptions.ConnectionError:
            return {"success": False, "error": "Cannot connect to Flask server"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def analyze_inline(self, profile: dict, ingredients_text: str) -> dict:
        """
        Calls /test/analyze with inline allergies — no Firestore user required.
        Returns predicted risk_level, risk_score, and confidence.
        """
        payload = {
            "ingredients_text": ingredients_text,
            "allergies": profile.get("allergies", []),
            "dietary_restrictions": profile.get("dietary_restrictions", []),
        }
        try:
            t0 = time.time()
            response = requests.post(
                f"{self.api_url}/test/analyze",
                json=payload,
                timeout=200,
            )
            elapsed = time.time() - t0

            if response.status_code != 200:
                return {
                    "success": False,
                    "error": f"HTTP {response.status_code}: {response.text[:200]}",
                    "response_time": elapsed,
                }

            data = response.json()
            return {
                "success": True,
                "predicted_risk": data.get("risk_level", "unknown"),
                "predicted_score": int(data.get("risk_score", 0)),
                "confidence": float(data.get("confidence", 0.0)),
                "response_time": elapsed,
                "full_result": data,
            }
        except Exception as e:
            return {"success": False, "error": str(e), "response_time": 0.0}

    # ── Test runner ───────────────────────────────────────────────────────────

    def run_all_tests(self) -> list[dict] | None:
        if not self.load_ground_truth():
            return None
        if not self.load_profiles():
            return None

        total, successful, ocr_failures = 0, 0, 0

        print("\n" + "=" * 65)
        print("RUNNING TESTS")
        print("=" * 65)

        for gt in self.ground_truth:
            image_filename = gt["image_filename"]
            image_path = os.path.join(IMAGES_DIR, image_filename)

            if not os.path.exists(image_path):
                print(f"\n⚠ Image not found — skipping: {image_path}")
                continue

            print(f"\n📷  {image_filename}")

            # Step 1: OCR — once per image
            print("   OCR extraction ...", end=" ", flush=True)
            ocr = self.extract_ingredients(image_path)

            if not ocr["success"]:
                print(f"FAILED ({ocr['error']})")
                ocr_failures += 1
                for profile in self.profiles:
                    total += 1
                    self.results.append(
                        {
                            "success": False,
                            "image_name": image_filename,
                            "profile_id": profile["profile_id"],
                            "error": ocr["error"],
                            "ocr_failure": True,
                        }
                    )
                continue

            ing_count = len(ocr.get("extracted_ingredients", []))
            print(f"OK  ({ing_count} ingredients, OCR conf {ocr['ocr_confidence']:.0%})")
            ingredients_text = ocr["ingredients_text"]

            # Step 2: Analyse against each profile
            for profile in self.profiles:
                pid = profile["profile_id"]
                expected_risk = gt.get(f"expected_risk_{pid}", "safe")
                expected_score = gt.get(f"expected_risk_score_{pid}", 0)
                total += 1

                print(
                    f"   → {pid:20s}  expected={expected_risk:8s} score={expected_score:3d} ...",
                    end=" ",
                    flush=True,
                )

                result = self.analyze_inline(profile, ingredients_text)

                if result["success"]:
                    successful += 1
                    pred_risk = result["predicted_risk"]
                    pred_score = result["predicted_score"]

                    # Binary correct: safe vs any-risk (caution/unsafe both count as "has risk")
                    expected_binary = label_to_binary(expected_risk)
                    predicted_binary = label_to_binary(pred_risk)
                    binary_correct = expected_binary == predicted_binary

                    # Exact 3-class correct
                    exact_correct = expected_risk == pred_risk

                    status = "✅" if binary_correct else "❌"
                    mismatch = "" if exact_correct else f" (exact: {pred_risk})"
                    print(
                        f"{status}  got={pred_risk:8s} score={pred_score:3d}{mismatch}"
                        f"  [{result['response_time']:.1f}s]"
                    )

                    self.results.append(
                        {
                            "success": True,
                            "image_name": image_filename,
                            "profile_id": pid,
                            "profile_allergies": profile.get("allergies", []),
                            "profile_dietary": profile.get("dietary_restrictions", []),
                            # Expected
                            "expected_risk": expected_risk,
                            "expected_score": expected_score,
                            "expected_binary": expected_binary,
                            # Predicted
                            "predicted_risk": pred_risk,
                            "predicted_score": pred_score,
                            "predicted_binary": predicted_binary,
                            "confidence": result["confidence"],
                            # Correctness
                            "binary_correct": binary_correct,
                            "exact_correct": exact_correct,
                            "score_error": abs(expected_score - pred_score),
                            # OCR
                            "ocr_confidence": ocr["ocr_confidence"],
                            "extracted_ingredients": ocr.get("extracted_ingredients", [])[:8],
                            "response_time": result["response_time"],
                        }
                    )
                else:
                    print(f"FAILED ({result.get('error', '?')})")
                    self.results.append(
                        {
                            "success": False,
                            "image_name": image_filename,
                            "profile_id": pid,
                            "error": result.get("error", "Unknown"),
                            "response_time": result.get("response_time", 0),
                        }
                    )

        print("\n" + "=" * 65)
        print(f"DONE  {successful}/{total} successful  |  OCR failures: {ocr_failures} images")
        print("=" * 65)
        return self.results

    # ── Metrics ───────────────────────────────────────────────────────────────

    def calculate_metrics(self) -> dict | None:
        ok = [r for r in self.results if r.get("success")]
        if not ok:
            print("No successful tests to analyse.")
            return None

        print(f"\n📊  Analysing {len(ok)} successful tests …")

        # Binary classification (safe vs has-risk)
        y_act = [r["expected_binary"] for r in ok]
        y_pred = [r["predicted_binary"] for r in ok]

        tp = sum(1 for a, p in zip(y_act, y_pred) if a == 1 and p == 1)
        tn = sum(1 for a, p in zip(y_act, y_pred) if a == 0 and p == 0)
        fp = sum(1 for a, p in zip(y_act, y_pred) if a == 0 and p == 1)
        fn = sum(1 for a, p in zip(y_act, y_pred) if a == 1 and p == 0)

        total = len(y_act)
        accuracy = (tp + tn) / total if total else 0
        precision = tp / (tp + fp) if (tp + fp) else 0
        recall = tp / (tp + fn) if (tp + fn) else 0
        f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0

        # Exact 3-class accuracy
        exact_acc = sum(1 for r in ok if r["exact_correct"]) / len(ok) if ok else 0

        # Risk score MAE (Mean Absolute Error)
        score_errors = [r["score_error"] for r in ok]
        mae = sum(score_errors) / len(score_errors) if score_errors else 0

        # False negative analysis: missed dangerous products
        false_negatives = [r for r in ok if r["expected_binary"] == 1 and r["predicted_binary"] == 0]
        false_positives = [r for r in ok if r["expected_binary"] == 0 and r["predicted_binary"] == 1]

        # Average confidence and OCR
        avg_confidence = sum(r.get("confidence", 0) for r in ok) / len(ok)
        avg_ocr = sum(r.get("ocr_confidence", 0) for r in ok) / len(ok)
        avg_response_time = sum(r.get("response_time", 0) for r in ok) / len(ok)

        # Per-profile metrics
        profile_metrics = {}
        for pid in sorted(set(r["profile_id"] for r in ok)):
            pr = [r for r in ok if r["profile_id"] == pid]
            pa = [r["expected_binary"] for r in pr]
            pp = [r["predicted_binary"] for r in pr]
            p_tp = sum(1 for a, p in zip(pa, pp) if a == 1 and p == 1)
            p_tn = sum(1 for a, p in zip(pa, pp) if a == 0 and p == 0)
            p_fp = sum(1 for a, p in zip(pa, pp) if a == 0 and p == 1)
            p_fn = sum(1 for a, p in zip(pa, pp) if a == 1 and p == 0)
            p_acc = (p_tp + p_tn) / len(pa) if pa else 0
            p_prec = p_tp / (p_tp + p_fp) if (p_tp + p_fp) else 0
            p_rec = p_tp / (p_tp + p_fn) if (p_tp + p_fn) else 0
            p_f1 = 2 * p_prec * p_rec / (p_prec + p_rec) if (p_prec + p_rec) else 0
            p_exact = sum(1 for r in pr if r["exact_correct"]) / len(pr) if pr else 0
            profile_metrics[pid] = {
                "tests": len(pr),
                "accuracy": round(p_acc, 4),
                "precision": round(p_prec, 4),
                "recall": round(p_rec, 4),
                "f1": round(p_f1, 4),
                "exact_3class_accuracy": round(p_exact, 4),
                "confusion": {"tp": p_tp, "tn": p_tn, "fp": p_fp, "fn": p_fn},
            }

        # Per-image metrics
        image_metrics = {}
        for img in sorted(set(r["image_name"] for r in ok)):
            ir = [r for r in ok if r["image_name"] == img]
            correct = sum(1 for r in ir if r["binary_correct"])
            image_metrics[img] = {
                "tests": len(ir),
                "binary_correct": correct,
                "binary_accuracy": round(correct / len(ir), 4) if ir else 0,
                "ocr_confidence": round(ir[0].get("ocr_confidence", 0), 4) if ir else 0,
            }

        return {
            "timestamp": datetime.now().isoformat(),
            "total_tests": len(self.results),
            "successful_tests": len(ok),
            "failed_tests": len(self.results) - len(ok),
            # Binary
            "binary_accuracy": round(accuracy, 4),
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "f1_score": round(f1, 4),
            # 3-class
            "exact_3class_accuracy": round(exact_acc, 4),
            # Risk score
            "risk_score_mae": round(mae, 2),
            # Operational
            "avg_confidence": round(avg_confidence, 4),
            "avg_ocr_confidence": round(avg_ocr, 4),
            "avg_response_time_s": round(avg_response_time, 3),
            # Confusion matrix
            "confusion_matrix": {"TP": tp, "TN": tn, "FP": fp, "FN": fn},
            # Errors
            "false_negative_count": len(false_negatives),
            "false_negative_cases": [
                {"image": r["image_name"], "profile": r["profile_id"],
                 "expected": r["expected_risk"], "got": r["predicted_risk"]}
                for r in false_negatives
            ],
            "false_positive_count": len(false_positives),
            "false_positive_cases": [
                {"image": r["image_name"], "profile": r["profile_id"],
                 "expected": r["expected_risk"], "got": r["predicted_risk"]}
                for r in false_positives
            ],
            # Breakdowns
            "profile_metrics": profile_metrics,
            "image_metrics": image_metrics,
        }

    # ── Report printer ────────────────────────────────────────────────────────

    def print_report(self, metrics: dict) -> None:
        if not metrics:
            print("No metrics to report.")
            return

        SEP = "=" * 65
        DIV = "-" * 45

        print(f"\n{SEP}")
        print("BITERIGHT ACCURACY REPORT")
        print(f"{SEP}\n")

        print("📊  TEST SUMMARY")
        print(DIV)
        print(f"  Total test cases   : {metrics['total_tests']}")
        print(f"  Successful         : {metrics['successful_tests']}")
        print(f"  Failed             : {metrics['failed_tests']}")

        if metrics["successful_tests"] == 0:
            print("\n⚠ No successful tests. Check Flask server and image paths.")
            return

        cm = metrics["confusion_matrix"]
        print(f"\n📈  CONFUSION MATRIX  (binary: safe vs has-risk)")
        print(DIV)
        print(f"                    Predicted →")
        print(f"                     SAFE     HAS-RISK")
        print(f"  Actual SAFE        {cm['TN']:5d}    {cm['FP']:5d}   (FP = over-alert)")
        print(f"  Actual HAS-RISK    {cm['FN']:5d}    {cm['TP']:5d}   (FN = missed danger ⚠)")

        print(f"\n🎯  KEY METRICS")
        print(DIV)
        print(f"  Binary Accuracy      : {metrics['binary_accuracy']:.2%}")
        print(f"  Precision            : {metrics['precision']:.2%}   (of flagged, how many correct)")
        print(f"  Recall               : {metrics['recall']:.2%}   (of real risks, how many caught)")
        print(f"  F1-Score             : {metrics['f1_score']:.2%}")
        print(f"  3-Class Accuracy     : {metrics['exact_3class_accuracy']:.2%}   (safe/caution/unsafe exact match)")
        print(f"  Risk Score MAE       : {metrics['risk_score_mae']:.1f} pts  (0-100 scale, lower is better)")
        print(f"  Avg OCR Confidence   : {metrics['avg_ocr_confidence']:.2%}")
        print(f"  Avg Analysis Conf    : {metrics['avg_confidence']:.2%}")
        print(f"  Avg Response Time    : {metrics['avg_response_time_s']:.2f}s")

        print(f"\n⚠  MISSED DANGERS  (False Negatives — critical failures)")
        print(DIV)
        if metrics["false_negative_cases"]:
            for case in metrics["false_negative_cases"]:
                print(f"  {case['image']:30s}  profile={case['profile']:20s}  expected={case['expected']}  got={case['got']}")
        else:
            print("  None — all dangerous products were caught ✅")

        print(f"\n🔔  OVER-ALERTS  (False Positives)")
        print(DIV)
        if metrics["false_positive_cases"]:
            for case in metrics["false_positive_cases"]:
                print(f"  {case['image']:30s}  profile={case['profile']:20s}  expected={case['expected']}  got={case['got']}")
        else:
            print("  None — no false alarms ✅")

        print(f"\n👤  PER-PROFILE ACCURACY")
        print(DIV)
        for pid, pm in metrics["profile_metrics"].items():
            print(
                f"  {pid:22s}  acc={pm['accuracy']:.1%}  "
                f"P={pm['precision']:.1%}  R={pm['recall']:.1%}  "
                f"F1={pm['f1']:.1%}  3-cls={pm['exact_3class_accuracy']:.1%}"
            )

        print(f"\n🖼  IMAGE PERFORMANCE")
        print(DIV)
        sorted_imgs = sorted(metrics["image_metrics"].items(), key=lambda x: x[1]["binary_accuracy"])
        for img, im in sorted_imgs:
            bar = "█" * int(im["binary_accuracy"] * 10)
            print(
                f"  {img:35s}  {im['binary_accuracy']:.0%}  {bar}  "
                f"({im['binary_correct']}/{im['tests']})"
            )

        # Save results
        os.makedirs(RESULTS_DIR, exist_ok=True)
        metrics_path = os.path.join(RESULTS_DIR, "accuracy_metrics.json")
        details_path = os.path.join(RESULTS_DIR, "detailed_results.json")

        with open(metrics_path, "w") as f:
            json.dump(metrics, f, indent=2)

        serialisable = []
        for r in self.results:
            row = dict(r)
            row["profile_allergies"] = list(row.get("profile_allergies", []))
            row["profile_dietary"] = list(row.get("profile_dietary", []))
            serialisable.append(row)
        with open(details_path, "w") as f:
            json.dump(serialisable, f, indent=2, default=str)

        print(f"\n✓  Results saved → {RESULTS_DIR}/")
        print(f"   • {metrics_path}")
        print(f"   • {details_path}")
        print(f"\n{SEP}")


# ── Entry point ────────────────────────────────────────────────────────────────

def _preflight():
    """Check everything is in place before running tests."""
    ok = True

    # Flask running?
    try:
        requests.get(f"{API_URL}/", timeout=10)
        print("✓ Flask API is running")
    except requests.exceptions.ConnectionError:
        print("✗ Flask API is NOT running  →  python app.py  in another terminal")
        ok = False

    # Test endpoint available?
    if ok:
        try:
            r = requests.post(
                f"{API_URL}/test/analyze",
                json={"ingredients_text": "water", "allergies": [], "dietary_restrictions": []},
                timeout=10,
            )
            if r.status_code == 200:
                print("✓ /test/analyze endpoint OK")
            else:
                print(f"✗ /test/analyze returned HTTP {r.status_code}")
                ok = False
        except Exception as e:
            print(f"✗ /test/analyze error: {e}")
            ok = False

    # Ground truth
    if os.path.exists(GROUND_TRUTH_PATH):
        print(f"✓ Ground truth found  ({GROUND_TRUTH_PATH})")
    else:
        print(f"✗ Ground truth missing  →  {GROUND_TRUTH_PATH}")
        ok = False

    # Profiles
    if os.path.exists(PROFILES_PATH):
        print(f"✓ Test profiles found  ({PROFILES_PATH})")
    else:
        print(f"✗ Test profiles missing  →  {PROFILES_PATH}")
        ok = False

    # Images
    if os.path.exists(IMAGES_DIR):
        imgs = [f for f in os.listdir(IMAGES_DIR) if f.lower().endswith((".jpg", ".jpeg", ".png", ".webp"))]
        print(f"✓ {len(imgs)} images in {IMAGES_DIR}")
        if len(imgs) < 5:
            print(f"⚠ Only {len(imgs)} images found — add more for a meaningful evaluation.")
    else:
        print(f"✗ Images directory missing  →  {IMAGES_DIR}")
        ok = False

    return ok


if __name__ == "__main__":
    print("=" * 65)
    print("BITERIGHT ACCURACY TEST SUITE")
    print("=" * 65)

    if not _preflight():
        print("\n❌ Pre-flight checks failed. Fix the issues above and retry.")
        raise SystemExit(1)

    tester = AccuracyTester(api_url=API_URL)
    results = tester.run_all_tests()

    if results is not None:
        metrics = tester.calculate_metrics()
        if metrics:
            tester.print_report(metrics)
            print("\n✅  Testing complete!")
            print("    Run  python analyze_results.py  for deeper analysis.")
        else:
            print("\n⚠ Tests ran but metrics could not be calculated (check for 0 successful tests).")
    else:
        print("\n❌ Testing failed — no results generated.")