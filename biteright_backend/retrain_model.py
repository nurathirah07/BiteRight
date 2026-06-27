# biteright_backend/retrain_model.py
"""
Retrain Random Forest model with balanced data
"""

import pandas as pd
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split, cross_val_score
from sklearn.metrics import classification_report, confusion_matrix, accuracy_score
import joblib
import os
import re

def preprocess_text(text):
    """Clean and normalize text"""
    if pd.isna(text):
        return ""
    text = str(text).lower()
    text = re.sub(r'[^a-z\s]', ' ', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text

def train_model():
    """Train Random Forest model on balanced data"""
    
    # Load training data
    df = pd.read_csv('training_data_balanced.csv')
    print(f"Loaded {len(df)} training samples")
    print(f"Positive (has allergens): {df['has_allergens'].sum()}")
    print(f"Negative (no allergens): {len(df) - df['has_allergens'].sum()}")
    
    # Preprocess text
    df['processed_text'] = df['text'].apply(preprocess_text)
    
    # Vectorize text
    vectorizer = TfidfVectorizer(
        max_features=3000,
        ngram_range=(1, 2),  # Unigrams and bigrams
        stop_words='english',
        min_df=2,
        max_df=0.8
    )
    
    X = vectorizer.fit_transform(df['processed_text'])
    y = df['has_allergens'].values
    
    print(f"\nFeature matrix shape: {X.shape}")
    
    # Split data
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )
    
    # Train Random Forest
    model = RandomForestClassifier(
        n_estimators=100,
        max_depth=10,
        min_samples_split=5,
        min_samples_leaf=2,
        random_state=42,
        class_weight='balanced'  # Important for imbalanced data
    )
    
    model.fit(X_train, y_train)
    
    # Evaluate
    y_pred = model.predict(X_test)
    accuracy = accuracy_score(y_test, y_pred)
    
    print(f"\nModel Performance:")
    print(f"  Accuracy: {accuracy:.4f}")
    print(f"\nClassification Report:")
    print(classification_report(y_test, y_pred, target_names=['No Allergens', 'Has Allergens']))
    
    # Cross-validation
    cv_scores = cross_val_score(model, X, y, cv=5)
    print(f"\nCross-validation accuracy: {cv_scores.mean():.4f} (+/- {cv_scores.std() * 2:.4f})")
    
    # Save model and vectorizer
    os.makedirs('models', exist_ok=True)
    joblib.dump(model, 'models/random_forest.pkl')
    joblib.dump(vectorizer, 'models/vectorizer.pkl')
    
    print("\n✓ Model saved to models/random_forest.pkl")
    print("✓ Vectorizer saved to models/vectorizer.pkl")
    
    # Test on safe products
    print("\n" + "="*50)
    print("TESTING ON SAFE PRODUCTS (Should predict NO allergens)")
    print("="*50)
    
    safe_test = [
        "rice",
        "salt", 
        "white sugar",
        "olive oil",
        "water"
    ]
    
    for text in safe_test:
        processed = preprocess_text(text)
        vec = vectorizer.transform([processed])
        pred = model.predict(vec)[0]
        prob = model.predict_proba(vec)[0]
        
        status = "❌ UNSAFE (False Positive!)" if pred == 1 else "✅ SAFE"
        print(f"  '{text}': {status} (confidence: {max(prob):.2%})")
    
    # Test on unsafe products
    print("\n" + "="*50)
    print("TESTING ON UNSAFE PRODUCTS (Should predict HAS allergens)")
    print("="*50)
    
    unsafe_test = [
        "peanuts, sugar, salt",
        "wheat flour, water, yeast",
        "milk, cream, sugar",
        "soy sauce, soybeans, wheat",
        "eggs, milk, flour"
    ]
    
    for text in unsafe_test:
        processed = preprocess_text(text)
        vec = vectorizer.transform([processed])
        pred = model.predict(vec)[0]
        prob = model.predict_proba(vec)[0]
        
        status = "✅ UNSAFE" if pred == 1 else "❌ SAFE (False Negative!)"
        print(f"  '{text}': {status} (confidence: {max(prob):.2%})")
    
    return model, vectorizer

if __name__ == "__main__":
    train_model()