"""
Extract training data from Firebase for ML model training
UPDATED with synthetic negative sample generation
"""

import firebase_admin
from firebase_admin import credentials, firestore
import pandas as pd
import numpy as np
from collections import Counter
import re
import os
import random

# Initialize Firebase
cred = credentials.Certificate('serviceAccountKey.json')
firebase_admin.initialize_app(cred)
db = firestore.client()

def extract_training_data():
    """Extract products with allergen information from Firebase"""
    
    print("Extracting training data from Firebase...")
    
    # List available collections
    collections = [col.id for col in db.collections()]
    print(f"Available collections: {collections}")
    
    # Use openfoodfacts_products collection
    collection_name = 'openfoodfacts_products'
    
    if collection_name not in collections:
        print(f"Collection '{collection_name}' not found!")
        return pd.DataFrame()
    
    print(f"\nExtracting from: {collection_name}")
    products_ref = db.collection(collection_name).stream()
    
    data = []
    count = 0
    
    for product in products_ref:
        product_data = product.to_dict()
        count += 1
        
        # Extract fields based on your actual structure
        barcode = product_data.get('barcode', '') or product.id
        product_name = product_data.get('product_name', '')
        brands = product_data.get('brands', '')
        categories = product_data.get('categories', '')
        
        # Get allergens (array in your structure)
        allergens = product_data.get('allergens', [])
        if not isinstance(allergens, list):
            # If it's a string, convert to list
            if isinstance(allergens, str):
                allergens = [a.strip() for a in allergens.split(',') if a.strip()]
            else:
                allergens = []
        
        # Get has_allergens flag
        has_allergens = product_data.get('has_allergens', False)
        
        # Since there's no ingredients field, we'll use product_name + categories as text
        text_for_ml = f"{product_name} {categories} {brands}".lower()
        
        # Only include if we have some text to work with
        if len(text_for_ml) > 10:
            data.append({
                'barcode': barcode,
                'product_name': product_name,
                'brands': brands,
                'categories': categories,
                'text': text_for_ml,  # Combined text for ML
                'allergens': str(allergens),  # Store as string for CSV
                'has_allergens': 1 if has_allergens else 0,
                'allergen_count': len(allergens)
            })
        
        # Progress indicator
        if count % 100 == 0:
            print(f"   Processed {count} products...")
    
    if not data:
        print("No products extracted!")
        return pd.DataFrame()
    
    df = pd.DataFrame(data)
    print(f"\nExtracted {len(df)} products")
    print(f"   Products with allergens: {df['has_allergens'].sum()}")
    print(f"   Products without allergens: {len(df) - df['has_allergens'].sum()}")
    
    # Show sample
    print("\nSample products:")
    for i, row in df.head(3).iterrows():
        print(f"   • {row['product_name']}: {row['allergens']}")
    
    # Save to CSV
    df.to_csv('training_data.csv', index=False)
    print("Saved training data to training_data.csv")
    
    return df

def analyze_allergen_distribution(df):
    """Analyze the distribution of allergens in your dataset"""
    
    if len(df) == 0:
        print("No data to analyze")
        return
    
    print("\nAllergen Distribution Analysis:")
    
    # Count all allergens
    all_allergens = []
    for idx, row in df[df['has_allergens'] == 1].iterrows():
        allergens_str = row['allergens']
        # Parse string representation of list
        if isinstance(allergens_str, str) and allergens_str.startswith('['):
            try:
                allergens = eval(allergens_str)
                if isinstance(allergens, list):
                    all_allergens.extend(allergens)
            except:
                pass
    
    if not all_allergens:
        print("No allergen data found in the extracted products")
        return
    
    allergen_counts = Counter(all_allergens)
    
    print(f"Total allergen occurrences: {len(all_allergens)}")
    print(f"Unique allergens: {len(allergen_counts)}")
    print("\nTop 20 most common allergens:")
    for allergen, count in allergen_counts.most_common(20):
        print(f"   {allergen}: {count}")

