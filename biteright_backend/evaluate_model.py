import ast
import os
import re
from datetime import datetime

import joblib
import pandas as pd
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix, f1_score, precision_score, recall_score
from sklearn.model_selection import train_test_split


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_FILES = [
    os.path.join(BASE_DIR, "training_data_balanced.csv"),
    os.path.join(BASE_DIR, "training_data.csv"),
]
MODEL_PATH = os.path.join(BASE_DIR, "models", "random_forest.pkl")
VECTORIZER_PATH = os.path.join(BASE_DIR, "models", "vectorizer.pkl")
REPORT_PATH = os.path.join(BASE_DIR, "models", "random_forest_evaluation_report.txt")


def preprocess_text(text):
    if pd.isna(text) or text is None:
        return ""
    text = str(text).lower()
    text = re.sub(r"[^a-z0-9\s,;:/()'&-]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def parse_allergens(value):
    empty_labels = {"", "[]", "none", "nan", "null"}
    if pd.isna(value):
        return []
    try:
        parsed = ast.literal_eval(str(value))
        if isinstance(parsed, list):
            return [
                str(item).strip().lower()
                for item in parsed
                if str(item).strip().lower() not in empty_labels
            ]
    except (SyntaxError, ValueError):
        pass
    return [
        item.strip().lower()
        for item in re.split(r"[,;|]", str(value))
        if item.strip().lower() not in empty_labels
    ]


def load_data():
    for path in DATA_FILES:
        if not os.path.exists(path):
            continue
        df = pd.read_csv(path)
        if "has_allergens" not in df.columns:
            continue

        text_columns = [column for column in ["text", "ingredients", "product_name", "brands", "categories"] if column in df.columns]
        if not text_columns:
            continue

        df["training_text"] = df[text_columns].fillna("").astype(str).agg(" ".join, axis=1).map(preprocess_text)
        df["has_allergens"] = pd.to_numeric(df["has_allergens"], errors="coerce").fillna(0).astype(int)
        df = df[df["training_text"].str.len() > 0].copy()
        if df["has_allergens"].nunique() >= 2:
            print(f"Loaded {len(df)} rows from {os.path.basename(path)}")
            return df

    raise FileNotFoundError("No valid evaluation CSV found.")


def per_allergen_performance(test_df, y_pred):
    if "allergens" not in test_df.columns:
        return []

    rows = []
    test_df = test_df.copy()
    test_df["parsed_allergens"] = test_df["allergens"].map(parse_allergens)
    allergen_names = sorted({name for names in test_df["parsed_allergens"] for name in names})

    for allergen in allergen_names:
        mask = test_df["parsed_allergens"].map(lambda names: allergen in names)
        support = int(mask.sum())
        if support == 0:
            continue
        predicted_positive = pd.Series(y_pred, index=test_df.index).astype(int)
        detected = int(predicted_positive[mask].sum())
        missed = support - detected
        rows.append({
            "allergen": allergen,
            "support": support,
            "detected_by_binary_model": detected,
            "missed_by_binary_model": missed,
            "recall_on_allergen_rows": detected / support,
        })

    return rows


def main():
    print("=" * 60)
    print("BiteRight Random Forest Evaluation")
    print("=" * 60)

    if not os.path.exists(MODEL_PATH) or not os.path.exists(VECTORIZER_PATH):
        raise FileNotFoundError("Model files missing. Run train_random_forest.py first.")

    model = joblib.load(MODEL_PATH)
    vectorizer = joblib.load(VECTORIZER_PATH)
    df = load_data()

    train_df, test_df = train_test_split(
        df,
        test_size=0.2,
        random_state=42,
        stratify=df["has_allergens"],
    )
    x_test = vectorizer.transform(test_df["training_text"])
    y_test = test_df["has_allergens"].values
    y_pred = model.predict(x_test)

    cm = confusion_matrix(y_test, y_pred)
    metrics = {
        "accuracy": accuracy_score(y_test, y_pred),
        "precision": precision_score(y_test, y_pred, zero_division=0),
        "recall": recall_score(y_test, y_pred, zero_division=0),
        "f1": f1_score(y_test, y_pred, zero_division=0),
    }
    per_allergen = per_allergen_performance(test_df, y_pred)

    lines = [
        "BiteRight Random Forest Evaluation Report",
        f"Generated: {datetime.now().isoformat(timespec='seconds')}",
        f"Rows: train={len(train_df)}, test={len(test_df)}",
        "",
        "Overall Metrics:",
        *[f"  {name}: {value:.4f}" for name, value in metrics.items()],
        "",
        "Confusion Matrix:",
        "  [[true_negative, false_positive],",
        "   [false_negative, true_positive]]",
        f"  {cm.tolist()}",
        "",
        "Classification Report:",
        classification_report(y_test, y_pred, target_names=["No Allergens", "Has Allergens"], zero_division=0),
        "",
        "Per-Allergen Performance:",
        "  Note: the current Random Forest is a binary allergen detector, so per-allergen rows report",
        "  whether products containing each allergen were classified as allergen-positive.",
    ]

    if per_allergen:
        for row in per_allergen:
            lines.append(
                "  {allergen}: support={support}, detected={detected_by_binary_model}, "
                "missed={missed_by_binary_model}, recall={recall_on_allergen_rows:.4f}".format(**row)
            )
    else:
        lines.append("  No allergen label column found.")

    report = "\n".join(lines)
    print(report)

    os.makedirs(os.path.dirname(REPORT_PATH), exist_ok=True)
    with open(REPORT_PATH, "w", encoding="utf-8") as file:
        file.write(report + "\n")
    print(f"\nSaved report: {REPORT_PATH}")


if __name__ == "__main__":
    main()
