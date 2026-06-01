"""
Extract training data from Firebase for ML model training
UPDATED with synthetic negative sample generation
"""

import csv
import firebase_admin  # type: ignore
from firebase_admin import credentials, firestore  # type: ignore
from collections import Counter
import random

# Initialize Firebase
cred = credentials.Certificate('serviceAccountKey.json')
firebase_admin.initialize_app(cred)
db = firestore.client()


def save_to_csv(data, filename):
    if not data:
        print(f"No data to save to {filename}")
        return

    fieldnames = sorted({key for row in data for key in row.keys()})
    with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        for row in data:
            writer.writerow({key: '' if value is None else str(value) for key, value in row.items()})


def parse_allergens(allergens):
    if isinstance(allergens, list):
        return allergens
    if isinstance(allergens, str):
        allergens = allergens.strip()
        if allergens.startswith('[') and allergens.endswith(']'):
            try:
                parsed = eval(allergens)
                if isinstance(parsed, list):
                    return parsed
            except Exception:
                pass
        return [a.strip() for a in allergens.split(',') if a.strip()]
    return []


def extract_training_data():
    """Extract products with allergen information from Firebase"""
    print("Extracting training data from Firebase...")

    collections = [col.id for col in db.collections()]
    print(f"Available collections: {collections}")

    collection_name = 'openfoodfacts_products'
    if collection_name not in collections:
        print(f"Collection '{collection_name}' not found!")
        return []

    print(f"\nExtracting from: {collection_name}")
    products_ref = db.collection(collection_name).stream()

    data = []
    count = 0

    for product in products_ref:
        product_data = product.to_dict() or {}
        count += 1

        barcode = product_data.get('barcode', '') or product.id
        product_name = product_data.get('product_name', '') or ''
        brands = product_data.get('brands', '') or ''
        categories = product_data.get('categories', '') or ''

        allergens = product_data.get('allergens', [])
        if not isinstance(allergens, list):
            allergens = parse_allergens(allergens)

        has_allergens = bool(product_data.get('has_allergens', False))
        text_for_ml = f"{product_name} {categories} {brands}".lower().strip()

        if len(text_for_ml) > 10:
            data.append({
                'barcode': barcode,
                'product_name': product_name,
                'brands': brands,
                'categories': categories,
                'text': text_for_ml,
                'allergens': str(allergens),
                'has_allergens': 1 if has_allergens else 0,
                'allergen_count': len(allergens)
            })

        if count % 100 == 0:
            print(f"   Processed {count} products...")

    if not data:
        print("No products extracted!")
        return []

    total = len(data)
    positives = sum(item['has_allergens'] for item in data)
    negatives = total - positives

    print(f"\nExtracted {total} products")
    print(f"   Products with allergens: {positives}")
    print(f"   Products without allergens: {negatives}")

    print("\nSample products:")
    for row in data[:3]:
        print(f"   • {row['product_name']}: {row['allergens']}")

    save_to_csv(data, 'training_data.csv')
    print("Saved training data to training_data.csv")

    return data


def analyze_allergen_distribution(data):
    """Analyze the distribution of allergens in your dataset"""
    if not data:
        print("No data to analyze")
        return

    print("\nAllergen Distribution Analysis:")
    all_allergens = []

    for row in data:
        if row.get('has_allergens') == 1:
            all_allergens.extend(parse_allergens(row.get('allergens', [])))

    if not all_allergens:
        print("No allergen data found in the extracted products")
        return

    allergen_counts = Counter(all_allergens)

    print(f"Total allergen occurrences: {len(all_allergens)}")
    print(f"Unique allergens: {len(allergen_counts)}")
    print("\nTop 20 most common allergens:")
    for allergen, count in allergen_counts.most_common(20):
        print(f"   {allergen}: {count}")


