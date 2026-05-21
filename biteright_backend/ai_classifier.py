"""
Random Forest Model for Allergen Detection
"""

import pandas as pd
import numpy as np
from sklearn.model_selection import train_test_split, cross_val_score, StratifiedKFold
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import classification_report, confusion_matrix, accuracy_score, f1_score
import joblib
import re
import nltk
from nltk.corpus import stopwords
import os
import warnings
warnings.filterwarnings('ignore')

# Download NLTK data if needed
try:
    nltk.download('stopwords', quiet=True)
    STOPWORDS = set(stopwords.words('english'))
except:
    STOPWORDS = set()

class AllergenClassifier:
    """
    Random Forest Classifier for allergen detection
    Uses product_name, brands, and categories combined as text
    """
    
    def __init__(self):
        self.vectorizer = TfidfVectorizer(
            max_features=5000,
            ngram_range=(1, 3),
            stop_words='english',
            min_df=1,
            max_df=0.9
        )
        
        # Random Forest Classifier
        self.model = RandomForestClassifier(
            n_estimators=100,
            max_depth=15,
            min_samples_split=5,
            min_samples_leaf=2,
            random_state=42,
            n_jobs=-1
        )
        
        self.is_trained = False
        self.feature_names = None
        
    def preprocess_text(self, text):
        """Clean and preprocess text"""
        if pd.isna(text) or text is None:
            return ""
        
        text = str(text).lower()
        text = re.sub(r'[^a-zA-Z\s]', ' ', text)
        text = re.sub(r'\s+', ' ', text).strip()
        
        return text
    
    def prepare_features(self, df):
        """Prepare features from the text column"""
        print("Preparing features...")
        
        if 'text' in df.columns:
            text_column = 'text'
            print(f"   Using 'text' column")
        elif 'ingredients' in df.columns:
            text_column = 'ingredients'
            print(f"   Using 'ingredients' column")
        else:
            print(f"   Creating text from available columns...")
            df['text'] = df.apply(lambda row: 
                f"{row.get('product_name', '')} {row.get('brands', '')} {row.get('categories', '')}", 
                axis=1
            )
            text_column = 'text'
        
        print(f"   Preprocessing {len(df)} samples...")
        df['processed_text'] = df[text_column].apply(self.preprocess_text)
        
        df = df[df['processed_text'].str.len() > 0]
        print(f"   After preprocessing: {len(df)} samples")
        
        print("\nSample processed text:")
        for i, text in enumerate(df['processed_text'].head(3)):
            print(f"   {i+1}. {text[:100]}...")
        
        print(f"   Vectorizing text...")
        X = self.vectorizer.fit_transform(df['processed_text'])
        y = df['has_allergens'].values
        
        self.feature_names = self.vectorizer.get_feature_names_out()
        
        print(f"   Feature matrix shape: {X.shape}")
        print(f"   Vocabulary size: {len(self.feature_names)}")
        print(f"   Class distribution: {np.bincount(y)}")
        
        return X, y, df
    
    def train(self, df):
        """Train the Random Forest model"""
        print("\nTraining Random Forest Model...")
        
        X, y, df_clean = self.prepare_features(df)
        
        if X.shape[0] < 10:
            print("Not enough samples for training!")
            return 0.0
        
        unique_classes = np.unique(y)
        if len(unique_classes) < 2:
            print("Training data must contain both positive and negative samples!")
            print(f"   Found only class: {unique_classes[0]}")
            return 0.0
        
        try:
            X_train, X_test, y_train, y_test = train_test_split(
                X, y, test_size=0.2, random_state=42, stratify=y
            )
            
            print(f"\n   Training samples: {X_train.shape[0]}")
            print(f"   Test samples: {X_test.shape[0]}")
            print(f"   Training class distribution: {np.bincount(y_train)}")
            print(f"   Test class distribution: {np.bincount(y_test)}")
            
            print(f"   Training Random Forest...")
            self.model.fit(X_train, y_train)
            
            y_pred = self.model.predict(X_test)
            accuracy = accuracy_score(y_test, y_pred)
            f1 = f1_score(y_test, y_pred, average='weighted')
            
            print("\nModel Performance:")
            print(f"   Accuracy: {accuracy:.4f}")
            print(f"   F1-Score: {f1:.4f}")
            
            if X.shape[0] >= 15:
                print(f"\n   Performing 3-fold cross-validation...")
                cv = StratifiedKFold(n_splits=3, shuffle=True, random_state=42)
                cv_scores = cross_val_score(self.model, X, y, cv=cv, scoring='accuracy')
                print(f"   Cross-validation accuracy: {cv_scores.mean():.4f} (+/- {cv_scores.std()*2:.4f})")
            
            print("\nClassification Report:")
            print(classification_report(y_test, y_pred, target_names=['No Allergens', 'Has Allergens'], zero_division=0))
            
            cm = confusion_matrix(y_test, y_pred)
            print("\nConfusion Matrix:")
            print(f"   True Negatives: {cm[0,0]}, False Positives: {cm[0,1]}")
            print(f"   False Negatives: {cm[1,0]}, True Positives: {cm[1,1]}")
            
            self.is_trained = True
            
            # Show feature importance
            if hasattr(self.model, 'feature_importances_'):
                importance = self.model.feature_importances_
                top_indices = np.argsort(importance)[-20:]
                print("\nTop 20 most important features:")
                for idx in sorted(top_indices, reverse=True):
                    if importance[idx] > 0.005:
                        print(f"   {self.feature_names[idx]}: {importance[idx]:.4f}")
            
            return accuracy
            
        except Exception as e:
            print(f"Error during training: {e}")
            return 0.0
    
    def predict(self, text):
        """Predict if text indicates allergens"""
        if not self.is_trained:
            print("Model not trained yet!")
            return {
                'has_allergens': False,
                'confidence': 0.0,
                'probabilities': {'no_allergens': 0.5, 'has_allergens': 0.5},
                'processed_text': self.preprocess_text(text)
            }
        
        processed = self.preprocess_text(text)
        X = self.vectorizer.transform([processed])
        
        try:
            prediction = self.model.predict(X)[0]
            probabilities = self.model.predict_proba(X)[0]
            
            return {
                'has_allergens': bool(prediction),
                'confidence': float(max(probabilities)),
                'probabilities': {
                    'no_allergens': float(probabilities[0]),
                    'has_allergens': float(probabilities[1])
                },
                'processed_text': processed
            }
        except Exception as e:
            print(f"Prediction error: {e}")
            return {
                'has_allergens': False,
                'confidence': 0.0,
                'error': str(e),
                'processed_text': processed
            }
    
    def save_model(self, path='models/'):
        """Save trained model to disk"""
        os.makedirs(path, exist_ok=True)
        
        try:
            joblib.dump(self.model, f'{path}random_forest.pkl')
            joblib.dump(self.vectorizer, f'{path}vectorizer.pkl')
            
            if self.feature_names is not None:
                np.save(f'{path}feature_names.npy', self.feature_names)
            
            print(f"Models saved to {path}")
            return True
        except Exception as e:
            print(f"Error saving models: {e}")
            return False
    
    def load_model(self, path='models/'):
        """Load pre-trained model"""
        try:
            if not os.path.exists(f'{path}random_forest.pkl'):
                print(f"No trained model found in {path}")
                return False
            
            self.model = joblib.load(f'{path}random_forest.pkl')
            self.vectorizer = joblib.load(f'{path}vectorizer.pkl')
            
            if os.path.exists(f'{path}feature_names.npy'):
                self.feature_names = np.load(f'{path}feature_names.npy', allow_pickle=True)
            
            self.is_trained = True
            print(f"Random Forest model loaded from {path}")
            return True
        except Exception as e:
            print(f"Error loading model: {e}")
            return False

