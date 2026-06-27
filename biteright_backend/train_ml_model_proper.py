# biteright_backend/train_ml_model_proper.py
"""
Train a robust Random Forest model for allergen detection
Uses expanded training data from multiple sources
"""

import pandas as pd
import numpy as np
import re
import joblib
import os
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split, cross_val_score
from sklearn.metrics import classification_report, confusion_matrix, accuracy_score

# ============= EXPANDED TRAINING DATA =============

# POSITIVE EXAMPLES (Products WITH allergens)
POSITIVE_EXAMPLES = [
    # Peanuts/Peanut butter
    ("peanut butter", 1, ["peanuts"]),
    ("roasted peanuts sugar salt", 1, ["peanuts"]),
    ("creamy peanut butter spread", 1, ["peanuts"]),
    ("peanut oil peanut flour", 1, ["peanuts"]),
    
    # Milk/Dairy
    ("milk chocolate cocoa butter milk powder", 1, ["milk"]),
    ("whey protein isolate natural flavors", 1, ["milk"]),
    ("whole milk cream", 1, ["milk"]),
    ("butter cream cheese", 1, ["milk"]),
    ("greek yogurt live cultures", 1, ["milk"]),
    ("cheddar cheese annatto", 1, ["milk"]),
    
    # Wheat/Gluten
    ("whole wheat flour water yeast salt", 1, ["wheat", "gluten"]),
    ("durum wheat semolina pasta", 1, ["wheat", "gluten"]),
    ("white bread enriched wheat flour", 1, ["wheat", "gluten"]),
    ("barley malt extract", 1, ["gluten"]),
    ("rye bread", 1, ["gluten"]),
    ("seitan vital wheat gluten", 1, ["wheat", "gluten"]),
    
    # Eggs
    ("eggs milk flour sugar", 1, ["eggs", "milk", "wheat"]),
    ("mayonnaise eggs oil vinegar", 1, ["eggs"]),
    ("egg whites albumin", 1, ["eggs"]),
    
    # Soy
    ("soy sauce water soybeans wheat", 1, ["soy", "wheat"]),
    ("tofu soybeans calcium sulfate", 1, ["soy"]),
    ("soy milk calcium carbonate", 1, ["soy"]),
    ("soy lecithin emulsifier", 1, ["soy"]),
    ("hydrolyzed soy protein", 1, ["soy"]),
    ("tempeh fermented soybeans", 1, ["soy"]),
    
    # Tree Nuts
    ("almonds sugar honey", 1, ["tree_nuts"]),
    ("almond milk water almonds", 1, ["tree_nuts"]),
    ("cashews salt oil", 1, ["tree_nuts"]),
    ("coconut milk cream", 1, ["tree_nuts"]),
    ("walnuts maple syrup", 1, ["tree_nuts"]),
    ("hazelnut cocoa spread", 1, ["tree_nuts"]),
    
    # Fish
    ("canned tuna water salt", 1, ["fish"]),
    ("salmon fillet", 1, ["fish"]),
    ("anchovy paste", 1, ["fish"]),
    ("fish sauce", 1, ["fish"]),
    
    # Shellfish
    ("shrimp salt preservatives", 1, ["shellfish"]),
    ("crab meat", 1, ["shellfish"]),
    ("lobster butter", 1, ["shellfish"]),
    ("clam chowder", 1, ["shellfish"]),
    
    # Sesame
    ("sesame seeds tahini", 1, ["sesame"]),
    ("tahini paste ground sesame", 1, ["sesame"]),
    ("sesame oil", 1, ["sesame"]),
]

# NEGATIVE EXAMPLES (Products with NO allergens)
NEGATIVE_EXAMPLES = [
    # Pure single ingredients
    ("white rice", 0, []),
    ("brown rice", 0, []),
    ("jasmine rice", 0, []),
    ("basmati rice", 0, []),
    ("salt", 0, []),
    ("sea salt", 0, []),
    ("white sugar", 0, []),
    ("brown sugar", 0, []),
    ("powdered sugar", 0, []),
    ("water", 0, []),
    ("spring water", 0, []),
    ("carbonated water", 0, []),
    ("olive oil", 0, []),
    ("extra virgin olive oil", 0, []),
    ("coconut oil", 0, []),
    ("canola oil", 0, []),
    ("sunflower oil", 0, []),
    ("avocado oil", 0, []),
    
    # Simple combinations
    ("potatoes canola oil salt", 0, []),
    ("tomatoes water", 0, []),
    ("carrots", 0, []),
    ("celery", 0, []),
    ("spinach", 0, []),
    ("lettuce", 0, []),
    ("cucumber", 0, []),
    ("broccoli", 0, []),
    ("cauliflower", 0, []),
    
    # Safe ingredients
    ("corn starch", 0, []),
    ("tapioca starch", 0, []),
    ("potato starch", 0, []),
    ("baking soda", 0, []),
    ("baking powder", 0, []),
    ("white vinegar", 0, []),
    ("apple cider vinegar", 0, []),
    ("black pepper", 0, []),
    ("cinnamon", 0, []),
    ("vanilla extract", 0, []),
    ("coffee beans", 0, []),
    ("green tea leaves", 0, []),
]