def add_synthetic_negative_samples(df, target_ratio=0.5):
    """
    Add synthetic negative samples if real ones are missing
    """
    
    positive = df[df['has_allergens'] == 1]
    negative = df[df['has_allergens'] == 0]
    
    if len(negative) > 0:
        print(f"\nAlready have {len(negative)} negative samples")
        return df
    
    print(f"\nNo negative samples found. Creating synthetic ones...")
    
    # Common non-allergenic products (safe products)
    safe_products = [
        {
            'product_name': 'Pure Salt',
            'brands': 'Generic',
            'categories': 'Seasoning,Spices',
            'text': 'pure salt seasoning spices',
            'allergens': '[]',
            'has_allergens': 0
        },
        {
            'product_name': 'White Sugar',
            'brands': 'Generic',
            'categories': 'Sweetener,Baking',
            'text': 'white sugar sweetener baking',
            'allergens': '[]',
            'has_allergens': 0
        },
        {
            'product_name': 'Water',
            'brands': 'Generic',
            'categories': 'Beverages',
            'text': 'water beverages',
            'allergens': '[]',
            'has_allergens': 0
        },
        {
            'product_name': 'Olive Oil',
            'brands': 'Generic',
            'categories': 'Oils,Fats',
            'text': 'olive oil fats cooking',
            'allergens': '[]',
            'has_allergens': 0
        },
        {
            'product_name': 'White Rice',
            'brands': 'Generic',
            'categories': 'Grains,Rice',
            'text': 'white rice grains',
            'allergens': '[]',
            'has_allergens': 0
        },
        {
            'product_name': 'Corn Starch',
            'brands': 'Generic',
            'categories': 'Baking,Thickener',
            'text': 'corn starch baking thickener',
            'allergens': '[]',
            'has_allergens': 0
        },
        {
            'product_name': 'Baking Soda',
            'brands': 'Generic',
            'categories': 'Baking,Leavening',
            'text': 'baking soda leavening',
            'allergens': '[]',
            'has_allergens': 0
        },
        {
            'product_name': 'White Vinegar',
            'brands': 'Generic',
            'categories': 'Condiments',
            'text': 'white vinegar condiments',
            'allergens': '[]',
            'has_allergens': 0
        },
        {
            'product_name': 'Honey',
            'brands': 'Generic',
            'categories': 'Sweetener',
            'text': 'honey sweetener natural',
            'allergens': '[]',
            'has_allergens': 0
        },
        {
            'product_name': 'Maple Syrup',
            'brands': 'Generic',
            'categories': 'Sweetener,Syrup',
            'text': 'maple syrup sweetener',
            'allergens': '[]',
            'has_allergens': 0
        },
        {
            'product_name': 'Black Pepper',
            'brands': 'Generic',
            'categories': 'Spices,Seasoning',
            'text': 'black pepper spices seasoning',
            'allergens': '[]',
            'has_allergens': 0
        },
        {
            'product_name': 'Cinnamon',
            'brands': 'Generic',
            'categories': 'Spices,Baking',
            'text': 'cinnamon spices baking',
            'allergens': '[]',
            'has_allergens': 0
        },
        {
            'product_name': 'Vanilla Extract',
            'brands': 'Generic',
            'categories': 'Baking,Flavoring',
            'text': 'vanilla extract baking flavoring',
            'allergens': '[]',
            'has_allergens': 0
        },
        {
            'product_name': 'Coffee Beans',
            'brands': 'Generic',
            'categories': 'Beverages,Coffee',
            'text': 'coffee beans beverages',
            'allergens': '[]',
            'has_allergens': 0
        },
        {
            'product_name': 'Green Tea',
            'brands': 'Generic',
            'categories': 'Beverages,Tea',
            'text': 'green tea beverages',
            'allergens': '[]',
            'has_allergens': 0
        }
    ]
    
    # Create variations by adding numbers to product names
    synthetic_negatives = []
    num_needed = len(positive)  # Create as many negatives as positives
    
    for i in range(num_needed):
        base = random.choice(safe_products)
        synthetic = base.copy()
        
        # Add variation to make each slightly different
        variation = random.choice(['', ' Organic', ' Premium', ' Fine', ' Pure', ' Natural'])
        synthetic['product_name'] = base['product_name'] + variation
        synthetic['barcode'] = f"SYNTHETIC_{i:04d}"
        synthetic['brands'] = base['brands'] + random.choice(['', ' Co.', ' Inc.', ' Brands'])
        
        # Slightly vary the text
        words = synthetic['text'].split()
        if len(words) > 2:
            random.shuffle(words)
            synthetic['text'] = ' '.join(words)
        
        synthetic_negatives.append(synthetic)
    
    synthetic_df = pd.DataFrame(synthetic_negatives)
    print(f"Created {len(synthetic_df)} synthetic negative samples")
    
    # Combine with original data
    combined_df = pd.concat([df, synthetic_df], ignore_index=True)
    
    # Shuffle the dataset
    combined_df = combined_df.sample(frac=1, random_state=42).reset_index(drop=True)
    
    print(f"\nCombined dataset statistics:")
    print(f"   Total samples: {len(combined_df)}")
    print(f"   Positive (has allergens): {combined_df['has_allergens'].sum()}")
    print(f"   Negative (no allergens): {len(combined_df) - combined_df['has_allergens'].sum()}")
    print(f"   Ratio positive/negative: {combined_df['has_allergens'].sum() / (len(combined_df) - combined_df['has_allergens'].sum()):.2f}")
    
    return combined_df

