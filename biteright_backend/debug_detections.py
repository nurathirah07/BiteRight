# debug_detections.py
"""
Debug script to see what allergens the system is detecting
"""

import requests
import json
import os

API_URL = "http://localhost:5000"

# Test a few known safe products
safe_products = [
    "rice.png",           # Should be SAFE for all (no allergens)
    "salt.jpg",          # Should be SAFE for all
    "white sugar.jpg",   # Should be SAFE for all
]

# Test a product that should be safe for Profile 1
# Profile 1 has allergies: Sesame, Fish, Shellfish, Wheat
# Rice has no allergens → should be SAFE

print("="*60)
print("DEBUGGING ALLERGEN DETECTION")
print("="*60)

for product in safe_products:
    image_path = f"test_data/images/{product}"
    
    if not os.path.exists(image_path):
        print(f"⚠ Image not found: {image_path}")
        continue
    
    print(f"\n📷 Testing: {product}")
    print("-"*40)
    
    # Step 1: Extract ingredients
    with open(image_path, 'rb') as f:
        files = {'image': f}
        ocr_response = requests.post(f"{API_URL}/extract-ingredients", files=files)
    
    if ocr_response.status_code != 200:
        print(f"  OCR Failed: {ocr_response.status_code}")
        continue
    
    ocr_result = ocr_response.json()
    extracted = ocr_result.get('ingredients', [])
    print(f"  Extracted ingredients: {extracted}")
    
    # Step 2: Analyze with each profile
    for profile_id in ['TEST_PROFILE_1', 'TEST_PROFILE_2', 'TEST_PROFILE_3', 'TEST_PROFILE_4', 'TEST_PROFILE_5']:
        analysis_data = {
            'user_id': profile_id,
            'ingredients_text': ', '.join(extracted) if extracted else ""
        }
        
        analysis_response = requests.post(f"{API_URL}/analyze-with-profile", json=analysis_data)
        
        if analysis_response.status_code == 200:
            result = analysis_response.json()
            print(f"\n  {profile_id}:")
            print(f"    Risk Level: {result.get('risk_level')}")
            print(f"    Risk Score: {result.get('risk_score')}")
            print(f"    Alerts: {result.get('alerts', [])[:3]}")
            print(f"    Detected Allergens: {result.get('allergens_detected', [])}")
        else:
            print(f"\n  {profile_id}: ERROR {analysis_response.status_code}")
            print(f"    {analysis_response.text[:200]}")