def add_synthetic_negative_samples(data, target_ratio=0.5):
    """
    Add synthetic negative samples if real ones are missing
    """
    positive = [item for item in data if item.get('has_allergens') == 1]
    negative = [item for item in data if item.get('has_allergens') == 0]

    if len(negative) > 0:
        print(f"\nAlready have {len(negative)} negative samples")
        return data

    print(f"\nNo negative samples found. Creating synthetic ones...")

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

    synthetic_negatives = []
    num_needed = len(positive)

    for i in range(num_needed):
        base = random.choice(safe_products)
        synthetic = base.copy()
        variation = random.choice(['', ' Organic', ' Premium', ' Fine', ' Pure', ' Natural'])
        synthetic['product_name'] = base['product_name'] + variation
        synthetic['barcode'] = f"SYNTHETIC_{i:04d}"
        synthetic['brands'] = base['brands'] + random.choice(['', ' Co.', ' Inc.', ' Brands'])

        words = synthetic['text'].split()
        if len(words) > 2:
            random.shuffle(words)
            synthetic['text'] = ' '.join(words)

        synthetic['allergen_count'] = 0
        synthetic_negatives.append(synthetic)

    print(f"Created {len(synthetic_negatives)} synthetic negative samples")

    combined_data = list(data) + synthetic_negatives
    random.Random(42).shuffle(combined_data)

    total = len(combined_data)
    positives = sum(item['has_allergens'] for item in combined_data)
    negatives = total - positives

    print(f"\nCombined dataset statistics:")
    print(f"   Total samples: {total}")
    print(f"   Positive (has allergens): {positives}")
    print(f"   Negative (no allergens): {negatives}")
    if negatives > 0:
        print(f"   Ratio positive/negative: {positives / negatives:.2f}")
    else:
        print("   Ratio positive/negative: infinite")

    return combined_data


def create_balanced_dataset(data):
    """Create a balanced dataset for training"""
    if not data:
        print("No data to balance")
        return data

    positive = [item for item in data if item.get('has_allergens') == 1]
    negative = [item for item in data if item.get('has_allergens') == 0]

    print(f"\nBefore balancing:")
    print(f"   Positive samples: {len(positive)}")
    print(f"   Negative samples: {len(negative)}")

    if len(positive) == 0:
        print("No positive samples found!")
        return data

    if len(negative) == 0:
        print("No negative samples found! Adding synthetic negatives...")
        data = add_synthetic_negative_samples(data)
        positive = [item for item in data if item.get('has_allergens') == 1]
        negative = [item for item in data if item.get('has_allergens') == 0]

    if len(positive) < len(negative):
        sampled_negative = random.Random(42).sample(negative, len(positive))
        balanced_data = list(positive) + sampled_negative
    elif len(negative) < len(positive):
        sampled_positive = random.Random(42).sample(positive, len(negative))
        balanced_data = sampled_positive + list(negative)
    else:
        balanced_data = list(data)

    random.Random(42).shuffle(balanced_data)

    positives = sum(item['has_allergens'] for item in balanced_data)
    negatives = len(balanced_data) - positives

    print(f"\nAfter balancing:")
    print(f"   Total samples: {len(balanced_data)}")
    print(f"   Positive: {positives}")
    print(f"   Negative: {negatives}")

    return balanced_data


