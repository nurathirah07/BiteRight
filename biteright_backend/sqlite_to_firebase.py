"""
Export SQLite data to Firebase Firestore
"""

import sqlite3
import firebase_admin
from firebase_admin import credentials, firestore
from tqdm import tqdm
import pandas as pd
import os

# Initialize Firebase
cred = credentials.Certificate('serviceAccountKey.json')
firebase_admin.initialize_app(cred)
db = firestore.client()

# Database path
DB_FILE = "data/openfoodfacts.db"

def export_allergens_to_firestore():
    """Export allergen information to Firestore"""
    
    if not os.path.exists(DB_FILE):
        print(f"Database file not found: {DB_FILE}")
        return
    
    conn = sqlite3.connect(DB_FILE)
    
    print("Loading products with allergen info from SQLite...")
    
    # Use the correct column 'allergens' instead of 'allergens_en'
    query = """
        SELECT code, product_name, brands, categories, allergens, traces_tags
        FROM products 
        WHERE allergens IS NOT NULL AND allergens != ''
        LIMIT 1000  -- Start with 1000 for testing, remove for full export
    """
    
    df = pd.read_sql_query(query, conn)
    print(f"Found {len(df)} products with allergen information")
    
    if len(df) == 0:
        print("No allergen data found in database.")
        conn.close()
        return
    
    print(f"Exporting {len(df)} products to Firebase...")
    
    # Use batched writes for efficiency
    batch = db.batch()
    count = 0
    batch_size = 500  # Firestore batch limit
    
    for _, row in tqdm(df.iterrows(), total=len(df), desc="Uploading to Firebase"):
        # Parse allergens (they're comma-separated)
        allergen_str = row['allergens'] or ''
        # Clean and split allergens
        allergen_list = []
        for a in allergen_str.split(','):
            a = a.strip()
            if a and len(a) > 1:
                # Remove common prefixes like 'en:' if present
                if ':' in a:
                    a = a.split(':')[-1]
                allergen_list.append(a)
        
        # Parse traces
        traces_str = row['traces_tags'] or ''
        traces_list = [t.strip() for t in traces_str.split(',') if t.strip()]
        
        # Create document data
        product_data = {
            'barcode': row['code'],
            'product_name': row['product_name'] or 'Unknown Product',
            'brands': row['brands'] or 'Unknown Brand',
            'categories': row['categories'] or 'Unknown Category',
            'allergens': allergen_list,
            'traces': traces_list,
            'has_allergens': len(allergen_list) > 0,
            'updated_at': firestore.SERVER_TIMESTAMP
        }
        
        # Use barcode as document ID
        doc_ref = db.collection('openfoodfacts_products').document(row['code'])
        batch.set(doc_ref, product_data)
        count += 1
        
        # Commit batch when full
        if count % batch_size == 0:
            batch.commit()
            print(f"Committed {count} documents")
            batch = db.batch()
    
    # Final commit
    if count % batch_size != 0:
        batch.commit()
    
    print(f"Successfully uploaded {count} products to Firebase!")
    conn.close()

def export_allergen_summary():
    """Create a summary collection of unique allergens"""
    
    conn = sqlite3.connect(DB_FILE)
    
    print("Generating allergen summary...")
    
    # Use 'allergens' column instead of 'allergens_en'
    df = pd.read_sql_query("""
        SELECT allergens, COUNT(*) as frequency
        FROM products
        WHERE allergens IS NOT NULL AND allergens != ''
        GROUP BY allergens
        ORDER BY frequency DESC
    """, conn)
    
    print(f"Found {len(df)} unique allergen combinations")
    
    # Parse and normalize allergens
    allergen_summary = {}
    for _, row in tqdm(df.iterrows(), total=len(df), desc="Processing allergens"):
        allergen_str = row['allergens']
        frequency = row['frequency']
        
        if not allergen_str:
            continue
            
        # Split by comma and clean
        for allergen in allergen_str.split(','):
            allergen = allergen.strip().lower()
            # Remove common prefixes
            if ':' in allergen:
                allergen = allergen.split(':')[-1]
            if allergen and len(allergen) > 1:
                if allergen in allergen_summary:
                    allergen_summary[allergen] += frequency
                else:
                    allergen_summary[allergen] = frequency
    
    print(f"Generated {len(allergen_summary)} unique allergen entries")
    
    # Upload to Firebase
    batch = db.batch()
    count = 0
    batch_size = 500
    
    print(f"Uploading allergen summary to Firebase...")
    
    for allergen, freq in tqdm(allergen_summary.items(), desc="Uploading allergens"):
        allergen_keyword = allergen.replace(' ', '_')
        doc_ref = db.collection('master_allergens').document(allergen_keyword)
        batch.set(doc_ref, {
            'allergen_keyword': allergen_keyword,
            'standard_name': allergen,
            'frequency': freq,
            'category': categorize_allergen(allergen),
            'synonym_list': [allergen],
            'updated_at': firestore.SERVER_TIMESTAMP
        })
        count += 1
        
        if count % batch_size == 0:
            batch.commit()
            batch = db.batch()
    
    if count % batch_size != 0:
        batch.commit()
    
    print(f"Uploaded {count} allergen summaries")
    conn.close()