def create_balanced_dataset(df):
    """Create a balanced dataset for training"""
    
    if len(df) == 0:
        print("No data to balance")
        return df
    
    # Separate positive and negative samples
    positive = df[df['has_allergens'] == 1]
    negative = df[df['has_allergens'] == 0]
    
    print(f"\nBefore balancing:")
    print(f"   Positive samples: {len(positive)}")
    print(f"   Negative samples: {len(negative)}")
    
    if len(positive) == 0:
        print("No positive samples found!")
        return df
    
    # If no negative samples, add synthetic ones
    if len(negative) == 0:
        print("No negative samples found! Adding synthetic negatives...")
        df = add_synthetic_negative_samples(df)
        # Re-extract positive and negative
        positive = df[df['has_allergens'] == 1]
        negative = df[df['has_allergens'] == 0]
    
    # Balance the dataset
    if len(positive) < len(negative):
        # Undersample negative
        negative_sampled = negative.sample(n=len(positive), random_state=42)
        balanced_df = pd.concat([positive, negative_sampled])
    elif len(negative) < len(positive):
        # Undersample positive
        positive_sampled = positive.sample(n=len(negative), random_state=42)
        balanced_df = pd.concat([positive_sampled, negative])
    else:
        # Already balanced
        balanced_df = df.copy()
    
    # Shuffle
    balanced_df = balanced_df.sample(frac=1, random_state=42).reset_index(drop=True)
    
    print(f"\nAfter balancing:")
    print(f"   Total samples: {len(balanced_df)}")
    print(f"   Positive: {len(balanced_df[balanced_df['has_allergens']==1])}")
    print(f"   Negative: {len(balanced_df[balanced_df['has_allergens']==0])}")
    
    return balanced_df

def create_sample_data():
    """Create sample data for testing if no real data exists"""
    print("\nCreating sample data for testing...")
    
    sample_data = [
        # Positive samples (with allergens)
        {
            'barcode': '001',
            'product_name': 'Creamy Peanut Butter',
            'brands': 'Test Brand',
            'categories': 'Spread,Nut Butter',
            'text': 'creamy peanut butter spread nut butter test brand',
            'allergens': "['peanuts']",
            'has_allergens': 1
        },
        {
            'barcode': '002',
            'product_name': 'Milk Chocolate Bar',
            'brands': 'Test Brand',
            'categories': 'Confectionery,Chocolate',
            'text': 'milk chocolate bar confectionery chocolate test brand',
            'allergens': "['milk']",
            'has_allergens': 1
        },
        {
            'barcode': '003',
            'product_name': 'Whole Wheat Bread',
            'brands': 'Test Brand',
            'categories': 'Bakery,Bread',
            'text': 'whole wheat bread bakery bread test brand',
            'allergens': "['gluten', 'wheat']",
            'has_allergens': 1
        },
        {
            'barcode': '004',
            'product_name': 'Soy Milk',
            'brands': 'Test Brand',
            'categories': 'Beverages,Milk Alternative',
            'text': 'soy milk beverages milk alternative test brand',
            'allergens': "['soy']",
            'has_allergens': 1
        },
        {
            'barcode': '005',
            'product_name': 'Almond Flour',
            'brands': 'Test Brand',
            'categories': 'Baking,Flour',
            'text': 'almond flour baking flour test brand',
            'allergens': "['almonds', 'tree nuts']",
            'has_allergens': 1
        },
        # Negative samples (no allergens)
        {
            'barcode': '006',
            'product_name': 'Pure Sea Salt',
            'brands': 'Test Brand',
            'categories': 'Seasoning,Spices',
            'text': 'pure sea salt seasoning spices test brand',
            'allergens': "[]",
            'has_allergens': 0
        },
        {
            'barcode': '007',
            'product_name': 'White Cane Sugar',
            'brands': 'Test Brand',
            'categories': 'Sweetener,Baking',
            'text': 'white cane sugar sweetener baking test brand',
            'allergens': "[]",
            'has_allergens': 0
        },
        {
            'barcode': '008',
            'product_name': 'Spring Water',
            'brands': 'Test Brand',
            'categories': 'Beverages,Water',
            'text': 'spring water beverages water test brand',
            'allergens': "[]",
            'has_allergens': 0
        },
        {
            'barcode': '009',
            'product_name': 'Extra Virgin Olive Oil',
            'brands': 'Test Brand',
            'categories': 'Oils,Cooking',
            'text': 'extra virgin olive oil oils cooking test brand',
            'allergens': "[]",
            'has_allergens': 0
        },
        {
            'barcode': '010',
            'product_name': 'Basmati Rice',
            'brands': 'Test Brand',
            'categories': 'Grains,Rice',
            'text': 'basmati rice grains rice test brand',
            'allergens': "[]",
            'has_allergens': 0
        }
    ]
    
    df = pd.DataFrame(sample_data)
    print(f"Created {len(df)} sample products (5 positive, 5 negative)")
    return df