def create_sample_data():
    """Create sample data for testing if no real data exists"""
    print("\nCreating sample data for testing...")

    sample_data = [
        {
            'barcode': '001',
            'product_name': 'Creamy Peanut Butter',
            'brands': 'Test Brand',
            'categories': 'Spread,Nut Butter',
            'text': 'creamy peanut butter spread nut butter test brand',
            'allergens': "['peanuts']",
            'has_allergens': 1,
            'allergen_count': 1
        },
        {
            'barcode': '002',
            'product_name': 'Milk Chocolate Bar',
            'brands': 'Test Brand',
            'categories': 'Confectionery,Chocolate',
            'text': 'milk chocolate bar confectionery chocolate test brand',
            'allergens': "['milk']",
            'has_allergens': 1,
            'allergen_count': 1
        },
        {
            'barcode': '003',
            'product_name': 'Whole Wheat Bread',
            'brands': 'Test Brand',
            'categories': 'Bakery,Bread',
            'text': 'whole wheat bread bakery bread test brand',
            'allergens': "['gluten', 'wheat']",
            'has_allergens': 1,
            'allergen_count': 2
        },
        {
            'barcode': '004',
            'product_name': 'Soy Milk',
            'brands': 'Test Brand',
            'categories': 'Beverages,Milk Alternative',
            'text': 'soy milk beverages milk alternative test brand',
            'allergens': "['soy']",
            'has_allergens': 1,
            'allergen_count': 1
        },
        {
            'barcode': '005',
            'product_name': 'Almond Flour',
            'brands': 'Test Brand',
            'categories': 'Baking,Flour',
            'text': 'almond flour baking flour test brand',
            'allergens': "['almonds', 'tree nuts']",
            'has_allergens': 1,
            'allergen_count': 2
        },
        {
            'barcode': '006',
            'product_name': 'Pure Sea Salt',
            'brands': 'Test Brand',
            'categories': 'Seasoning,Spices',
            'text': 'pure sea salt seasoning spices test brand',
            'allergens': "[]",
            'has_allergens': 0,
            'allergen_count': 0
        },
        {
            'barcode': '007',
            'product_name': 'White Cane Sugar',
            'brands': 'Test Brand',
            'categories': 'Sweetener,Baking',
            'text': 'white cane sugar sweetener baking test brand',
            'allergens': "[]",
            'has_allergens': 0,
            'allergen_count': 0
        },
        {
            'barcode': '008',
            'product_name': 'Spring Water',
            'brands': 'Test Brand',
            'categories': 'Beverages,Water',
            'text': 'spring water beverages water test brand',
            'allergens': "[]",
            'has_allergens': 0,
            'allergen_count': 0
        },
        {
            'barcode': '009',
            'product_name': 'Extra Virgin Olive Oil',
            'brands': 'Test Brand',
            'categories': 'Oils,Cooking',
            'text': 'extra virgin olive oil oils cooking test brand',
            'allergens': "[]",
            'has_allergens': 0,
            'allergen_count': 0
        },
        {
            'barcode': '010',
            'product_name': 'Basmati Rice',
            'brands': 'Test Brand',
            'categories': 'Grains,Rice',
            'text': 'basmati rice grains rice test brand',
            'allergens': "[]",
            'has_allergens': 0,
            'allergen_count': 0
        }
    ]

    print(f"Created {len(sample_data)} sample products (5 positive, 5 negative)")
    return sample_data


def validate_dataset(data):
    """Validate the dataset before saving"""
    print("\nValidating dataset...")

    if not data:
        print("No data to validate")
        return False

    issues = []
    required_cols = ['barcode', 'product_name', 'text', 'has_allergens']
    available_cols = set()
    for row in data:
        available_cols.update(row.keys())

    for col in required_cols:
        if col not in available_cols:
            issues.append(f"Missing required column: {col}")

    if issues:
        print("Issues found:")
        for issue in issues:
            print(f"   • {issue}")
        return False

    null_counts = {}
    for row in data:
        for key, value in row.items():
            if value is None:
                null_counts[key] = null_counts.get(key, 0) + 1
                row[key] = ''

    if null_counts:
        print("Null values found:")
        for col, count in null_counts.items():
            print(f"   • {col}: {count} nulls")

    pos = sum(1 for row in data if row.get('has_allergens') == 1)
    neg = len(data) - pos

    print(f"\nFinal class distribution:")
    print(f"   Positive: {pos} ({pos/len(data)*100:.1f}%)")
    print(f"   Negative: {neg} ({neg/len(data)*100:.1f}%)")

    if pos == 0 or neg == 0:
        print("CRITICAL: Only one class present!")
        return False

    if abs(pos - neg) > len(data) * 0.3:
        print("Warning: Significant class imbalance detected")

    return True


if __name__ == "__main__":
    print("=" * 60)
    print("BITERIGHT - TRAINING DATA EXTRACTION")
    print("=" * 60)

    df = extract_training_data()

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
        balanced_df = create_balanced_dataset(df)

        if validate_dataset(balanced_df):
            save_to_csv(balanced_df, 'training_data_balanced.csv')
            print("\nTraining data preparation complete!")
            print(f"Saved to: training_data_balanced.csv")
            print(f"\nFinal dataset size: {len(balanced_df)} products")
            print("   Used fields: product_name, brands, categories")

            print("\nSample from final dataset:")
            sample = random.sample(balanced_df, min(3, len(balanced_df)))
            for row in sample:
                status = "HAS ALLERGENS" if row.get('has_allergens') == 1 else "SAFE"
                print(f"   • {row['product_name']}: {status}")
        else:
            print("\nDataset validation failed. Please check the issues above.")
