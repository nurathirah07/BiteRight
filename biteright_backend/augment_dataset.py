"""
Food Allergen Detection - Data Augmentation Script
Handles files in the 'data' subdirectory
"""

import pandas as pd
import numpy as np
import re
from pathlib import Path
import os
import warnings
warnings.filterwarnings('ignore')

# ============================================
# STEP 0: Set up file paths
# ============================================

print("=" * 60)
print("FILE LOCATION SETUP")
print("=" * 60)

# Define paths
data_dir = Path('data')
current_dir = Path.cwd()

print(f"Current directory: {current_dir}")
print(f"Data directory: {data_dir}")
print(f"Data directory exists: {data_dir.exists()}")

# Create data directory if it doesn't exist
if not data_dir.exists():
    data_dir.mkdir()
    print(f"✓ Created data directory")

# ============================================
# STEP 1: Find your training dataset
# ============================================

print("\n" + "=" * 60)
print("STEP 1: Finding your training dataset")
print("=" * 60)

# Look for training file in both root and data directory
training_candidates = [
    current_dir / 'training_data_balanced.csv',
    data_dir / 'training_data_balanced.csv',
    current_dir / 'balanced_dataset.csv',
    data_dir / 'balanced_dataset.csv',
    current_dir / 'training_data.csv',
    data_dir / 'training_data.csv',
]

training_file = None
for candidate in training_candidates:
    if candidate.exists():
        training_file = candidate
        break

if training_file is None:
    print("❌ Could not find training data file!")
    print("\nSearched locations:")
    for candidate in training_candidates:
        print(f"  - {candidate}")
    print("\nPlease ensure your training data CSV is in the root or data directory.")
    exit(1)

# Load training data
existing_df = pd.read_csv(training_file)
print(f"✓ Found: {training_file}")
print(f"✓ Dataset size: {len(existing_df)} rows")
print(f"✓ Columns: {existing_df.columns.tolist()}")
print(f"✓ Class distribution:")
print(f"  - Has allergens (1): {(existing_df['has_allergens'] == 1).sum()}")
print(f"  - No allergens (0): {(existing_df['has_allergens'] == 0).sum()}")
print(f"  - Ratio: {(existing_df['has_allergens'] == 1).sum() / len(existing_df):.2f}")

# ============================================
# STEP 2: Find Open Food Facts file
# ============================================

print("\n" + "=" * 60)
print("STEP 2: Finding Open Food Facts data")
print("=" * 60)

# Look for OFF file in data directory
off_candidates = [
    data_dir / 'en.openfoodfacts.org.products.csv',
    data_dir / 'openfoodfacts.csv',
    data_dir / 'products.csv',
    data_dir / 'en.openfoodfacts.org.products.csv.gz',
    current_dir / 'en.openfoodfacts.org.products.csv',
]

off_file = None
for candidate in off_candidates:
    if candidate.exists():
        off_file = candidate
        break

if off_file is None:
    print("❌ Open Food Facts file not found!")
    print("\nSearched locations:")
    for candidate in off_candidates:
        print(f"  - {candidate}")
    print("\nPlease download the file to the 'data' directory:")
    print("  https://static.openfoodfacts.org/data/en.openfoodfacts.org.products.csv.gz")
    print("\nOr place your CSV file in the data folder with one of these names.")
    exit(1)

print(f"✓ Found: {off_file}")
file_size_mb = off_file.stat().st_size / (1024 * 1024)
print(f"✓ File size: {file_size_mb:.2f} MB")

# ============================================
# STEP 3: Load Open Food Facts data
# ============================================

print("\n" + "=" * 60)
print("STEP 3: Loading Open Food Facts data")
print("=" * 60)

# Define columns we need
required_columns = [
    'code', 'product_name', 'ingredients_text', 
    'allergens', 'countries', 'brands', 'categories'
]

print("Loading data (this may take a minute for large files)...")

try:
    # Check if it's a gzipped file
    if str(off_file).endswith('.gz'):
        print("Detected gzipped file. Decompressing...")
        ofd_df = pd.read_csv(
            off_file,
            compression='gzip',
            usecols=required_columns,
            low_memory=False,
            nrows=200000  # Limit to 200k rows for faster processing
        )
    else:
        # Load regular CSV with limit
        ofd_df = pd.read_csv(
            off_file,
            usecols=required_columns,
            low_memory=False,
            nrows=200000  # Limit to 200k rows
        )
    
    print(f"✓ Loaded {len(ofd_df):,} products from Open Food Facts")
    
