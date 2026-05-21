"""
Import Open Food Facts CSV to SQLite database
This script handles the large CSV file efficiently using streaming
"""

import csv
import sqlite3
import os
from tqdm import tqdm
import time

# Configuration - UPDATE THIS PATH TO YOUR CSV FILE
CSV_FILE = "data/en.openfoodfacts.org.products.csv"
DB_FILE = "data/openfoodfacts.db"
BATCH_SIZE = 10000  # Number of rows to insert per batch

def create_table_schema(conn):
    """Create the main products table with appropriate schema"""
    cursor = conn.cursor()
    
    # Drop existing table if it exists
    cursor.execute("DROP TABLE IF EXISTS products")
    
    # Create table with relevant fields for BiteRight
    cursor.execute('''
        CREATE TABLE products (
            code TEXT PRIMARY KEY,
            product_name TEXT,
            generic_name TEXT,
            brands TEXT,
            categories TEXT,
            categories_tags TEXT,
            ingredients_text TEXT,
            allergens TEXT,
            allergens_en TEXT,
            traces TEXT,
            traces_tags TEXT,
            countries TEXT,
            countries_tags TEXT,
            packaging TEXT,
            labels TEXT,
            image_url TEXT,
            quantity TEXT,
            serving_size TEXT,
            nutrition_grade_fr TEXT,
            created_t INTEGER,
            last_modified_t INTEGER
        )
    ''')
    
    # Create indexes for faster queries
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_categories ON products(categories_tags)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_allergens ON products(allergens_en)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_countries ON products(countries_tags)")
    
    conn.commit()
    print("Table schema created")

def optimize_sqlite(conn):
    """Optimize SQLite for bulk inserts"""
    cursor = conn.cursor()
    cursor.execute("PRAGMA journal_mode = OFF")
    cursor.execute("PRAGMA synchronous = OFF")
    cursor.execute("PRAGMA cache_size = 1000000")
    cursor.execute("PRAGMA locking_mode = EXCLUSIVE")
    cursor.execute("PRAGMA temp_store = MEMORY")
    print("SQLite optimized for bulk insert")

def safe_get(row, indices, field, default=''):
    """Safely get field from row with fallback to default"""
    idx = indices.get(field)
    if idx is not None and idx < len(row):
        # Truncate very long fields to prevent SQLite issues
        value = row[idx] if row[idx] else default
        if len(str(value)) > 1000:
            return str(value)[:1000]
        return value
    return default

def safe_int(row, indices, field, default=None):
    """Safely get integer field"""
    idx = indices.get(field)
    if idx is not None and idx < len(row) and row[idx]:
        try:
            # Handle scientific notation and large numbers
            val_str = row[idx].strip()
            if 'e' in val_str.lower():
                return int(float(val_str))
            return int(val_str)
        except (ValueError, TypeError):
            return default
    return default

