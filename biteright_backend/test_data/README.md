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