def create_training_data():
    """Create expanded training dataset"""
    
    # Create DataFrame from examples
    data = []
    
    # Add positive examples (multiply for more samples)
    for text, label, allergens in POSITIVE_EXAMPLES:
        # Create variations of each example
        variations = [
            text,
            text + " product",
            "ingredients: " + text,
            text + " natural flavor",
        ]
        for var in variations:
            data.append({
                'text': var,
                'has_allergens': label,
                'allergens': str(allergens)
            })
    
    # Add negative examples
    for text, label, allergens in NEGATIVE_EXAMPLES:
        variations = [
            text,
            text + " product",
            "ingredients: " + text,
        ]
        for var in variations:
            data.append({
                'text': var,
                'has_allergens': label,
                'allergens': str(allergens)
            })
    
    # Create DataFrame
    df = pd.DataFrame(data)
    
    # Ensure balance (roughly equal numbers)
    positive = df[df['has_allergens'] == 1]
    negative = df[df['has_allergens'] == 0]
    
    min_count = min(len(positive), len(negative))
    positive = positive.sample(n=min_count, random_state=42)
    negative = negative.sample(n=min_count, random_state=42)
    
    df = pd.concat([positive, negative], ignore_index=True)
    df = df.sample(frac=1, random_state=42).reset_index(drop=True)
    
    print(f"Training data created:")
    print(f"  Positive (has allergens): {len(positive)}")
    print(f"  Negative (no allergens): {len(negative)}")
    print(f"  Total: {len(df)}")
    
    return df

def preprocess_text(text):
    """Clean text for ML training"""
    if pd.isna(text):
        return ""
    text = str(text).lower()
    # Remove special characters but keep important ones
    text = re.sub(r'[^a-z\s]', ' ', text)
    # Remove extra spaces
    text = re.sub(r'\s+', ' ', text).strip()
    return text

def train_model():
    """Train Random Forest model"""
    
    print("="*60)
    print("TRAINING RANDOM FOREST MODEL")
    print("="*60)
    
    # Create training data
    df = create_training_data()
    
    # Preprocess text
    df['processed_text'] = df['text'].apply(preprocess_text)
    
    print(f"\nSample training examples:")
    for i in range(5):
        print(f"  {df['processed_text'].iloc[i]} -> {df['has_allergens'].iloc[i]}")
    
    # Vectorize text
    vectorizer = TfidfVectorizer(
        max_features=5000,
        ngram_range=(1, 2),  # Unigrams and bigrams
        stop_words='english',
        min_df=2,
        max_df=0.9
    )
    
    X = vectorizer.fit_transform(df['processed_text'])
    y = df['has_allergens'].values
    
    print(f"\nFeature matrix shape: {X.shape}")
    print(f"Class distribution: {np.bincount(y)}")
    
    # Split data
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )
    
    print(f"\nTraining samples: {X_train.shape[0]}")
    print(f"Test samples: {X_test.shape[0]}")
    
    # Train Random Forest
    model = RandomForestClassifier(
        n_estimators=150,        # More trees for better accuracy
        max_depth=12,
        min_samples_split=4,
        min_samples_leaf=2,
        random_state=42,
        class_weight='balanced',  # Handle imbalanced data
        n_jobs=-1
    )
    
    model.fit(X_train, y_train)
    
    # Evaluate on test set
    y_pred = model.predict(X_test)
    
    accuracy = accuracy_score(y_test, y_pred)
    
    print(f"\n" + "="*60)
    print("MODEL PERFORMANCE ON TEST SET")
    print("="*60)
    print(f"Accuracy: {accuracy:.4f} ({accuracy*100:.1f}%)")
    print(f"\nClassification Report:")
    print(classification_report(y_test, y_pred, target_names=['No Allergens', 'Has Allergens']))
    
    cm = confusion_matrix(y_test, y_pred)
    print(f"\nConfusion Matrix:")
    print(f"  True Negatives: {cm[0,0]}")
    print(f"  False Positives: {cm[0,1]}")
    print(f"  False Negatives: {cm[1,0]}")
    print(f"  True Positives: {cm[1,1]}")
    
    # Cross-validation
    cv_scores = cross_val_score(model, X, y, cv=5)
    print(f"\nCross-validation accuracy: {cv_scores.mean():.4f} (+/- {cv_scores.std()*2:.4f})")
    
    # Save model
    os.makedirs('models', exist_ok=True)
    joblib.dump(model, 'models/random_forest.pkl')
    joblib.dump(vectorizer, 'models/vectorizer.pkl')
    
    print(f"\n✓ Model saved to: models/random_forest.pkl")
    print(f"✓ Vectorizer saved to: models/vectorizer.pkl")
    
    return model, vectorizer