def import_csv_to_sqlite():
    """Main import function using streaming to handle large file"""
    
    if not os.path.exists(CSV_FILE):
        print(f"CSV file not found: {CSV_FILE}")
        print("Please make sure the file exists and update the CSV_FILE variable.")
        return
    
    file_size_gb = os.path.getsize(CSV_FILE) / (1024**3)
    print(f"Importing from: {CSV_FILE}")
    print(f"File size: {file_size_gb:.2f} GB")
    print(f"Target database: {DB_FILE}")
    
    # Connect to SQLite
    conn = sqlite3.connect(DB_FILE)
    create_table_schema(conn)
    optimize_sqlite(conn)
    
    cursor = conn.cursor()
    
    # First, count total rows for progress bar
    print("Counting total rows...")
    with open(CSV_FILE, 'r', encoding='utf-8') as f:
        total_rows = sum(1 for _ in f) - 1  # Subtract header row
    print(f"Total rows to process: {total_rows:,}")
    
    # Open CSV and start streaming import
    print("Starting import (this will take 30-60 minutes)...")
    
    start_time = time.time()
    rows_processed = 0
    batch_data = []
    
    try:
        with open(CSV_FILE, 'r', encoding='utf-8') as f:
            # Use csv.reader with tab delimiter (Open Food Facts CSV uses tabs)
            reader = csv.reader(f, delimiter='\t')
            
            # Get header row
            headers = next(reader)
            print(f"CSV columns: {len(headers)} fields")
            
            # Create a mapping of column indices
            col_indices = {name: idx for idx, name in enumerate(headers)}
            
            # Progress bar
            pbar = tqdm(total=total_rows, desc="Importing", unit="rows")
            
            for row in reader:
                if len(row) < len(headers):
                    continue  # Skip incomplete rows
                
                # Extract only the fields we need (for performance)
                try:
                    product_data = (
                        safe_get(row, col_indices, 'code'),
                        safe_get(row, col_indices, 'product_name'),
                        safe_get(row, col_indices, 'generic_name'),
                        safe_get(row, col_indices, 'brands'),
                        safe_get(row, col_indices, 'categories'),
                        safe_get(row, col_indices, 'categories_tags'),
                        safe_get(row, col_indices, 'ingredients_text'),
                        safe_get(row, col_indices, 'allergens'),
                        safe_get(row, col_indices, 'allergens_en'),
                        safe_get(row, col_indices, 'traces'),
                        safe_get(row, col_indices, 'traces_tags'),
                        safe_get(row, col_indices, 'countries'),
                        safe_get(row, col_indices, 'countries_tags'),
                        safe_get(row, col_indices, 'packaging'),
                        safe_get(row, col_indices, 'labels'),
                        safe_get(row, col_indices, 'image_url'),
                        safe_get(row, col_indices, 'quantity'),
                        safe_get(row, col_indices, 'serving_size'),
                        safe_get(row, col_indices, 'nutrition_grade_fr'),
                        safe_int(row, col_indices, 'created_t'),
                        safe_int(row, col_indices, 'last_modified_t')
                    )
                    batch_data.append(product_data)
                    rows_processed += 1
                    
                    # Insert in batches for performance
                    if len(batch_data) >= BATCH_SIZE:
                        cursor.executemany('''
                            INSERT OR REPLACE INTO products VALUES (
                                ?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?
                            )
                        ''', batch_data)
                        conn.commit()
                        batch_data = []
                        
                except Exception as e:
                    print(f"Error processing row {rows_processed}: {e}")
                    continue
                
                pbar.update(1)
            
            # Insert remaining batch
            if batch_data:
                cursor.executemany('''
                    INSERT OR REPLACE INTO products VALUES (
                        ?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?
                    )
                ''', batch_data)
                conn.commit()
            
            pbar.close()
            
    except KeyboardInterrupt:
        print("\nImport interrupted by user. Progress saved up to last batch.")
    except Exception as e:
        print(f"\nFatal error during import: {e}")
    finally:
        elapsed_time = time.time() - start_time
        print(f"\nProcessed {rows_processed:,} rows in {elapsed_time/60:.1f} minutes")
        
        # Get statistics
        cursor.execute("SELECT COUNT(*) FROM products")
        count = cursor.fetchone()[0]
        print(f"Total products in database: {count:,}")
        
        # Sample some allergen data
        cursor.execute("SELECT COUNT(*) FROM products WHERE allergens_en IS NOT NULL AND allergens_en != ''")
        allergen_count = cursor.fetchone()[0]
        print(f"Products with allergen info: {allergen_count:,}")
        
        conn.close()

def create_filtered_views(conn):
    """Create views for common queries (allergens, etc.)"""
    cursor = conn.cursor()
    
    # View for products with allergen information
    cursor.execute('''
        CREATE VIEW IF NOT EXISTS allergen_products AS
        SELECT code, product_name, brands, categories, allergens_en, traces_tags
        FROM products
        WHERE allergens_en IS NOT NULL AND allergens_en != ''
    ''')
    
    # View for products by country
    cursor.execute('''
        CREATE VIEW IF NOT EXISTS products_by_country AS
        SELECT code, product_name, countries_tags
        FROM products
    ''')
    
    conn.commit()
    print("Created filtered views")

def quick_test():
    """Quick test to check if the import worked"""
    if not os.path.exists(DB_FILE):
        print("Database file not found. Run import first.")
        return
    
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    cursor.execute("SELECT COUNT(*) FROM products")
    count = cursor.fetchone()[0]
    print(f"Database contains {count:,} products")
    
    cursor.execute("SELECT COUNT(*) FROM products WHERE allergens_en IS NOT NULL AND allergens_en != ''")
    allergen_count = cursor.fetchone()[0]
    print(f"Products with allergens: {allergen_count:,}")
    
    cursor.execute("SELECT code, product_name, allergens_en FROM products WHERE allergens_en IS NOT NULL AND allergens_en != '' LIMIT 5")
    samples = cursor.fetchall()
    print("\nSample products with allergens:")
    for sample in samples:
        print(f"   - {sample[1]}: {sample[2][:50]}...")
    
    conn.close()

if __name__ == "__main__":
    print("="*60)
    print("BITERIGHT - OPEN FOOD FACTS CSV TO SQLITE IMPORT")
    print("="*60)
    
    # Ask user what to do
    print("\nOptions:")
    print("1. Run full import (will take 30-60 minutes)")
    print("2. Quick test (check existing database)")
    print("3. Exit")
    
    choice = input("\nEnter choice (1, 2, or 3): ").strip()
    
    if choice == '1':
        import_csv_to_sqlite()
        # After import, create views
        if os.path.exists(DB_FILE):
            conn = sqlite3.connect(DB_FILE)
            create_filtered_views(conn)
            conn.close()
    elif choice == '2':
        quick_test()
    else:
        print("Exiting...")