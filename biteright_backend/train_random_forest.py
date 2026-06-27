"""
Train Random Forest model for ingredient allergen detection
"""

import pandas as pd
import numpy as np
from sklearn.model_selection import train_test_split, cross_val_score
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import classification_report, confusion_matrix, accuracy_score
import joblib
import os

def train_random_forest():
    print("="*60)
    print("Training Random Forest Classifier")
    print("="*60)
    
    # Load data
    df = pd.read_csv('training_data_balanced.csv')
    
    # Create text feature if needed
    if 'text' not in df.columns:
        df['text'] = df['product_name'].fillna('') + ' ' + \
                    df['brands'].fillna('') + ' ' + \
                    df['categories'].fillna('')
    
    # Clean text
    df['text'] = df['text'].str.lower()
    df['text'] = df['text'].str.replace(r'[^a-zA-Z\s]', ' ', regex=True)
    df['text'] = df['text'].str.replace(r'\s+', ' ', regex=True).str.strip()
    
    # Prepare data
    X = df['text'].fillna('')
    y = df['has_allergens'].values
    
    print(f"Total samples: {len(X)}")
    print(f"Positive: {sum(y)}, Negative: {len(y) - sum(y)}")
    
    # Split data
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )
    
    # Vectorize
    vectorizer = TfidfVectorizer(
        max_features=5000,
        ngram_range=(1, 3),
        stop_words='english',
        min_df=2,
        max_df=0.95
    )
    
    X_train_vec = vectorizer.fit_transform(X_train)
    X_test_vec = vectorizer.transform(X_test)
    
    print(f"Feature matrix: {X_train_vec.shape}")
    
    # Train Random Forest
    model = RandomForestClassifier(
        n_estimators=100,
        max_depth=15,
        min_samples_split=5,
        min_samples_leaf=2,
        class_weight='balanced',
        random_state=42,
        n_jobs=-1
    )
    
    model.fit(X_train_vec, y_train)
    
    # Evaluate
    y_pred = model.predict(X_test_vec)
    accuracy = accuracy_score(y_test, y_pred)
    
    print(f"\nAccuracy: {accuracy:.4f}")
    print(f"Number of Trees: {model.n_estimators}")
    print(f"Max Depth: {model.max_depth}")
    print("\nClassification Report:")
    print(classification_report(y_test, y_pred, target_names=['Safe', 'Has Allergens']))
    
    # Cross-validation
    cv_scores = cross_val_score(model, X_train_vec, y_train, cv=5)
    print(f"\nCV Accuracy: {cv_scores.mean():.4f} (+/- {cv_scores.std()*2:.4f})")
    
    # Save model
    os.makedirs('models', exist_ok=True)
    joblib.dump(model, 'models/random_forest.pkl')
    joblib.dump(vectorizer, 'models/vectorizer.pkl')
    
    print("\nOK: Model saved to models/random_forest.pkl")
    print("OK: Vectorizer saved to models/vectorizer.pkl")
    
    return model, accuracy

if __name__ == "__main__":
    train_random_forest()
