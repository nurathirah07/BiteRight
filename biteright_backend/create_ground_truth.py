# biteright_backend/create_ground_truth.py
"""
Ground Truth Validator and Fixer for BiteRight Testing
Validates that ground_truth.csv is complete and properly formatted
Run this after you have created ground_truth.csv to verify it's correct
"""

import os
import csv
import json
from datetime import datetime

def validate_ground_truth():
    """Validate existing ground truth CSV file"""
    
    current_dir = os.path.dirname(os.path.abspath(__file__))
    test_data_dir = os.path.join(current_dir, 'test_data')
    csv_path = os.path.join(test_data_dir, 'ground_truth.csv')
    
    # Check if file exists
    if not os.path.exists(csv_path):
        print(f"✗ ERROR: ground_truth.csv not found at {csv_path}")
        print("\nYou need to create ground_truth.csv first.")
        print("You can use the template from my previous response.")
        return False
    
    print(f"✓ Found ground_truth.csv at {csv_path}")
    
    # Load test profiles to verify columns
    profiles_path = os.path.join(test_data_dir, 'test_profiles.json')
    if not os.path.exists(profiles_path):
        print(f"✗ ERROR: test_profiles.json not found. Please run run_this_first.py first.")
        return False
    
    with open(profiles_path, 'r') as f:
        profiles = json.load(f)
    
    profile_ids = [p['profile_id'] for p in profiles]
    print(f"✓ Loaded {len(profile_ids)} test profiles: {', '.join(profile_ids)}")
    
    # Read and validate CSV
    rows = []
    errors = []
    warnings = []
    
    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        
        # Check required columns
        required_base = ['image_id', 'image_filename', 'actual_ingredients', 'actual_allergens_present']
        for col in required_base:
            if col not in fieldnames:
                errors.append(f"Missing required column: {col}")
        
        # Check profile-specific columns
        for profile_id in profile_ids:
            safe_col = f'safe_for_{profile_id}'
            risk_col = f'expected_risk_{profile_id}'
            score_col = f'expected_risk_score_{profile_id}'
            
            if safe_col not in fieldnames:
                errors.append(f"Missing column: {safe_col}")
            if risk_col not in fieldnames:
                errors.append(f"Missing column: {risk_col}")
            if score_col not in fieldnames:
                errors.append(f"Missing column: {score_col}")
        
        if errors:
            print("\n✗ ERRORS FOUND:")
            for err in errors:
                print(f"  - {err}")
            return False
        
        # Validate each row
        print("\n📋 VALIDATING EACH ROW...")
        row_count = 0
        missing_data_count = 0
        
        for row_num, row in enumerate(reader, 2):  # Start at row 2 (after header)
            row_count += 1
            row_errors = []
            
            # Check image_id format
            if not row.get('image_id', '').startswith('IMG_'):
                row_errors.append(f"Invalid image_id format: {row.get('image_id')}")
            
            # Check image_filename exists
            image_filename = row.get('image_filename', '')
            if not image_filename:
                row_errors.append("Missing image_filename")
            else:
                # Check if image file exists
                image_path = os.path.join(test_data_dir, 'images', image_filename)
                if not os.path.exists(image_path):
                    warnings.append(f"Image file not found: {image_filename}")
            
            # Check each profile's data
            for profile_id in profile_ids:
                safe_val = row.get(f'safe_for_{profile_id}', '').strip().upper()
                risk_val = row.get(f'expected_risk_{profile_id}', '').strip().lower()
                score_val = row.get(f'expected_risk_score_{profile_id}', '').strip()
                
                # Check safe_for value
                if safe_val not in ['TRUE', 'FALSE', '']:
                    row_errors.append(f"{profile_id}: safe_for must be TRUE/FALSE, got '{safe_val}'")
                elif safe_val == '':
                    missing_data_count += 1
                    warnings.append(f"Row {row_num} ({image_filename}): Missing safe_for_{profile_id}")
                
                # Check risk value
                if risk_val not in ['safe', 'caution', 'unsafe', '']:
                    row_errors.append(f"{profile_id}: expected_risk must be safe/caution/unsafe, got '{risk_val}'")
                
                # Check score value
                if score_val:
                    try:
                        score_int = int(float(score_val))
                        if score_int < 0 or score_int > 100:
                            row_errors.append(f"{profile_id}: expected_risk_score must be 0-100, got {score_int}")
                    except ValueError:
                        row_errors.append(f"{profile_id}: expected_risk_score must be a number, got '{score_val}'")
            
            if row_errors:
                print(f"\n  ✗ Row {row_num} ({image_filename}):")
                for err in row_errors:
                    print(f"      {err}")
            else:
                if row_num % 5 == 0:
                    print(f"  ✓ Row {row_num}: {image_filename} - OK")
            
            rows.append(row)
    
    print(f"\n" + "="*60)
    print("VALIDATION SUMMARY")
    print("="*60)
    print(f"Total rows: {row_count}")
    print(f"Missing data fields: {missing_data_count}")
    print(f"Warnings: {len(warnings)}")
    
    if warnings:
        print("\n⚠️ WARNINGS:")
        for w in warnings[:10]:
            print(f"  - {w}")
        if len(warnings) > 10:
            print(f"  ... and {len(warnings)-10} more")
    
    if missing_data_count > 0:
        print(f"\n⚠️ You have {missing_data_count} empty fields that need to be filled.")
        print("Please complete the ground_truth.csv file with all values.")
        return False
    
    print("\n✅ GROUND TRUTH VALIDATION PASSED!")
    print("Your ground_truth.csv is complete and ready for testing.")
    
    return True

