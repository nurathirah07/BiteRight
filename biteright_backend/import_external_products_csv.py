"""
Import an external food ingredients/allergens CSV into Firestore.

Default mode is a dry run. Use --apply to write to openfoodfacts_products.
The importer uses deterministic document IDs, so duplicate CSV rows update the
same product document instead of creating duplicates.
"""

import argparse
import csv
import hashlib
import os
import re


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SERVICE_ACCOUNT_PATH = os.path.join(BASE_DIR, "serviceAccountKey.json")
DEFAULT_CSV_PATH = r"C:\Users\Nur\Downloads\food_ingredients_and_allergens.csv"
TARGET_COLLECTION = "openfoodfacts_products"


def initialize_firestore():
    import firebase_admin
    from firebase_admin import credentials, firestore

    if not firebase_admin._apps:
        cred = credentials.Certificate(SERVICE_ACCOUNT_PATH)
        firebase_admin.initialize_app(cred)
    return firestore.client()


def server_timestamp():
    try:
        from firebase_admin import firestore

        return firestore.SERVER_TIMESTAMP
    except ImportError:
        return "__SERVER_TIMESTAMP__"


def normalize_text(value):
    return str(value or "").strip()


def normalize_key(value):
    key = normalize_text(value).lower()
    key = re.sub(r"[^a-z0-9]+", "_", key)
    return key.strip("_") or "unknown"


def split_allergens(value):
    allergens = []
    for item in normalize_text(value).split(","):
        item = item.strip()
        if item and item.lower() not in {"none", "n/a", "na", "unknown"}:
            allergens.append(item)
    return list(dict.fromkeys(allergens))


def collect_ingredients(row):
    ingredient_fields = ["Main Ingredient", "Sweetener", "Fat/Oil", "Seasoning"]
    ingredients = []
    for field in ingredient_fields:
        value = normalize_text(row.get(field))
        if value and value.lower() not in {"none", "n/a", "na", "unknown"}:
            ingredients.append(value)
    return list(dict.fromkeys(ingredients))


def build_document_id(product_name, ingredients):
    digest_source = "|".join([product_name.lower(), *[item.lower() for item in ingredients]])
    digest = hashlib.sha1(digest_source.encode("utf-8")).hexdigest()[:12]
    return f"external_csv_{normalize_key(product_name)}_{digest}"


def build_product_document(row):
    product_name = normalize_text(row.get("Food Product")) or "Unknown Product"
    ingredients = collect_ingredients(row)
    allergens = split_allergens(row.get("Allergens"))
    prediction = normalize_text(row.get("Prediction"))
    doc_id = build_document_id(product_name, ingredients)

    return doc_id, {
        "barcode": doc_id,
        "external_id": doc_id,
        "source": "food_ingredients_and_allergens_csv",
        "product_name": product_name,
        "brands": "External CSV",
        "categories": "External food ingredients dataset",
        "ingredients": ingredients,
        "ingredients_text": ", ".join(ingredients),
        "main_ingredient": normalize_text(row.get("Main Ingredient")),
        "sweetener": normalize_text(row.get("Sweetener")),
        "fat_oil": normalize_text(row.get("Fat/Oil")),
        "seasoning": normalize_text(row.get("Seasoning")),
        "allergens": allergens,
        "traces": [],
        "has_allergens": bool(allergens) or prediction.lower() == "contains",
        "prediction": prediction,
        "updated_at": server_timestamp(),
    }


def commit_batch(db, batch, pending_count, apply_changes):
    if pending_count and apply_changes:
        batch.commit()
    return db.batch(), 0


def import_csv(csv_path, apply_changes):
    if not os.path.exists(csv_path):
        raise FileNotFoundError(f"CSV file not found: {csv_path}")

    db = initialize_firestore() if apply_changes else None
    batch = db.batch() if apply_changes else None
    pending_count = 0
    total_rows = 0
    unique_docs = set()

    with open(csv_path, newline="", encoding="utf-8-sig") as csv_file:
        reader = csv.DictReader(csv_file)
        required_columns = {"Food Product", "Main Ingredient", "Sweetener", "Fat/Oil", "Seasoning", "Allergens", "Prediction"}
        missing_columns = required_columns.difference(reader.fieldnames or [])
        if missing_columns:
            raise ValueError(f"CSV is missing required columns: {sorted(missing_columns)}")

        for row in reader:
            total_rows += 1
            doc_id, product_doc = build_product_document(row)
            unique_docs.add(doc_id)

            if apply_changes:
                doc_ref = db.collection(TARGET_COLLECTION).document(doc_id)
                batch.set(doc_ref, product_doc, merge=True)
                pending_count += 1

                if pending_count >= 450:
                    batch, pending_count = commit_batch(db, batch, pending_count, apply_changes)

    if apply_changes:
        commit_batch(db, batch, pending_count, apply_changes)

    action = "Imported" if apply_changes else "Would import"
    print(f"{action} {len(unique_docs)} unique products from {total_rows} CSV rows into {TARGET_COLLECTION}")
    if total_rows != len(unique_docs):
        print(f"Skipped duplicate writes by reusing deterministic IDs for {total_rows - len(unique_docs)} duplicate rows")


def main():
    parser = argparse.ArgumentParser(description="Import an external product/allergen CSV into Firestore.")
    parser.add_argument("--csv", default=DEFAULT_CSV_PATH, help="Path to food_ingredients_and_allergens.csv")
    parser.add_argument("--apply", action="store_true", help="Write changes to Firestore. Omit for dry run.")
    args = parser.parse_args()

    print(f"Running in {'APPLY' if args.apply else 'DRY RUN'} mode")
    import_csv(args.csv, args.apply)
    if not args.apply:
        print("Dry run complete. Run again with --apply to write to Firebase.")


if __name__ == "__main__":
    main()
