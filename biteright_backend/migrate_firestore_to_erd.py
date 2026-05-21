"""
Copy existing Firestore data into the ERD-aligned collection structure.

Default mode is a dry run. Use --apply to write changes.
This script does not delete old collections.
"""

import argparse
import os

import firebase_admin
from firebase_admin import credentials, firestore


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SERVICE_ACCOUNT_PATH = os.path.join(BASE_DIR, "serviceAccountKey.json")

SCAN_HISTORY_COLLECTION = "scan_history"
LEGACY_SCANS_COLLECTION = "scans"
MASTER_ALLERGENS_COLLECTION = "master_allergens"
LEGACY_ALLERGENS_COLLECTION = "allergens"
DIETARY_RESTRICTIONS_COLLECTION = "dietary_restrictions"


def initialize_firestore():
    if not firebase_admin._apps:
        cred = credentials.Certificate(SERVICE_ACCOUNT_PATH)
        firebase_admin.initialize_app(cred)
    return firestore.client()


def commit_batch(db, batch, pending_count, apply_changes):
    if pending_count and apply_changes:
        batch.commit()
    return db.batch(), 0


def migrate_allergens(db, apply_changes):
    batch = db.batch()
    pending_count = 0
    total = 0

    for doc in db.collection(LEGACY_ALLERGENS_COLLECTION).stream():
        data = doc.to_dict() or {}
        standard_name = str(data.get("standard_name") or doc.id).strip()
        allergen_keyword = standard_name.lower().replace("-", "_").replace(" ", "_")

        erd_data = {
            "allergen_keyword": allergen_keyword,
            "standard_name": standard_name,
            "category": data.get("category", ""),
            "synonym_list": data.get("synonym_list", data.get("synonyms", [])),
            "severity": data.get("severity", ""),
            "updated_at": firestore.SERVER_TIMESTAMP,
        }

        target = db.collection(MASTER_ALLERGENS_COLLECTION).document(allergen_keyword)
        batch.set(target, erd_data, merge=True)
        pending_count += 1
        total += 1

        if pending_count >= 450:
            batch, pending_count = commit_batch(db, batch, pending_count, apply_changes)

    commit_batch(db, batch, pending_count, apply_changes)
    print(f"{'Copied' if apply_changes else 'Would copy'} {total} allergens to {MASTER_ALLERGENS_COLLECTION}")


def migrate_scans(db, apply_changes):
    batch = db.batch()
    pending_count = 0
    total = 0

    for doc in db.collection(LEGACY_SCANS_COLLECTION).stream():
        data = doc.to_dict() or {}
        target = db.collection(SCAN_HISTORY_COLLECTION).document(doc.id)

        risk_level = data.get("risk_level", data.get("safety_classification", "unknown"))
        scan_date = data.get("scan_date") or data.get("scanned_at") or data.get("timestamp") or firestore.SERVER_TIMESTAMP

        erd_data = dict(data)
        erd_data.update({
            "scan_id": doc.id,
            "user_id": data.get("user_id", ""),
            "scan_date": scan_date,
            "input_image_url": data.get("input_image_url", data.get("image_url", "")),
            "safety_classification": data.get("safety_classification", risk_level),
        })

        # Keep app-compatible aliases during transition.
        erd_data.setdefault("scanned_at", scan_date)
        erd_data.setdefault("timestamp", scan_date)
        erd_data.setdefault("risk_level", risk_level)

        batch.set(target, erd_data, merge=True)
        pending_count += 1
        total += 1

        if pending_count >= 450:
            batch, pending_count = commit_batch(db, batch, pending_count, apply_changes)

    commit_batch(db, batch, pending_count, apply_changes)
    print(f"{'Copied' if apply_changes else 'Would copy'} {total} scans to {SCAN_HISTORY_COLLECTION}")


def migrate_user_restrictions(db, apply_changes):
    batch = db.batch()
    pending_count = 0
    total = 0

    for user_doc in db.collection("users").stream():
        user_data = user_doc.to_dict() or {}
        user_id = user_doc.id

        restriction_sources = [
            ("allergy", user_data.get("allergies", [])),
            ("dietary", user_data.get("dietary_restrictions", [])),
        ]

        for restriction_type, restrictions in restriction_sources:
            if not isinstance(restrictions, list):
                continue

            for restriction in restrictions:
                if isinstance(restriction, dict):
                    restriction_name = restriction.get("id") or restriction.get("name")
                    status = restriction.get("status", "active")
                else:
                    restriction_name = str(restriction)
                    status = "active"

                if not restriction_name:
                    continue

                restriction_key = str(restriction_name).lower().replace("-", "_").replace(" ", "_")
                doc_id = f"{user_id}_{restriction_type}_{restriction_key}"
                target = db.collection(DIETARY_RESTRICTIONS_COLLECTION).document(doc_id)

                batch.set(target, {
                    "restriction_id": doc_id,
                    "user_id": user_id,
                    "restriction_name": restriction_name,
                    "restriction_type": restriction_type,
                    "status": status,
                    "updated_at": firestore.SERVER_TIMESTAMP,
                }, merge=True)

                pending_count += 1
                total += 1

                if pending_count >= 450:
                    batch, pending_count = commit_batch(db, batch, pending_count, apply_changes)

    commit_batch(db, batch, pending_count, apply_changes)
    print(f"{'Copied' if apply_changes else 'Would copy'} {total} restrictions to {DIETARY_RESTRICTIONS_COLLECTION}")


def main():
    parser = argparse.ArgumentParser(description="Migrate Firestore data to ERD-aligned collections.")
    parser.add_argument("--apply", action="store_true", help="Write changes to Firestore. Omit for dry run.")
    args = parser.parse_args()

    db = initialize_firestore()
    mode = "APPLY" if args.apply else "DRY RUN"
    print(f"Running Firestore ERD migration in {mode} mode")

    migrate_allergens(db, args.apply)
    migrate_scans(db, args.apply)
    migrate_user_restrictions(db, args.apply)

    if not args.apply:
        print("Dry run complete. Run again with --apply to write these changes.")
    else:
        print("Migration complete. Old collections were not deleted.")


if __name__ == "__main__":
    main()