def export_full_dataset():
    """Export ALL products with allergen data (no limit)"""
    
    if not os.path.exists(DB_FILE):
        print(f"Database file not found: {DB_FILE}")
        return
    
    conn = sqlite3.connect(DB_FILE)
    
    print("Loading ALL products with allergen info from SQLite...")
    
    # Remove the LIMIT to get all products
    query = """
        SELECT code, product_name, brands, categories, allergens, traces_tags
        FROM products 
        WHERE allergens IS NOT NULL AND allergens != ''
    """
    
    df = pd.read_sql_query(query, conn)
    total_products = len(df)
    print(f"Found {total_products} products with allergen information")
    
    if total_products == 0:
        print("No allergen data found in database.")
        conn.close()
        return
    
    print(f"Exporting {total_products} products to Firebase...")
    print("This may take a while and use Firestore quota!")
    
    # Ask for confirmation
    confirm = input(f"Export {total_products} products? (y/n): ")
    if confirm.lower() != 'y':
        print("Export cancelled.")
        conn.close()
        return
    
    # Use batched writes for efficiency
    batch = db.batch()
    count = 0
    batch_size = 500
    
    for _, row in tqdm(df.iterrows(), total=total_products, desc="Uploading to Firebase"):
        # Parse allergens
        allergen_str = row['allergens'] or ''
        allergen_list = []
        for a in allergen_str.split(','):
            a = a.strip()
            if a and len(a) > 1:
                if ':' in a:
                    a = a.split(':')[-1]
                allergen_list.append(a)
        
        # Parse traces
        traces_str = row['traces_tags'] or ''
        traces_list = [t.strip() for t in traces_str.split(',') if t.strip()]
        
        product_data = {
            'barcode': row['code'],
            'product_name': row['product_name'] or 'Unknown Product',
            'brands': row['brands'] or 'Unknown Brand',
            'categories': row['categories'] or 'Unknown Category',
            'allergens': allergen_list,
            'traces': traces_list,
            'has_allergens': len(allergen_list) > 0,
            'updated_at': firestore.SERVER_TIMESTAMP
        }
        
        doc_ref = db.collection('openfoodfacts_products').document(row['code'])
        batch.set(doc_ref, product_data)
        count += 1
        
        if count % batch_size == 0:
            batch.commit()
            print(f"Committed {count}/{total_products} documents")
            batch = db.batch()
    
    if count % batch_size != 0:
        batch.commit()
    
    print(f"Successfully uploaded {count} products to Firebase!")
    conn.close()

def categorize_allergen(allergen):
    """Categorize allergen type"""
    allergen_lower = allergen.lower()
    
    categories = {
        'nuts': ['peanut', 'almond', 'walnut', 'cashew', 'pecan', 'hazelnut', 'nut'],
        'dairy': ['milk', 'dairy', 'lactose', 'casein', 'whey', 'cream', 'cheese', 'yogurt'],
        'eggs': ['egg', 'albumin', 'ovalbumin'],
        'soy': ['soy', 'soya', 'tofu', 'tempeh', 'lecithin'],
        'gluten': ['gluten', 'wheat', 'barley', 'rye', 'oats', 'spelt'],
        'fish': ['fish', 'salmon', 'tuna', 'cod', 'mackerel'],
        'shellfish': ['shrimp', 'crab', 'lobster', 'prawn', 'shellfish'],
        'sesame': ['sesame', 'tahini'],
        'sulfites': ['sulfite', 'sulphite', 'sulfur dioxide'],
        'celery': ['celery', 'celeriac'],
        'mustard': ['mustard'],
        'lupin': ['lupin'],
        'molluscs': ['mollusc', 'oyster', 'clam', 'mussel', 'scallop']
    }
    
    for category, keywords in categories.items():
        for keyword in keywords:
            if keyword in allergen_lower:
                return category
    
    return 'other'

def check_firebase_connection():
    """Test Firebase connection"""
    try:
        test_ref = db.collection('_test_').document('connection_test')
        test_ref.set({'timestamp': firestore.SERVER_TIMESTAMP})
        test_ref.delete()
        print("Firebase connection successful!")
        return True
    except Exception as e:
        print(f"Firebase connection failed: {e}")
        return False

if __name__ == "__main__":
    print("="*60)
    print("BITERIGHT - SQLITE TO FIREBASE EXPORT")
    print("="*60)
    
    # Check Firebase connection first
    if not check_firebase_connection():
        print("\nPlease check your serviceAccountKey.json file and Firebase configuration.")
        exit(1)
    
    print(f"\nDatabase has 3,258 total products")
    print(f"Products with allergens: 121")
    
    print("\nOptions:")
    print("1. Export test batch (121 products with allergens)")
    print("2. Export allergen summary statistics")
    print("3. Export full dataset (all 121 products)")
    print("4. Exit")
    
    choice = input("\nEnter choice (1, 2, 3, or 4): ").strip()
    
    if choice == '1':
        export_allergens_to_firestore()  # This will export the 121 products
    elif choice == '2':
        export_allergen_summary()
    elif choice == '3':
        export_full_dataset()
    else:
        print("Exiting...")
