import ast
import os
import re
import warnings

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics import accuracy_score, classification_report, f1_score, make_scorer, precision_score, recall_score
from sklearn.model_selection import StratifiedKFold, cross_validate, train_test_split

warnings.filterwarnings("ignore")


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_FILES = [
    os.path.join(BASE_DIR, "training_data_balanced.csv"),
    os.path.join(BASE_DIR, "training_data.csv"),
]
MODELS_DIR = os.path.join(BASE_DIR, "models")
MODEL_PATH = os.path.join(MODELS_DIR, "random_forest.pkl")
VECTORIZER_PATH = os.path.join(MODELS_DIR, "vectorizer.pkl")


def preprocess_text(text):
    if pd.isna(text) or text is None:
        return ""
    text = str(text).lower()
    text = re.sub(r"[^a-z0-9\s,;:/()'&-]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def load_training_data():
    for path in DATA_FILES:
        if not os.path.exists(path):
            continue

        df = pd.read_csv(path)
        print(f"Loaded {len(df)} rows from {os.path.basename(path)}")

        if "has_allergens" not in df.columns:
            print(f"Skipping {path}: missing has_allergens column")
            continue

        text_columns = [column for column in ["text", "ingredients", "product_name", "brands", "categories"] if column in df.columns]
        if not text_columns:
            print(f"Skipping {path}: no usable text columns found")
            continue

        df["training_text"] = df[text_columns].fillna("").astype(str).agg(" ".join, axis=1).map(preprocess_text)
        df["has_allergens"] = pd.to_numeric(df["has_allergens"], errors="coerce").fillna(0).astype(int)
        df = df[df["training_text"].str.len() > 0].copy()

        class_counts = df["has_allergens"].value_counts().to_dict()
        print(f"Class distribution: {class_counts}")

        if df["has_allergens"].nunique() >= 2:
            return df

        print(f"Skipping {path}: training requires both positive and negative samples")

    raise FileNotFoundError("No valid training CSV found. Expected training_data_balanced.csv or training_data.csv.")


def build_vectorizer():
    return TfidfVectorizer(
        max_features=5000,
        ngram_range=(1, 3),
        stop_words="english",
    )


def build_model():
    return RandomForestClassifier(
        n_estimators=100,
        max_depth=15,
        min_samples_split=5,
        min_samples_leaf=2,
        random_state=42,
        n_jobs=-1,
    )


def run_cross_validation(model, x, y):
    min_class_count = int(np.bincount(y).min())
    n_splits = min(5, min_class_count)
    if n_splits < 2:
        print("Not enough samples per class for cross-validation.")
        return

    cv = StratifiedKFold(n_splits=n_splits, shuffle=True, random_state=42)
    scoring = {
        "accuracy": "accuracy",
        "precision": make_scorer(precision_score, zero_division=0),
        "recall": make_scorer(recall_score, zero_division=0),
        "f1": make_scorer(f1_score, zero_division=0),
    }
    scores = cross_validate(model, x, y, cv=cv, scoring=scoring)

    print(f"\n{n_splits}-fold cross-validation:")
    for metric in scoring:
        values = scores[f"test_{metric}"]
        print(f"  {metric}: {values.mean():.4f} (+/- {values.std() * 2:.4f})")


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


def main():
    print("=" * 60)
    print("BiteRight Random Forest Training")
    print("=" * 60)

    df = load_training_data()
    vectorizer = build_vectorizer()
    model = build_model()

    x = vectorizer.fit_transform(df["training_text"])
    y = df["has_allergens"].values

    run_cross_validation(model, x, y)

    x_train, x_test, y_train, y_test = train_test_split(
        x,
        y,
        test_size=0.2,
        random_state=42,
        stratify=y,
    )
    model.fit(x_train, y_train)
    y_pred = model.predict(x_test)

    print("\nHoldout performance:")
    print(f"  accuracy: {accuracy_score(y_test, y_pred):.4f}")
    print(classification_report(y_test, y_pred, target_names=["No Allergens", "Has Allergens"], zero_division=0))

    os.makedirs(MODELS_DIR, exist_ok=True)
    joblib.dump(model, MODEL_PATH)
    joblib.dump(vectorizer, VECTORIZER_PATH)
    print(f"Saved model: {MODEL_PATH}")
    print(f"Saved vectorizer: {VECTORIZER_PATH}")

    if "allergens" in df.columns:
        allergens = sorted({item for value in df["allergens"] for item in parse_allergens(value)})
        print(f"\nAllergen labels present in training data: {', '.join(allergens[:25])}")


if __name__ == "__main__":
    main()
