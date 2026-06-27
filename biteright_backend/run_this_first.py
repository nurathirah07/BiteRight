# biteright_backend/run_this_first.py
"""
Create 5 random test profiles with different allergy combinations
Run this first to generate consistent profile IDs
"""

import json
import random
import os

# Get the current script's directory
current_dir = os.path.dirname(os.path.abspath(__file__))
print(f"Current directory: {current_dir}")

# Create test_data directory in the current directory
test_data_dir = os.path.join(current_dir, 'test_data')
os.makedirs(test_data_dir, exist_ok=True)
print(f"Created directory: {test_data_dir}")

# Also create images subdirectory
images_dir = os.path.join(test_data_dir, 'images')
os.makedirs(images_dir, exist_ok=True)
print(f"Created directory: {images_dir}")

# Define all possible allergens
ALL_ALLERGENS = [
    {"id": "peanuts", "name": "Peanuts", "severity": "high"},
    {"id": "tree_nuts", "name": "Tree Nuts", "severity": "high"},
    {"id": "milk", "name": "Milk/Dairy", "severity": "medium"},
    {"id": "eggs", "name": "Eggs", "severity": "medium"},
    {"id": "soy", "name": "Soy", "severity": "medium"},
    {"id": "wheat", "name": "Wheat", "severity": "medium"},
    {"id": "gluten", "name": "Gluten", "severity": "medium"},
    {"id": "fish", "name": "Fish", "severity": "high"},
    {"id": "shellfish", "name": "Shellfish", "severity": "high"},
    {"id": "sesame", "name": "Sesame", "severity": "medium"}
]

# Create 5 random profiles (using fixed random seed for reproducibility)
random.seed(42)

profiles = []

for i in range(1, 6):
    num_allergies = random.randint(3, 4)
    selected = random.sample(ALL_ALLERGENS, num_allergies)
    
    profile = {
        "profile_id": f"TEST_PROFILE_{i}",
        "username": f"TestUser_{i}",
        "allergies": [a["id"] for a in selected],
        "allergy_names": [a["name"] for a in selected],
        "allergy_severities": {a["id"]: a["severity"] for a in selected},
        "dietary_restrictions": []
    }
    profiles.append(profile)

# Save profiles using absolute path
profiles_path = os.path.join(test_data_dir, 'test_profiles.json')
with open(profiles_path, 'w') as f:
    json.dump(profiles, f, indent=2)

print("\n" + "="*60)
print("TEST PROFILES CREATED SUCCESSFULLY")
print("="*60)
print(f"\n✓ Location: {profiles_path}")
print("\n" + "-"*40)

for p in profiles:
    print(f"\n{p['profile_id']}:")
    print(f"  Allergies: {', '.join(p['allergy_names'])}")
    print(f"  IDs: {p['allergies']}")

print("\n" + "="*60)
print("VERIFICATION:")
print("="*60)

# List created directories and files
if os.path.exists(test_data_dir):
    print(f"✓ test_data directory exists")
    for item in os.listdir(test_data_dir):
        print(f"  📁 {item}/" if os.path.isdir(os.path.join(test_data_dir, item)) else f"  📄 {item}")

print("\n" + "="*60)
print("NEXT STEPS:")
print("="*60)
print("1. Copy your 20 test images to: test_data/images/")
print("2. Run: python create_ground_truth.py")