def load_training_data():
    """Load and validate training data"""
    possible_files = [
        'training_data_balanced.csv',
        'training_data_fixed.csv',
        'training_data.csv'
    ]
    
    for file in possible_files:
        if os.path.exists(file):
            df = pd.read_csv(file)
            print(f"\nLoaded {len(df)} training samples from {file}")
            
            if 'has_allergens' not in df.columns:
                print(f"{file} missing 'has_allergens' column")
                continue
            
            pos = df['has_allergens'].sum()
            neg = len(df) - pos
            
            print(f"   Positive samples: {pos}")
            print(f"   Negative samples: {neg}")
            
            if pos > 0 and neg > 0:
                return df
            else:
                print(f"{file} has only one class. Need both positive and negative samples.")
    
    return None

def main():
    """Main training pipeline"""
    
    print("="*60)
    print("BITERIGHT - RANDOM FOREST CLASSIFIER TRAINING")
    print("="*60)
    
    df = load_training_data()
    
    if df is None:
        print("\nNo valid training data found!")
        print("\nPlease run create_training_data.py first to generate training data.")
        return

    print(f"\nData columns: {list(df.columns)}")

    classifier = AllergenClassifier()
    accuracy = classifier.train(df)
    
    if accuracy > 0:
        classifier.save_model()
        
        print("\nTesting with sample products from training data:")
        sample_size = min(5, len(df))
        sample_products = df.sample(sample_size)
        
        for idx, row in sample_products.iterrows():
            text = f"{row.get('product_name', '')} {row.get('brands', '')} {row.get('categories', '')}"
            result = classifier.predict(text)
            
            if result:
                actual = "Has Allergens" if row['has_allergens'] == 1 else "No Allergens"
                predicted = "Has Allergens" if result['has_allergens'] else "No Allergens"
                check = "OK" if result['has_allergens'] == row['has_allergens'] else "FAIL"
                
                print(f"\n   {check} Product: {row['product_name'][:50]}")
                print(f"      Actual: {actual}")
                print(f"      Predicted: {predicted}")
                print(f"      Confidence: {result['confidence']:.2%}")
        
        print("\nTraining and testing completed!")
    else:   
        print("\nTraining failed. Please check your data.")
        print("   Make sure you have both positive and negative samples.")

if __name__ == "__main__":
    main()