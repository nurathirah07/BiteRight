"""
Extract training data from Firebase for ML model training
FIXED: Better synthetic negative sample generation and proper balancing
"""

import csv
import firebase_admin
from firebase_admin import credentials, firestore
from collections import Counter
import random
import re

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


def clean_text(text):
    """Clean text for better ML training"""
    if not text:
        return ""
    text = str(text).lower()
    # Remove special characters but keep important ones
    text = re.sub(r'[^a-z0-9\s]', ' ', text)
    # Remove extra spaces
    text = re.sub(r'\s+', ' ', text).strip()
    return text


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
        
        # Get ingredients text - this is more reliable than product_name only
        ingredients_text = product_data.get('ingredients_text', '') or ''
        ingredients_text_en = product_data.get('ingredients_text_en', '') or ''

        allergens = product_data.get('allergens', [])
        if not isinstance(allergens, list):
            allergens = parse_allergens(allergens)

        has_allergens = bool(product_data.get('has_allergens', False))
        
        # Combine multiple text sources for better training
        text_for_ml = f"{product_name} {categories} {brands} {ingredients_text} {ingredients_text_en}".lower().strip()
        text_for_ml = clean_text(text_for_ml)

        if len(text_for_ml) > 20:  # Require meaningful text
            data.append({
                'barcode': barcode,
                'product_name': product_name,
                'brands': brands,
                'categories': categories,
                'ingredients': ingredients_text[:500],  # Limit length
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

    save_to_csv(data, 'training_data_raw.csv')
    print("Saved raw training data to training_data_raw.csv")

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


def create_high_quality_synthetic_negatives(positive_count):
    """
    Create HIGH QUALITY synthetic negative samples
    These are REAL examples of safe products
    """
    
    # Expanded list of truly safe products (no common allergens)
    safe_products = [
        # Pure single ingredients
        {'product_name': 'Pure Sea Salt', 'brands': 'Generic', 'categories': 'Seasoning', 
         'text': 'sea salt sodium chloride', 'allergens': '[]', 'has_allergens': 0},
        {'product_name': 'White Sugar', 'brands': 'Generic', 'categories': 'Sweetener', 
         'text': 'sugar cane sucrose sweetener', 'allergens': '[]', 'has_allergens': 0},
        {'product_name': 'Brown Sugar', 'brands': 'Generic', 'categories': 'Sweetener', 
         'text': 'brown sugar molasses cane sugar', 'allergens': '[]', 'has_allergens': 0},
        {'product_name': 'Powdered Sugar', 'brands': 'Generic', 'categories': 'Sweetener', 
         'text': 'confectioners sugar corn starch', 'allergens': '[]', 'has_allergens': 0},
        {'product_name': 'White Rice', 'brands': 'Generic', 'categories': 'Grains', 
         'text': 'long grain white rice', 'allergens': '[]', 'has_allergens': 0},
        {'product_name': 'Brown Rice', 'brands': 'Generic', 'categories': 'Grains', 
         'text': 'whole grain brown rice', 'allergens': '[]', 'has_allergens': 0},
        {'product_name': 'Jasmine Rice', 'brands': 'Generic', 'categories': 'Grains', 
         'text': 'jasmine fragrant rice', 'allergens': '[]', 'has_allergens': 0},
        {'product_name': 'Basmati Rice', 'brands': 'Generic', 'categories': 'Grains', 
         'text': 'basmati long grain rice', 'allergens': '[]', 'has_allergens': 0},
        {'product_name': 'Extra Virgin Olive Oil', 'brands': 'Generic', 'categories': 'Oils', 
         'text': 'cold pressed olive oil', 'allergens': '[]', 'has_allergens': 0},
        {'product_name': 'Coconut Oil', 'brands': 'Generic', 'categories': 'Oils', 
         'text': 'virgin coconut oil', 'allergens': '[]', 'has_allergens': 0},
        {'product_name': 'Canola Oil', 'brands': 'Generic', 'categories': 'Oils', 
         'text': 'vegetable canola oil', 'allergens': '[]', 'has_allergens': 0},
        {'product_name': 'Sunflower Oil', 'brands': 'Generic', 'categories': 'Oils', 
         'text': 'high oleic sunflower oil', 'allergens': '[]', 'has_allergens': 0},
        {'product_name': 'Avocado Oil', 'brands': 'Generic', 'categories': 'Oils', 
         'text': 'pure avocado oil', 'allergens': '[]', 'has_allergens': 0},
        {'product_name': 'Distilled White Vinegar', 'brands': 'Generic', 'categories': 'Condiment', 
         'text': 'white vinegar acetic acid water', 'allergens': '[]', 'has_allergens': 0},
        {'product_name': 'Apple Cider Vinegar', 'brands': 'Generic', 'categories': 'Condiment', 
         'text': 'raw unfiltered apple cider vinegar', 'allergens': '[]', 'has_allergens': 0},
        {'product_name': 'Baking Soda', 'brands': 'Generic', 'categories': 'Baking', 
         'text': 'sodium bicarbonate pure', 'allergens': '[]', 'has_allergens': 0},
        {'product_name': 'Baking Powder', 'brands': 'Generic', 'categories': 'Baking', 
         'text': 'monocalcium phosphate sodium bicarbonate corn starch', 'allergens': '[]', 'has_allergens': 0},
        {'product_name': 'Corn Starch', 'brands': 'Generic', 'categories': 'Thickener', 
         'text': 'pure corn starch', 'allergens': '[]', 'has_allergens': 0},
        {'product_name': 'Tapioca Starch', 'brands': 'Generic', 'categories': 'Thickener', 
         'text': 'cassava root tapioca flour', 'allergens': '[]', 'has_allergens': 0},
        {'product_name': 'Potato Starch', 'brands': 'Generic', 'categories': 'Thickener', 
         'text': 'potato starch', 'allergens': '[]', 'has_allergens': 0},
        {'product_name': 'Spring Water', 'brands': 'Generic', 'categories': 'Beverages', 
         'text': 'natural spring water', 'allergens': '[]', 'has_allergens': 0},
        {'product_name': 'Sparkling Water', 'brands': 'Generic', 'categories': 'Beverages', 
         'text': 'carbonated water', 'allergens': '[]', 'has_allergens': 0},
        {'product_name': 'Club Soda', 'brands': 'Generic', 'categories': 'Beverages', 
         'text': 'carbonated water sodium bicarbonate', 'allergens': '[]', 'has_allergens': 0},
        {'product_name': 'Tonic Water', 'brands': 'Generic', 'categories': 'Beverages', 
         'text': 'carbonated water quinine sugar', 'allergens': '[]', 'has_allergens': 0},
        {'product_name': 'Black Coffee', 'brands': 'Generic', 'categories': 'Beverages', 
         'text': 'arabica coffee beans', 'allergens': '[]', 'has_allergens': 0},
        {'product_name': 'Green Tea', 'brands': 'Generic', 'categories': 'Beverages', 
         'text': 'green tea leaves', 'allergens': '[]', 'has_allergens': 0},
        {'product_name': 'Black Tea', 'brands': 'Generic', 'categories': 'Beverages', 
         'text': 'black tea leaves', 'allergens': '[]', 'has_allergens': 0},
        {'product_name': 'Herbal Tea', 'brands': 'Generic', 'categories': 'Beverages', 
         'text': 'chamomile peppermint hibiscus', 'allergens': '[]', 'has_allergens': 0},
        {'product_name': 'Ground Black Pepper', 'brands': 'Generic', 'categories': 'Spice', 
         'text': 'black peppercorns', 'allergens': '[]', 'has_allergens': 0},
        {'product_name': 'Sea Salt Grinder', 'brands': 'Generic', 'categories': 'Spice', 
         'text': 'coarse sea salt', 'allergens': '[]', 'has_allergens': 0},
        {'product_name': 'Pure Honey', 'brands': 'Generic', 'categories': 'Sweetener', 
         'text': 'raw wildflower honey', 'allergens': '[]', 'has_allergens': 0},
        {'product_name': 'Maple Syrup', 'brands': 'Generic', 'categories': 'Sweetener', 
         'text': 'pure maple syrup grade a', 'allergens': '[]', 'has_allergens': 0},
        {'product_name': 'Agave Nectar', 'brands': 'Generic', 'categories': 'Sweetener', 
         'text': 'blue agave syrup', 'allergens': '[]', 'has_allergens': 0},
        {'product_name': 'Coconut Sugar', 'brands': 'Generic', 'categories': 'Sweetener', 
         'text': 'coconut palm sugar', 'allergens': '[]', 'has_allergens': 0},
        {'product_name': 'Date Sugar', 'brands': 'Generic', 'categories': 'Sweetener', 
         'text': 'dried ground dates', 'allergens': '[]', 'has_allergens': 0},
        {'product_name': 'Cocoa Powder', 'brands': 'Generic', 'categories': 'Baking', 
         'text': 'unsweetened cocoa powder', 'allergens': '[]', 'has_allergens': 0},
        {'product_name': 'Vanilla Extract', 'brands': 'Generic', 'categories': 'Flavoring', 
         'text': 'vanilla bean extract alcohol water', 'allergens': '[]', 'has_allergens': 0},
        {'product_name': 'Lemon Juice', 'brands': 'Generic', 'categories': 'Condiment', 
         'text': 'pure lemon juice', 'allergens': '[]', 'has_allergens': 0},
        {'product_name': 'Lime Juice', 'brands': 'Generic', 'categories': 'Condiment', 
         'text': 'pure lime juice', 'allergens': '[]', 'has_allergens': 0},
        {'product_name': 'Coconut Water', 'brands': 'Generic', 'categories': 'Beverages', 
         'text': 'pure coconut water', 'allergens': '[]', 'has_allergens': 0},
    ]
    
    # Ensure we have enough safe products
    synthetic_negatives = []
    safe_products_copy = safe_products.copy()
    
    # If we need more than available, repeat with variations
    while len(synthetic_negatives) < positive_count:
        for base in safe_products_copy:
            if len(synthetic_negatives) >= positive_count:
                break
            synthetic = base.copy()
            
            # Add variety to avoid identical entries
            variations = ['', ' Organic', ' Premium', ' Fine', ' Pure', ' Natural', ' Premium Quality']
            suffix = random.choice(variations)
            synthetic['product_name'] = base['product_name'] + suffix
            
            # Add random brand names
            brands = ['Generic', 'Simple', 'Pure', 'Natural', 'Basic', 'Essential', 'Classic']
            synthetic['brands'] = random.choice(brands)
            
            # Shuffle text words for variety
            words = synthetic['text'].split()
            if len(words) > 2 and random.random() > 0.5:
                random.shuffle(words)
                synthetic['text'] = ' '.join(words)
            
            synthetic['barcode'] = f"SYNTHETIC_NEG_{len(synthetic_negatives):04d}"
            synthetic['allergen_count'] = 0
            synthetic_negatives.append(synthetic)
    
    return synthetic_negatives[:positive_count]


def create_high_quality_synthetic_positives(negative_count):
    """
    Create HIGH QUALITY synthetic positive samples (products WITH allergens)
    """
    
    allergen_products = [
        # Peanut products
        {'product_name': 'Peanut Butter', 'brands': 'Generic', 'categories': 'Spread',
         'text': 'roasted peanuts sugar salt peanut butter', 'allergens': "['peanuts']", 'has_allergens': 1},
        {'product_name': 'Salted Peanuts', 'brands': 'Generic', 'categories': 'Snack',
         'text': 'peanuts vegetable oil salt', 'allergens': "['peanuts']", 'has_allergens': 1},
        {'product_name': 'Honey Roasted Peanuts', 'brands': 'Generic', 'categories': 'Snack',
         'text': 'peanuts sugar honey salt peanut oil', 'allergens': "['peanuts']", 'has_allergens': 1},
        
        # Milk/Dairy products
        {'product_name': 'Whole Milk', 'brands': 'Generic', 'categories': 'Dairy',
         'text': 'grade a milk vitamin d3', 'allergens': "['milk']", 'has_allergens': 1},
        {'product_name': 'Cheddar Cheese', 'brands': 'Generic', 'categories': 'Dairy',
         'text': 'cultured milk salt enzymes annatto', 'allergens': "['milk']", 'has_allergens': 1},
        {'product_name': 'Greek Yogurt', 'brands': 'Generic', 'categories': 'Dairy',
         'text': 'cultured milk cream live active cultures', 'allergens': "['milk']", 'has_allergens': 1},
        {'product_name': 'Butter', 'brands': 'Generic', 'categories': 'Dairy',
         'text': 'cream salt', 'allergens': "['milk']", 'has_allergens': 1},
        {'product_name': 'Whey Protein Powder', 'brands': 'Generic', 'categories': 'Supplement',
         'text': 'whey protein isolate soy lecithin', 'allergens': "['milk', 'soy']", 'has_allergens': 1},
        
        # Wheat/Gluten products
        {'product_name': 'White Bread', 'brands': 'Generic', 'categories': 'Bakery',
         'text': 'enriched wheat flour water yeast sugar salt', 'allergens': "['wheat', 'gluten']", 'has_allergens': 1},
        {'product_name': 'Whole Wheat Bread', 'brands': 'Generic', 'categories': 'Bakery',
         'text': 'whole wheat flour water honey yeast salt', 'allergens': "['wheat', 'gluten']", 'has_allergens': 1},
        {'product_name': 'Spaghetti Pasta', 'brands': 'Generic', 'categories': 'Pasta',
         'text': 'durum wheat semolina', 'allergens': "['wheat', 'gluten']", 'has_allergens': 1},
        {'product_name': 'All Purpose Flour', 'brands': 'Generic', 'categories': 'Baking',
         'text': 'wheat flour niacin iron thiamin riboflavin folic acid', 'allergens': "['wheat', 'gluten']", 'has_allergens': 1},
        
        # Soy products
        {'product_name': 'Soy Sauce', 'brands': 'Generic', 'categories': 'Condiment',
         'text': 'water soybeans wheat salt sodium benzoate', 'allergens': "['soy', 'wheat']", 'has_allergens': 1},
        {'product_name': 'Tofu', 'brands': 'Generic', 'categories': 'Protein',
         'text': 'soybeans water calcium sulfate', 'allergens': "['soy']", 'has_allergens': 1},
        {'product_name': 'Soy Milk', 'brands': 'Generic', 'categories': 'Beverage',
         'text': 'soybeans water cane sugar calcium carbonate', 'allergens': "['soy']", 'has_allergens': 1},
        {'product_name': 'Edamame', 'brands': 'Generic', 'categories': 'Snack',
         'text': 'whole soybeans salt', 'allergens': "['soy']", 'has_allergens': 1},
        
        # Egg products
        {'product_name': 'Large Eggs', 'brands': 'Generic', 'categories': 'Dairy',
         'text': 'grade a eggs', 'allergens': "['eggs']", 'has_allergens': 1},
        {'product_name': 'Mayonnaise', 'brands': 'Generic', 'categories': 'Condiment',
         'text': 'soybean oil eggs vinegar water salt sugar', 'allergens': "['eggs', 'soy']", 'has_allergens': 1},
        
        # Tree nut products
        {'product_name': 'Raw Almonds', 'brands': 'Generic', 'categories': 'Snack',
         'text': 'california almonds', 'allergens': "['tree_nuts']", 'has_allergens': 1},
        {'product_name': 'Almond Milk', 'brands': 'Generic', 'categories': 'Beverage',
         'text': 'water almonds cane sugar calcium carbonate', 'allergens': "['tree_nuts']", 'has_allergens': 1},
        {'product_name': 'Cashews', 'brands': 'Generic', 'categories': 'Snack',
         'text': 'cashew nuts', 'allergens': "['tree_nuts']", 'has_allergens': 1},
        {'product_name': 'Walnuts', 'brands': 'Generic', 'categories': 'Snack',
         'text': 'english walnuts', 'allergens': "['tree_nuts']", 'has_allergens': 1},
        
        # Fish products
        {'product_name': 'Canned Tuna', 'brands': 'Generic', 'categories': 'Seafood',
         'text': 'skipjack tuna water salt', 'allergens': "['fish']", 'has_allergens': 1},
        {'product_name': 'Salmon Fillet', 'brands': 'Generic', 'categories': 'Seafood',
         'text': 'atlantic salmon', 'allergens': "['fish']", 'has_allergens': 1},
        
        # Sesame products
        {'product_name': 'Sesame Seeds', 'brands': 'Generic', 'categories': 'Spice',
         'text': 'white sesame seeds', 'allergens': "['sesame']", 'has_allergens': 1},
        {'product_name': 'Tahini', 'brands': 'Generic', 'categories': 'Spread',
         'text': 'ground sesame seeds', 'allergens': "['sesame']", 'has_allergens': 1},
        
        # Mixed allergen products
        {'product_name': 'Chocolate Chip Cookies', 'brands': 'Generic', 'categories': 'Bakery',
         'text': 'wheat flour sugar butter eggs chocolate chips vanilla', 'allergens': "['wheat', 'milk', 'eggs']", 'has_allergens': 1},
        {'product_name': 'Ice Cream', 'brands': 'Generic', 'categories': 'Dessert',
         'text': 'milk cream sugar vanilla bean', 'allergens': "['milk']", 'has_allergens': 1},
        {'product_name': 'Breakfast Cereal', 'brands': 'Generic', 'categories': 'Cereal',
         'text': 'whole grain wheat sugar corn syrup honey', 'allergens': "['wheat', 'gluten']", 'has_allergens': 1},
    ]
    
    synthetic_positives = []
    allergen_products_copy = allergen_products.copy()
    
    while len(synthetic_positives) < negative_count:
        for base in allergen_products_copy:
            if len(synthetic_positives) >= negative_count:
                break
            synthetic = base.copy()
            
            # Add variety
            variations = ['', ' Classic', ' Original', ' Premium', ' Family Size']
            suffix = random.choice(variations)
            synthetic['product_name'] = base['product_name'] + suffix
            
            synthetic['barcode'] = f"SYNTHETIC_POS_{len(synthetic_positives):04d}"
            synthetic_positives.append(synthetic)
    
    return synthetic_positives[:negative_count]


def create_balanced_dataset(data):
    """Create a perfectly balanced dataset for training"""
    if not data:
        print("No data to balance")
        return data

    # Separate positive and negative from real data
    positive = [item for item in data if item.get('has_allergens') == 1]
    negative = [item for item in data if item.get('has_allergens') == 0]

    print(f"\nReal data statistics:")
    print(f"   Positive samples: {len(positive)}")
    print(f"   Negative samples: {len(negative)}")

    # We want balanced dataset (50% positive, 50% negative)
    target_size = max(len(positive), len(negative))
    
    # Enhance with high-quality synthetic samples if needed
    if len(positive) < target_size:
        print(f"\nCreating {target_size - len(positive)} synthetic positive samples...")
        synthetic_positives = create_high_quality_synthetic_positives(target_size - len(positive))
        positive.extend(synthetic_positives)
        print(f"   Added {len(synthetic_positives)} synthetic positive samples")
    
    if len(negative) < target_size:
        print(f"\nCreating {target_size - len(negative)} synthetic negative samples...")
        synthetic_negatives = create_high_quality_synthetic_negatives(target_size - len(negative))
        negative.extend(synthetic_negatives)
        print(f"   Added {len(synthetic_negatives)} synthetic negative samples")
    
    # Ensure exactly balanced
    final_size = min(len(positive), len(negative))
    positive = positive[:final_size]
    negative = negative[:final_size]
    
    # Combine and shuffle
    balanced_data = positive + negative
    random.Random(42).shuffle(balanced_data)

    final_positives = sum(item['has_allergens'] for item in balanced_data)
    final_negatives = len(balanced_data) - final_positives

    print(f"\nAfter balancing:")
    print(f"   Total samples: {len(balanced_data)}")
    print(f"   Positive (has allergens): {final_positives}")
    print(f"   Negative (no allergens): {final_negatives}")
    print(f"   Balance ratio: {final_positives/final_negatives:.2f}")

    return balanced_data


def create_sample_data():
    """Create sample data for testing if no real data exists"""
    print("\nCreating enhanced sample data for training...")
    
    # Create sample data using the synthetic generators
    sample_positives = create_high_quality_synthetic_positives(25)
    sample_negatives = create_high_quality_synthetic_negatives(25)
    
    sample_data = sample_positives + sample_negatives
    random.Random(42).shuffle(sample_data)
    
    print(f"Created {len(sample_data)} sample products")
    print(f"   Positive: {sum(1 for item in sample_data if item['has_allergens'] == 1)}")
    print(f"   Negative: {sum(1 for item in sample_data if item['has_allergens'] == 0)}")
    
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

    pos = sum(1 for row in data if row.get('has_allergens') == 1)
    neg = len(data) - pos

    print(f"\nFinal class distribution:")
    print(f"   Positive (has allergens): {pos} ({pos/len(data)*100:.1f}%)")
    print(f"   Negative (no allergens): {neg} ({neg/len(data)*100:.1f}%)")

    if pos == 0 or neg == 0:
        print("CRITICAL: Only one class present!")
        return False

    # Check for quality issues
    short_texts = sum(1 for row in data if len(row.get('text', '')) < 10)
    if short_texts > 0:
        print(f"⚠️ Warning: {short_texts} samples have very short text (<10 chars)")

    return True


if __name__ == "__main__":
    print("=" * 60)
    print("BITERIGHT - TRAINING DATA EXTRACTION (FIXED)")
    print("=" * 60)
    print("\nThis script creates a HIGH QUALITY balanced dataset for ML training.")
    print("It generates realistic synthetic samples for both safe and unsafe products.\n")

    # Try to extract real data from Firebase
    df = extract_training_data()

    if len(df) == 0:
        print("\nNo real data found in Firebase.")
        print("Creating enhanced synthetic dataset for training...")
        df = create_sample_data()
    else:
        # Analyze existing data
        analyze_allergen_distribution(df)

    if len(df) > 0:
        # Create balanced dataset with synthetic samples
        balanced_df = create_balanced_dataset(df)

        if validate_dataset(balanced_df):
            save_to_csv(balanced_df, 'training_data_balanced.csv')
            print("\n" + "=" * 60)
            print("✅ TRAINING DATA PREPARATION COMPLETE!")
            print("=" * 60)
            print(f"Saved to: training_data_balanced.csv")
            print(f"\nFinal dataset size: {len(balanced_df)} products")
            print(f"   Positive examples: {sum(1 for item in balanced_df if item['has_allergens'] == 1)}")
            print(f"   Negative examples: {sum(1 for item in balanced_df if item['has_allergens'] == 0)}")
            print("\nNext steps:")
            print("   1. Run: python retrain_model.py")
            print("   2. Then: python test_accuracy.py")
        else:
            print("\n❌ Dataset validation failed. Please check the issues above.")
    else:
        print("\n❌ Failed to create training data.")