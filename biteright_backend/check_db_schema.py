"""
Check SQLite database schema and sample data
"""

import sqlite3
import os

DB_FILE = "data/openfoodfacts.db"

if not os.path.exists(DB_FILE):
    print(f"Database file not found: {DB_FILE}")
    exit(1)

conn = sqlite3.connect(DB_FILE)
cursor = conn.cursor()

# Get table schema
cursor.execute("PRAGMA table_info(products)")
columns = cursor.fetchall()
print("\n=== TABLE SCHEMA ===")
print("Column Name".ljust(25), "Type".ljust(15))
print("-" * 40)
for col in columns:
    print(f"{col[1].ljust(25)} {col[2].ljust(15)}")

# Check total rows
cursor.execute("SELECT COUNT(*) FROM products")
total = cursor.fetchone()[0]
print(f"\n=== STATISTICS ===")
print(f"Total products: {total:,}")

# Check allergen-related columns
allergen_columns = ['allergens', 'allergens_en', 'allergens_tags', 'allergen']
for col in allergen_columns:
    try:
        cursor.execute(f"SELECT COUNT(*) FROM products WHERE {col} IS NOT NULL AND {col} != ''")
        count = cursor.fetchone()[0]
        print(f"Products with {col}: {count:,} ({count/total*100:.1f}% if total>0 else 0)")
    except sqlite3.OperationalError:
        print(f"Column {col} does not exist")

# Show sample of what's in the database
print("\n=== SAMPLE PRODUCTS (first 5) ===")
cursor.execute("""
    SELECT code, product_name, allergens_en, allergens, ingredients_text 
    FROM products 
    LIMIT 5
""")
samples = cursor.fetchall()
for i, sample in enumerate(samples, 1):
    print(f"\n{i}. Code: {sample[0]}")
    print(f"   Name: {sample[1]}")
    print(f"   Allergens_en: {sample[2]}")
    print(f"   Allergens: {sample[3]}")
    print(f"   Ingredients: {str(sample[4])[:100]}...")

conn.close()