except Exception as e:
    print(f"❌ Error loading: {e}")
    print("\nTrying with fewer columns...")
    
    try:
        # Try with minimal columns
        minimal_columns = ['code', 'product_name', 'ingredients_text', 'allergens']
        ofd_df = pd.read_csv(
            off_file,
            usecols=minimal_columns,
            low_memory=False,
            nrows=100000
        )
        print(f"✓ Loaded {len(ofd_df):,} products with minimal columns")
    except Exception as e2:
        print(f"❌ Still failing: {e2}")
        print("\n⚠️ Cannot load Open Food Facts data.")
        print("Using text augmentation on existing data instead...")
        
        # Fallback: simple text augmentation
        print("\nCreating augmented version of existing data...")
        augmented_rows = []
        for _, row in existing_df.iterrows():
            # Create 2 augmented versions
            for i in range(2):
                new_row = row.copy()
                if i == 0:
                    new_row['text'] = row['text'].lower()
                else:
                    new_row['text'] = row['text'].title()
                new_row['barcode'] = f"AUG_{row['barcode']}_{i}"
                augmented_rows.append(new_row)
        
        augmented_df = pd.concat([existing_df, pd.DataFrame(augmented_rows)], ignore_index=True)
        output_file = data_dir / 'training_data_augmented.csv'
        augmented_df.to_csv(output_file, index=False)
        print(f"✓ Created {len(augmented_df)} rows (was {len(existing_df)})")
        print(f"✓ Saved to: {output_file}")
        exit(0)

# ============================================
# STEP 4: Clean and prepare OFF data
# ============================================

print("\n" + "=" * 60)
print("STEP 4: Cleaning and preparing data")
print("=" * 60)

# Rename columns to match training data format
column_mapping = {
    'code': 'barcode',
    'ingredients_text': 'ingredients'
}
ofd_df = ofd_df.rename(columns={k: v for k, v in column_mapping.items() if k in ofd_df.columns})

# Create text column (product name + ingredients)
ofd_df['text'] = ofd_df['product_name'].fillna('') + ' ' + ofd_df['ingredients'].fillna('')
print(f"✓ Created 'text' column")

# Create target variable (has_allergens)
ofd_df['has_allergens'] = ofd_df['allergens'].notna().astype(int)
print(f"✓ Created 'has_allergens' column")

# Filter for quality
initial_count = len(ofd_df)

# Remove rows with very short text
ofd_df = ofd_df[ofd_df['text'].str.len() > 20]
print(f"✓ Removed short text: {initial_count - len(ofd_df):,} rows")

# Remove test/placeholder products
if 'product_name' in ofd_df.columns:
    test_patterns = ['test', 'example', 'unknown', 'to-be-completed', 'demo']
    mask = ~ofd_df['product_name'].fillna('').str.lower().str.contains('|'.join(test_patterns))
    ofd_df = ofd_df[mask]
    print(f"✓ Removed test products")

# Remove rows without ingredients
before_ingredients = len(ofd_df)
ofd_df = ofd_df[ofd_df['ingredients'].notna()]
print(f"✓ Removed missing ingredients: {before_ingredients - len(ofd_df):,} rows")

# Remove duplicates
before_dedup = len(ofd_df)
ofd_df = ofd_df.drop_duplicates(subset=['barcode'], keep='first')
print(f"✓ Removed duplicates: {before_dedup - len(ofd_df):,} rows")

print(f"\n✓ Cleaned dataset: {len(ofd_df):,} usable products")
print(f"  - Has allergens: {(ofd_df['has_allergens'] == 1).sum():,}")
print(f"  - No allergens: {(ofd_df['has_allergens'] == 0).sum():,}")

# ============================================
# STEP 5: Remove overlap with existing data
# ============================================

print("\n" + "=" * 60)
print("STEP 5: Removing overlapping products")
print("=" * 60)

# Convert barcodes to string for comparison
existing_barcodes = set(existing_df['barcode'].dropna().astype(str).unique())
ofd_df['barcode_str'] = ofd_df['barcode'].astype(str)

overlap_count = len(ofd_df[ofd_df['barcode_str'].isin(existing_barcodes)])
ofd_df = ofd_df[~ofd_df['barcode_str'].isin(existing_barcodes)]

print(f"✓ Removed {overlap_count:,} overlapping products")
print(f"✓ New unique products: {len(ofd_df):,}")

# ============================================
# STEP 6: Balance and sample new data
# ============================================

print("\n" + "=" * 60)
print("STEP 6: Balancing the new data")
print("=" * 60)

