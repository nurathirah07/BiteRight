"""
Complete pipeline: CSV -> SQLite -> Firebase
Run this script to update your database with latest Open Food Facts data
"""

import subprocess
import time
import os

def run_step(step_name, script_name):
    """Run a Python script and time it"""
    print(f"\n{'='*60}")
    print(f"STEP: {step_name}")
    print(f"{'='*60}")
    
    # Check if script exists
    if not os.path.exists(script_name):
        print(f"Script not found: {script_name}")
        print(f"Current directory: {os.getcwd()}")
        print(f"Files in directory: {os.listdir('.')}")
        return False
    
    start = time.time()
    result = subprocess.run(['python', script_name], capture_output=True, text=True)
    elapsed = time.time() - start
    
    if result.stdout:
        print(result.stdout)
    if result.stderr:
        print(f"Errors: {result.stderr}")
    
    print(f"Completed in {elapsed:.1f} seconds")
    return result.returncode == 0

def main():
    """Run the complete import pipeline"""
    
    print("="*60)
    print("BITERIGHT - OPEN FOOD FACTS IMPORT PIPELINE")
    print("="*60)
    
    # Show current directory
    print(f"\nCurrent directory: {os.getcwd()}")
    
    # Step 1: Check if data directory exists
    if not os.path.exists("data"):
        os.makedirs("data")
        print("Created data directory")
    
    # Step 2: Check if CSV exists
    csv_files = [f for f in os.listdir("data") if f.endswith('.csv')]
    if not csv_files:
        print("No CSV files found in data directory.")
        print("Please download the CSV file first:")
        print("1. cd data")
        print("2. Invoke-WebRequest -Uri 'https://static.openfoodfacts.org/data/en.openfoodfacts.org.products.sample.csv' -OutFile 'sample.csv'")
        response = input("\nContinue anyway? (y/n): ")
        if response.lower() != 'y':
            return
    else:
        print(f"Found CSV files: {csv_files}")
    
    # Step 3: Import CSV to SQLite
    if not run_step("Import CSV to SQLite", "import_csv_to_sqlite.py"):
        print("Import failed. Stopping pipeline.")
        return
    
    # Step 4: Check if SQLite was created
    if os.path.exists("data/openfoodfacts.db"):
        db_size = os.path.getsize("data/openfoodfacts.db") / (1024**3)
        print(f"SQLite database created: {db_size:.2f} GB")
    else:
        print("SQLite database not found. Import may have failed.")
    
    # Step 5: Export to Firebase
    if os.path.exists("sqlite_to_firebase.py"):
        if not run_step("Export to Firebase", "sqlite_to_firebase.py"):
            print("Firebase export failed.")
            return
    else:
        print("sqlite_to_firebase.py not found. Skipping Firebase export.")
    
    print("\n" + "="*60)
    print("PIPELINE COMPLETE!")
    print("="*60)
    print("\nNext steps:")
    print("1. Run python query_sqlite.py to verify the data")
    print("2. Check Firebase Console to see uploaded data")
    print("3. Run your Flask app: python app.py")

if __name__ == "__main__":
    main()