def validate_dataset(df):
    """Validate the dataset before saving"""
    
    print("\nValidating dataset...")
    
    issues = []
    
    # Check for required columns
    required_cols = ['barcode', 'product_name', 'text', 'has_allergens']
    for col in required_cols:
        if col not in df.columns:
            issues.append(f"Missing required column: {col}")
    
    if issues:
        print("Issues found:")
        for issue in issues:
            print(f"   • {issue}")
        return False
    
    # Check for null values
    null_counts = df.isnull().sum()
    if null_counts.sum() > 0:
        print("Null values found:")
        for col, count in null_counts[null_counts > 0].items():
            print(f"   • {col}: {count} nulls")
        # Fill nulls
        df = df.fillna('')
    
    # Check class balance
    pos = df['has_allergens'].sum()
    neg = len(df) - pos
    print(f"\nFinal class distribution:")
    print(f"   Positive: {pos} ({pos/len(df)*100:.1f}%)")
    print(f"   Negative: {neg} ({neg/len(df)*100:.1f}%)")
    
    if pos == 0 or neg == 0:
        print("CRITICAL: Only one class present!")
        return False
    
    if abs(pos - neg) > len(df) * 0.3:  # If imbalance > 30%
        print("Warning: Significant class imbalance detected")
    
    return True

if __name__ == "__main__":
    print("="*60)
    print("BITERIGHT - TRAINING DATA EXTRACTION")
    print("="*60)
    
    # Try to extract real data
    df = extract_training_data()
    
    # If no real data, use sample data
    if len(df) == 0:
        print("\nNo real data found in Firebase.")
        use_sample = input("Use sample data for testing? (y/n): ").lower()
        if use_sample == 'y':
            df = create_sample_data()
        else:
            print("Exiting...")
            exit()
    
    if len(df) > 0:
        analyze_allergen_distribution(df)
        
        # Create balanced dataset (this will add synthetic negatives if needed)
        balanced_df = create_balanced_dataset(df)
        
        # Validate the dataset
        if validate_dataset(balanced_df):
            # Save balanced dataset
            balanced_df.to_csv('training_data_balanced.csv', index=False)
            print("\nTraining data preparation complete!")
            print(f"Saved to: training_data_balanced.csv")
            print(f"\nFinal dataset size: {len(balanced_df)} products")
            print(f"   Used fields: product_name, brands, categories")
            
            # Show sample of the final dataset
            print("\nSample from final dataset:")
            sample = balanced_df.sample(min(3, len(balanced_df)))
            for idx, row in sample.iterrows():
                status = "HAS ALLERGENS" if row['has_allergens'] == 1 else "SAFE"
                print(f"   • {row['product_name']}: {status}")
        else:
            print("\nDataset validation failed. Please check the issues above.")