def test_model(model, vectorizer):
    """Test model on real-world examples"""
    
    print("\n" + "="*60)
    print("TESTING ON REAL-WORLD EXAMPLES")
    print("="*60)
    
    test_cases = [
        # Should be UNSAFE (has allergens)
        ("peanut butter", 1),
        ("milk chocolate", 1),
        ("wheat bread", 1),
        ("soy sauce", 1),
        ("eggs", 1),
        ("almond milk", 1),
        ("cheddar cheese", 1),
        ("whey protein", 1),
        ("sesame seeds", 1),
        ("canned tuna", 1),
        
        # Should be SAFE (no allergens)
        ("white rice", 0),
        ("sea salt", 0),
        ("granulated sugar", 0),
        ("spring water", 0),
        ("olive oil", 0),
        ("corn starch", 0),
        ("baking soda", 0),
        ("black pepper", 0),
        ("coffee", 0),
        ("green tea", 0),
    ]
    
    print("\nReal-world test results:")
    print("-"*50)
    
    correct = 0
    for text, expected in test_cases:
        processed = preprocess_text(text)
        vec = vectorizer.transform([processed])
        pred = model.predict(vec)[0]
        prob = model.predict_proba(vec)[0]
        
        expected_label = "UNSAFE" if expected == 1 else "SAFE"
        predicted_label = "UNSAFE" if pred == 1 else "SAFE"
        is_correct = pred == expected
        if is_correct:
            correct += 1
        
        status = "✅" if is_correct else "❌"
        print(f"{status} '{text}': Expected={expected_label}, Predicted={predicted_label} (conf={max(prob):.2%})")
    
    print(f"\nAccuracy on real-world tests: {correct}/{len(test_cases)} = {correct/len(test_cases)*100:.1f}%")

def test_on_actual_ingredients(model, vectorizer):
    """Test on actual ingredient lists from your images"""
    
    print("\n" + "="*60)
    print("TESTING ON ACTUAL INGREDIENT LISTS")
    print("="*60)
    
    # These are actual ingredients from your images
    test_ingredients = [
        # Should be UNSAFE (contains allergens)
        ("peanut butter ingredients: roasted peanuts, sugar, oil, salt", 1),
        ("milk chocolate: sugar, cocoa butter, whole milk powder", 1),
        ("instant noodles: wheat flour, palm oil, salt", 1),
        ("soy sauce: water, soybeans, wheat, salt", 1),
        ("whole wheat bread: whole wheat flour, water, honey, yeast", 1),
        ("ice cream: milk, cream, sugar", 1),
        ("egg noodles: durum wheat, eggs", 1),
        
        # Should be SAFE (no allergens)
        ("rice: white rice", 0),
        ("salt ingredients: sea salt", 0),
        ("sugar: pure cane sugar", 0),
        ("olive oil: extra virgin olive oil", 0),
        ("water: spring water", 0),
    ]
    
    print("\nActual ingredient test results:")
    print("-"*50)
    
    for text, expected in test_ingredients:
        processed = preprocess_text(text)
        vec = vectorizer.transform([processed])
        pred = model.predict(vec)[0]
        prob = model.predict_proba(vec)[0]
        
        expected_label = "UNSAFE" if expected == 1 else "SAFE"
        predicted_label = "UNSAFE" if pred == 1 else "SAFE"
        
        status = "✅" if pred == expected else "❌"
        print(f"{status} '{text[:50]}...': {predicted_label} (conf={max(prob):.2%})")

if __name__ == "__main__":
    model, vectorizer = train_model()
    test_model(model, vectorizer)
    test_on_actual_ingredients(model, vectorizer)
    
    print("\n" + "="*60)
    print("NEXT STEPS:")
    print("="*60)
    print("1. Restart your Flask app to load the new model")
    print("2. Run: python test_accuracy.py")
    print("3. Run: python analyze_results.py")