"""
setup_test_data.py
==================
Run this ONCE before test_accuracy.py.
Creates all required folders and template files you need to fill in.

Usage:
    python setup_test_data.py
"""

import os
import csv
import json

# ── Config ─────────────────────────────────────────────────────────────────────

PROFILE_IDS = [
    "no_allergens",
    "peanut_allergy",
    "milk_wheat",
    "vegan",
    "multi_allergy",
]

# 20 placeholder image filenames — replace with your actual filenames
IMAGE_SLOTS = [f"product_{i:02d}.jpg" for i in range(1, 21)]

# ── Create folders ─────────────────────────────────────────────────────────────

def create_dirs():
    for d in ("test_data", "test_data/images", "test_results"):
        os.makedirs(d, exist_ok=True)
        print(f"✓ {d}/")


# ── Write test_profiles.json ───────────────────────────────────────────────────
#
# Each profile maps directly to what /test/analyze expects:
#   allergies            → list of allergen IDs matching ALLERGEN_OPTIONS in dietary_options.py
#   dietary_restrictions → list of dietary IDs matching DIETARY_OPTIONS
#
# Valid allergen IDs: peanuts, tree_nuts, milk, eggs, soy, wheat, gluten,
#                    fish, shellfish, sesame
# Valid dietary IDs:  halal, vegetarian, vegan, keto, diabetic, low_sodium

def write_profiles():
    profiles = [
        {
            "profile_id": "no_allergens",
            "name": "No Allergies (Control)",
            "description": "Baseline — no restrictions. All products should be safe.",
            "allergies": [],
            "dietary_restrictions": [],
        },
        {
            "profile_id": "peanut_allergy",
            "name": "Peanut Allergy",
            "description": "High-severity peanut allergy only.",
            "allergies": [{"id": "peanuts", "severity": "high"}],
            "dietary_restrictions": [],
        },
        {
            "profile_id": "milk_wheat",
            "name": "Milk + Wheat Allergy",
            "description": "Common combination — covers many baked goods and dairy.",
            "allergies": [
                {"id": "milk", "severity": "high"},
                {"id": "wheat", "severity": "medium"},
            ],
            "dietary_restrictions": [],
        },
        {
            "profile_id": "vegan",
            "name": "Vegan Diet",
            "description": "No animal products — dietary restriction only, no allergies.",
            "allergies": [],
            "dietary_restrictions": ["vegan"],
        },
        {
            "profile_id": "multi_allergy",
            "name": "Multi-Allergen (Peanut + Soy + Wheat + Tree Nuts)",
            "description": "Broad restriction — should flag most processed foods.",
            "allergies": [
                {"id": "peanuts", "severity": "high"},
                {"id": "soy", "severity": "medium"},
                {"id": "wheat", "severity": "medium"},
                {"id": "tree_nuts", "severity": "high"},
            ],
            "dietary_restrictions": [],
        },
    ]

    path = "test_data/test_profiles.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(profiles, f, indent=2)
    print(f"✓ {path}  ({len(profiles)} profiles)")


# ── Write ground_truth.csv ─────────────────────────────────────────────────────
#
# Column guide:
#   image_filename         → exact filename in test_data/images/
#   product_name           → human-readable name (for your reference only)
#   known_allergens        → comma-separated allergens declared on the label
#
# For each profile_id:
#   expected_risk_<pid>       → safe | caution | unsafe
#   expected_risk_score_<pid> → 0-100  (new scale: 0=safest, 60-100=dangerous)
#
# Risk score guidance (must match the backend's _to_risk_score logic):
#   No personal allergen match  →  0-25   (safe)
#   Cross-contact / dietary     →  30-59  (caution)
#   Low-severity allergen match →  60-64  (unsafe)
#   Medium-severity match       →  65-84  (unsafe)
#   High-severity match         →  85-100 (unsafe)
#   Multiple personal matches   →  +5 per extra allergen, capped at 100

def write_ground_truth():
    fieldnames = ["image_filename", "product_name", "known_allergens"]
    for pid in PROFILE_IDS:
        fieldnames += [f"expected_risk_{pid}", f"expected_risk_score_{pid}"]

    path = "test_data/ground_truth.csv"

    # Only write if the file does not already exist — never overwrite real data
    if os.path.exists(path):
        print(f"⚠ {path} already exists — NOT overwritten. Edit manually.")
        return

    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()

        # Write one placeholder row per image slot
        for img in IMAGE_SLOTS:
            row: dict = {
                "image_filename": img,
                "product_name": "",         # ← fill in
                "known_allergens": "",       # ← fill in (e.g. "milk, wheat")
            }
            for pid in PROFILE_IDS:
                row[f"expected_risk_{pid}"] = "safe"   # ← fill in
                row[f"expected_risk_score_{pid}"] = 0  # ← fill in
            writer.writerow(row)

    print(f"✓ {path}  (template with {len(IMAGE_SLOTS)} rows — fill in before testing)")


# ── Write a README ─────────────────────────────────────────────────────────────

README = """\
# BiteRight Test Data

## Folder structure

    test_data/
    ├── images/               ← Put your product photos here (jpg/jpeg/png/webp)
    ├── ground_truth.csv      ← One row per image — fill this in manually
    └── test_profiles.json    ← Allergy profiles (auto-generated, edit as needed)

    test_results/             ← Created automatically when tests run
    ├── accuracy_metrics.json
    └── detailed_results.json

## ground_truth.csv columns

| Column | Description |
|--------|-------------|
| image_filename | Exact filename inside images/ |
| product_name | Human-readable name |
| known_allergens | Comma-separated allergens on label |
| expected_risk_<profile> | safe / caution / unsafe |
| expected_risk_score_<profile> | 0–100  (0 = completely safe, 60-100 = dangerous) |

## Risk score scale (new system — higher means MORE dangerous)

| Score | Meaning |
|-------|---------|
| 0 | Completely safe — no allergens at all |
| 1–25 | Safe — general allergens present but none match your profile |
| 30–59 | Caution — cross-contact warning or dietary violation |
| 60–64 | Unsafe — low-severity personal allergen |
| 65–84 | Unsafe — medium-severity (e.g. soy, wheat) |
| 85–100 | Unsafe — high-severity (e.g. peanuts, shellfish) |

## How to run

    # 1. Fill in ground_truth.csv and add images
    # 2. Start the backend
    python app.py

    # 3. In another terminal, run tests
    python test_accuracy.py
"""

def write_readme():
    path = "test_data/README.md"
    with open(path, "w", encoding="utf-8") as f:
        f.write(README)
    print(f"✓ {path}")


# ── Entry point ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 55)
    print("BITERIGHT TEST DATA SETUP")
    print("=" * 55)

    create_dirs()
    write_profiles()
    write_ground_truth()
    write_readme()

    print("\n✅  Setup complete! Next steps:")
    print("   1. Add product images  →  test_data/images/")
    print("   2. Fill in            →  test_data/ground_truth.csv")
    print("      (rename image_filename columns to match your actual files)")
    print("   3. Edit if needed     →  test_data/test_profiles.json")
    print("   4. Start Flask:        python app.py")
    print("   5. Run tests:          python test_accuracy.py")