# Split into classes
allergen_products = ofd_df[ofd_df['has_allergens'] == 1]
non_allergen_products = ofd_df[ofd_df['has_allergens'] == 0]

print(f"Available new products:")
print(f"  - With allergens: {len(allergen_products):,}")
print(f"  - Without allergens: {len(non_allergen_products):,}")

# Calculate how many to add (aim to double the dataset or add up to 2000)
current_has = (existing_df['has_allergens'] == 1).sum()
current_no = (existing_df['has_allergens'] == 0).sum()

# Target: make both classes equal to the larger class, up to 2000 each
target_per_class = max(current_has, current_no, 500)  # At least 500 per class
target_per_class = min(target_per_class, 2000)  # Cap at 2000 to keep dataset manageable

needed_has = max(0, target_per_class - current_has)
needed_no = max(0, target_per_class - current_no)

print(f"\nTarget: {target_per_class} per class (total {target_per_class * 2} rows)")
print(f"Need: +{needed_has} with allergens, +{needed_no} without allergens")

# Sample from available data
sampled_has = allergen_products.head(needed_has) if needed_has > 0 else pd.DataFrame()
sampled_no = non_allergen_products.head(needed_no) if needed_no > 0 else pd.DataFrame()

new_data = pd.concat([sampled_has, sampled_no], ignore_index=True)

# Keep only columns that exist in training data
keep_cols = ['barcode', 'text', 'has_allergens', 'ingredients', 'product_name', 'brands', 'countries', 'categories']
new_data = new_data[[col for col in keep_cols if col in new_data.columns]]

print(f"\n✓ Added {len(new_data)} new products")
print(f"  - With allergens: {(new_data['has_allergens'] == 1).sum()}")
print(f"  - Without allergens: {(new_data['has_allergens'] == 0).sum()}")

# ============================================
# STEP 7: Merge datasets
# ============================================

print("\n" + "=" * 60)
print("STEP 7: Merging datasets")
print("=" * 60)

# Ensure columns match
for col in new_data.columns:
    if col not in existing_df.columns:
        existing_df[col] = None

# Combine
augmented_df = pd.concat([existing_df, new_data], ignore_index=True)

print(f"✓ Original: {len(existing_df)} rows")
print(f"✓ Added: {len(new_data)} rows")
print(f"✓ Total: {len(augmented_df)} rows")

# ============================================
# STEP 8: Save augmented dataset
# ============================================

print("\n" + "=" * 60)
print("STEP 8: Saving augmented dataset")
print("=" * 60)

from datetime import datetime
timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

# Save in data directory
output_file = data_dir / f'training_data_augmented_{timestamp}.csv'
augmented_df.to_csv(output_file, index=False)

print(f"✓ Saved to: {output_file}")
print(f"✓ File size: {output_file.stat().st_size / 1024:.2f} KB")

# Also save a copy in root for easy access
root_copy = current_dir / f'training_data_augmented_{timestamp}.csv'
augmented_df.to_csv(root_copy, index=False)
print(f"✓ Also saved to: {root_copy}")

# ============================================
# STEP 9: Final summary
# ============================================

print("\n" + "=" * 60)
print("AUGMENTATION SUMMARY")
print("=" * 60)

print(f"""
┌─────────────────────────────────────────────────────────────┐
│                    DATA AUGMENTATION REPORT                 │
├─────────────────────────────────────────────────────────────┤
│ Original dataset size:        {len(existing_df):>10} rows          │
│ New products added:           {len(new_data):>10} rows          │
│ Total dataset size:           {len(augmented_df):>10} rows          │
├─────────────────────────────────────────────────────────────┤
│ Class distribution:                                          │
│   Has allergens (1):          {(augmented_df['has_allergens'] == 1).sum():>10} rows  │
│   No allergens (0):           {(augmented_df['has_allergens'] == 0).sum():>10} rows  │
├─────────────────────────────────────────────────────────────┤
│ Output files:                                               │
│   Primary: {output_file.name} │
│   Backup:  {root_copy.name} │
└─────────────────────────────────────────────────────────────┘
""")

# Show sample of newly added products
print("\nSample of newly added products:")
print("=" * 60)
if len(new_data) > 0:
    sample_cols = ['product_name', 'has_allergens', 'brands']
    existing_cols = [col for col in sample_cols if col in new_data.columns]
    print(new_data[existing_cols].head(10).to_string(index=False))
else:
    print("No new products were added (dataset already balanced)")

print("\n✅ Augmentation complete! You can now use this dataset for training.")