def show_statistics():
    """Display statistics from the ground truth data"""
    
    current_dir = os.path.dirname(os.path.abspath(__file__))
    csv_path = os.path.join(current_dir, 'test_data', 'ground_truth.csv')
    
    if not os.path.exists(csv_path):
        print("ground_truth.csv not found")
        return
    
    # Load profiles
    profiles_path = os.path.join(current_dir, 'test_data', 'test_profiles.json')
    if not os.path.exists(profiles_path):
        print("test_profiles.json not found")
        return
    
    with open(profiles_path, 'r') as f:
        profiles = json.load(f)
    
    profile_ids = [p['profile_id'] for p in profiles]
    
    # Read CSV
    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    
    print("\n" + "="*60)
    print("GROUND TRUTH STATISTICS")
    print("="*60)
    print(f"Total products: {len(rows)}")
    print(f"Total test cases: {len(rows)} × {len(profile_ids)} = {len(rows) * len(profile_ids)}")
    
    # Count safe/unsafe per profile
    print("\n📊 SAFETY DISTRIBUTION BY PROFILE:")
    print("-"*50)
    
    for profile_id in profile_ids:
        safe_count = 0
        unsafe_count = 0
        caution_count = 0
        
        for row in rows:
            safe_val = row.get(f'safe_for_{profile_id}', '').strip().upper()
            risk_val = row.get(f'expected_risk_{profile_id}', '').strip().lower()
            
            if safe_val == 'TRUE':
                safe_count += 1
            elif safe_val == 'FALSE':
                unsafe_count += 1
            
            if risk_val == 'caution':
                caution_count += 1
        
        print(f"\n{profile_id}:")
        print(f"  Safe: {safe_count} products")
        print(f"  Unsafe: {unsafe_count} products")
        print(f"  Caution (within unsafe): {caution_count}")
    
    # Count allergens present
    print("\n📊 ALLERGENS IN TEST SET:")
    print("-"*50)
    
    allergen_counts = {}
    for row in rows:
        allergens = row.get('actual_allergens_present', '')
        if allergens:
            for a in allergens.split(','):
                a = a.strip().lower()
                if a:
                    allergen_counts[a] = allergen_counts.get(a, 0) + 1
    
    for allergen, count in sorted(allergen_counts.items(), key=lambda x: -x[1]):
        print(f"  {allergen}: {count} products ({count/len(rows)*100:.0f}%)")
    
    # Count products with no allergens
    no_allergens = sum(1 for row in rows if not row.get('actual_allergens_present', ''))
    print(f"\n  Products with NO allergens: {no_allergens}")

def fix_common_issues():
    """Fix common issues in ground_truth.csv"""
    
    current_dir = os.path.dirname(os.path.abspath(__file__))
    csv_path = os.path.join(current_dir, 'test_data', 'ground_truth.csv')
    backup_path = os.path.join(current_dir, 'test_data', 'ground_truth_backup.csv')
    
    if not os.path.exists(csv_path):
        print("ground_truth.csv not found")
        return
    
    # Create backup
    import shutil
    shutil.copy(csv_path, backup_path)
    print(f"✓ Created backup at: {backup_path}")
    
    # Read and fix
    with open(csv_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Fix common issues
    fixes_made = []
    
    # Fix "TRUE"/"FALSE" case issues
    if 'true' in content.lower() and 'TRUE' not in content:
        content = content.replace('true', 'TRUE').replace('false', 'FALSE')
        fixes_made.append("Fixed TRUE/FALSE case")
    
    # Fix empty risk scores (set to 0)
    import re
    # Find empty score columns and set to 0
    pattern = r'(expected_risk_score_TEST_PROFILE_\d+),,'
    if re.search(pattern, content):
        content = re.sub(pattern, r'\1,0,', content)
        fixes_made.append("Set empty risk scores to 0")
    
    # Write fixed content
    with open(csv_path, 'w', encoding='utf-8') as f:
        f.write(content)
    
    if fixes_made:
        print("\n✅ Fixes applied:")
        for fix in fixes_made:
            print(f"  - {fix}")
        print("\nOriginal backup saved at: test_data/ground_truth_backup.csv")
    else:
        print("\n✓ No issues found that need automatic fixing")
        os.remove(backup_path)

if __name__ == "__main__":
    print("="*60)
    print("BITERIGHT - GROUND TRUTH VALIDATOR")
    print("="*60)
    print("\nThis script validates your ground_truth.csv file")
    print("and ensures it's ready for testing.\n")
    
    # Check if ground_truth.csv exists
    current_dir = os.path.dirname(os.path.abspath(__file__))
    csv_path = os.path.join(current_dir, 'test_data', 'ground_truth.csv')
    
    if not os.path.exists(csv_path):
        print("✗ ground_truth.csv not found!")
        print("\nSince you already have the filled ground truth data from my previous response,")
        print("please create the file manually:")
        print("\n1. Copy the CSV content I provided earlier")
        print("2. Save it as: test_data/ground_truth.csv")
        print("\nOr run this command to create it:")
        print('  python -c "import csv; ..."')
        exit(1)
    
    # Validate the file
    if validate_ground_truth():
        print("\n" + "="*60)
        print("NEXT STEPS")
        print("="*60)
        print("1. Make sure test users exist: python create_test_users.py")
        print("2. Start Flask app: python app.py")
        print("3. Run accuracy tests: python test_accuracy.py")
        print("4. Analyze results: python analyze_results.py")
        
        # Show statistics
        show_statistics()
    else:
        print("\n" + "="*60)
        print("FIXING COMMON ISSUES...")
        print("="*60)
        fix_common_issues()
        
        # Validate again
        print("\n" + "="*60)
        print("RE-VALIDATING...")
        print("="*60)
        if validate_ground_truth():
            print("\n✅ Fixed successfully! Run the test again.")
        else:
            print("\n❌ Please manually fix the issues in ground_truth.csv")