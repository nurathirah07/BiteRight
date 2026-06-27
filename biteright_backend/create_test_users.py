# biteright_backend/create_test_users.py
"""
Create test users in Firebase for accuracy testing
Run this before running test_accuracy.py
"""

import json
import os
import firebase_admin
from firebase_admin import credentials, firestore

# Initialize Firebase
cred_path = 'serviceAccountKey.json'

if not os.path.exists(cred_path):
    print(f"✗ ERROR: {cred_path} not found!")
    print("Please download your Firebase service account key and save it as serviceAccountKey.json")
    exit(1)

# Initialize Firebase app (if not already initialized)
try:
    firebase_admin.get_app()
except:
    cred = credentials.Certificate(cred_path)
    firebase_admin.initialize_app(cred)

db = firestore.client()
print("✓ Connected to Firebase")

# Load test profiles
profiles_path = 'test_data/test_profiles.json'
if not os.path.exists(profiles_path):
    print(f"✗ ERROR: {profiles_path} not found!")
    print("Please run run_this_first.py first")
    exit(1)

with open(profiles_path, 'r') as f:
    profiles = json.load(f)

print(f"\n✓ Loaded {len(profiles)} test profiles")

# Create users in Firebase
created_count = 0
existing_count = 0

for profile in profiles:
    user_id = profile['profile_id']
    user_ref = db.collection('users').document(user_id)
    
    if not user_ref.get().exists:
        # Create new user
        user_data = {
            'username': profile['username'],
            'email': f"{user_id.lower()}@test.com",
            'password_hash': 'test_hash_not_used_for_api',
            'allergies': profile['allergies'],
            'dietary_restrictions': [],
            'created_at': firestore.SERVER_TIMESTAMP,
            'updated_at': firestore.SERVER_TIMESTAMP
        }
        user_ref.set(user_data)
        print(f"  ✓ Created: {user_id} (allergies: {', '.join(profile['allergies'])})")
        created_count += 1
    else:
        # Update existing user
        user_ref.update({
            'allergies': profile['allergies'],
            'updated_at': firestore.SERVER_TIMESTAMP
        })
        print(f"  ✓ Updated: {user_id}")
        existing_count += 1

print("\n" + "="*50)
print("USER CREATION SUMMARY")
print("="*50)
print(f"Created: {created_count}")
print(f"Updated: {existing_count}")
print(f"Total: {len(profiles)}")

# Verify users were created
print("\n" + "="*50)
print("VERIFYING USERS IN FIRESTORE")
print("="*50)

for profile in profiles:
    user_ref = db.collection('users').document(profile['profile_id'])
    user_data = user_ref.get().to_dict()
    if user_data:
        print(f"  ✓ {profile['profile_id']}: {user_data.get('allergies', [])}")
    else:
        print(f"  ✗ {profile['profile_id']}: NOT FOUND")

print("\n✅ All test users created successfully!")
print("\nNow you can run: python test_accuracy.py")