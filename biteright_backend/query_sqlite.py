"""
Query SQLite database to verify and explore the Open Food Facts data
"""

import sqlite3
import os
from tabulate import tabulate

# Database path
DB_FILE = "data/openfoodfacts.db"

def check_database_exists():
    """Check if the database file exists"""
    if not os.path.exists(DB_FILE):
        print(f"Database file not found: {DB_FILE}")
        print("Please run import_csv_to_sqlite.py first to create the database.")
        return False
    return True

def get_basic_stats():
    """Get basic statistics about the database"""
    print("\n" + "="*60)
    print("DATABASE STATISTICS")
    print("="*60)
    
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    # Total products
    cursor.execute("SELECT COUNT(*) FROM products")
    total = cursor.fetchone()[0]
    print(f"Total products: {total:,}")
    
    # Products with allergens
    cursor.execute("SELECT COUNT(*) FROM products WHERE allergens_en IS NOT NULL AND allergens_en != ''")
    with_allergens = cursor.fetchone()[0]
    print(f"Products with allergen info: {with_allergens:,} ({with_allergens/total*100:.1f}%)")
    
    # Products with ingredients
    cursor.execute("SELECT COUNT(*) FROM products WHERE ingredients_text IS NOT NULL AND ingredients_text != ''")
    with_ingredients = cursor.fetchone()[0]
    print(f"Products with ingredients: {with_ingredients:,} ({with_ingredients/total*100:.1f}%)")
    
    # Unique brands
    cursor.execute("SELECT COUNT(DISTINCT brands) FROM products WHERE brands IS NOT NULL AND brands != ''")
    brands = cursor.fetchone()[0]
    print(f"Unique brands: {brands:,}")
    
    # Database size
    db_size = os.path.getsize(DB_FILE) / (1024**3)
    print(f"Database size: {db_size:.2f} GB")
    
    conn.close()
    return total

def sample_allergen_data(limit=10):
    """Show sample products with allergen information"""
    print("\n" + "="*60)
    print(f"SAMPLE PRODUCTS WITH ALLERGENS (first {limit})")
    print("="*60)
    
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT code, product_name, brands, allergens_en, traces_tags
        FROM products 
        WHERE allergens_en IS NOT NULL AND allergens_en != ''
        LIMIT ?
    """, (limit,))
    
    samples = cursor.fetchall()
    
    if not samples:
        print("No allergen data found yet.")
    else:
        for i, sample in enumerate(samples, 1):
            print(f"\n{i}. Product: {sample[1] or 'Unknown'}")
            print(f"   Barcode: {sample[0]}")
            print(f"   Brands: {sample[2] or 'Unknown'}")
            print(f"   Allergens: {sample[3]}")
            print(f"   Traces: {sample[4] or 'None'}")
    
    conn.close()

def top_allergens(limit=20):
    """Show most common allergens in the database"""
    print("\n" + "="*60)
    print(f"TOP {limit} MOST COMMON ALLERGENS")
    print("="*60)
    
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    # This query parses the allergen strings and counts frequencies
    cursor.execute("""
        SELECT allergens_en, COUNT(*) as count
        FROM products
        WHERE allergens_en IS NOT NULL AND allergens_en != ''
        GROUP BY allergens_en
        ORDER BY count DESC
        LIMIT ?
    """, (limit,))
    
    top = cursor.fetchall()
    
    if not top:
        print("No allergen data found yet.")
    else:
        data = []
        for allergen, count in top:
            data.append([allergen, f"{count:,}"])
        
        print(tabulate(data, headers=["Allergen String", "Frequency"], tablefmt="grid"))
    
    conn.close()

def search_products(search_term, limit=10):
    """Search for products by name or brand"""
    print("\n" + "="*60)
    print(f"SEARCH RESULTS FOR: '{search_term}'")
    print("="*60)
    
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT code, product_name, brands, allergens_en
        FROM products 
        WHERE product_name LIKE ? OR brands LIKE ?
        LIMIT ?
    """, (f'%{search_term}%', f'%{search_term}%', limit))
    
    results = cursor.fetchall()
    
    if not results:
        print(f"No products found matching '{search_term}'")
    else:
        for i, result in enumerate(results, 1):
            print(f"\n{i}. {result[1] or 'Unknown'}")
            print(f"   Barcode: {result[0]}")
            print(f"   Brand: {result[2] or 'Unknown'}")
            print(f"   Allergens: {result[3] or 'None'}")
    
    conn.close()

def check_recent_imports():
    """Check when data was last updated (if you have timestamp)"""
    print("\n" + "="*60)
    print("RECENTLY ADDED/UPDATED PRODUCTS")
    print("="*60)
    
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT code, product_name, last_modified_t
        FROM products
        WHERE last_modified_t IS NOT NULL
        ORDER BY last_modified_t DESC
        LIMIT 5
    """)
    
    recent = cursor.fetchall()
    
    if not recent:
        print("No timestamp data available.")
    else:
        for item in recent:
            print(f"\nProduct: {item[1]}")
            print(f"Barcode: {item[0]}")
            if item[2]:
                from datetime import datetime
                date = datetime.fromtimestamp(item[2])
                print(f"Last modified: {date}")
    
    conn.close()

def interactive_menu():
    """Interactive menu for querying the database"""
    
    if not check_database_exists():
        return
    
    while True:
        print("\n" + "="*60)
        print("BITERIGHT - SQLITE DATABASE QUERY TOOL")
        print("="*60)
        print("1. Show basic statistics")
        print("2. Show sample products with allergens")
        print("3. Show top allergens")
        print("4. Search products")
        print("5. Show recent products")
        print("6. Exit")
        
        choice = input("\nEnter your choice (1-6): ").strip()
        
        if choice == '1':
            get_basic_stats()
        elif choice == '2':
            try:
                limit = int(input("How many samples to show? (default 10): ") or "10")
                sample_allergen_data(limit)
            except ValueError:
                sample_allergen_data(10)
        elif choice == '3':
            try:
                limit = int(input("How many top allergens to show? (default 20): ") or "20")
                top_allergens(limit)
            except ValueError:
                top_allergens(20)
        elif choice == '4':
            search_term = input("Enter search term (product name or brand): ").strip()
            if search_term:
                try:
                    limit = int(input("Max results to show? (default 10): ") or "10")
                    search_products(search_term, limit)
                except ValueError:
                    search_products(search_term, 10)
            else:
                print("Search term cannot be empty")
        elif choice == '5':
            check_recent_imports()
        elif choice == '6':
            print("Goodbye!")
            break
        else:
            print("Invalid choice. Please enter 1-6.")
        
        input("\nPress Enter to continue...")

if __name__ == "__main__":
    # If no arguments, show interactive menu
    import sys
    if len(sys.argv) > 1:
        # Command line mode
        if sys.argv[1] == "--stats":
            if check_database_exists():
                get_basic_stats()
        elif sys.argv[1] == "--sample":
            limit = int(sys.argv[2]) if len(sys.argv) > 2 else 10
            if check_database_exists():
                sample_allergen_data(limit)
        elif sys.argv[1] == "--top":
            limit = int(sys.argv[2]) if len(sys.argv) > 2 else 20
            if check_database_exists():
                top_allergens(limit)
        else:
            print("Usage: python query_sqlite.py [--stats|--sample N|--top N]")
    else:
        # Interactive mode
        interactive_menu()