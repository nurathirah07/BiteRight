# test_ml_accuracy.py
"""
Test ML model accuracy on your test images
"""

import requests
import json
import csv
import os

# Set ML weight to 100% in processing_service.py temporarily
# Change: ML_WEIGHT = 1.0, RULE_WEIGHT = 0.0

def test_ml_accuracy():
    """Test only ML model on test images"""
    
    results = []
    
    with open('test_data/ground_truth.csv', 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            image_name = row['image_filename']
            image_path = f"test_data/images/{image_name}"
            
            if not os.path.exists(image_path):
                continue
            
            # Check if product has any allergen (unsafe for any profile)
            has_allergen = False
            for profile in ['TEST_PROFILE_1', 'TEST_PROFILE_2', 'TEST_PROFILE_3', 'TEST_PROFILE_4', 'TEST_PROFILE_5']:
                if row.get(f'safe_for_{profile}', 'TRUE') == 'FALSE':
                    has_allergen = True
                    break
            
            # Extract ingredients
            with open(image_path, 'rb') as f_img:
                ocr_response = requests.post('http://localhost:5000/extract-ingredients', 
                                            files={'image': f_img})
            
            if ocr_response.status_code != 200:
                continue
            
            ocr_result = ocr_response.json()
            ingredients_text = ' '.join(ocr_result.get('ingredients', []))
            
            # Get analysis (which uses ML)
            response = requests.post('http://localhost:5000/analyze-ingredients',
                                    json={'ingredients_text': ingredients_text})
            
            if response.status_code == 200:
                result = response.json()
                predicted = result.get('risk_level')
                expected = 'unsafe' if has_allergen else 'safe'
                is_correct = (predicted == expected) or (predicted == 'caution' and expected == 'unsafe')
                
                results.append({
                    'image': image_name,
                    'expected': expected,
                    'predicted': predicted,
                    'ml_confidence': result.get('ml_confidence', 0),
                    'correct': is_correct
                })
    
    # Calculate accuracy
    correct = sum(1 for r in results if r['correct'])
    total = len(results)
    
    print("="*60)
    print("ML MODEL ACCURACY ON TEST IMAGES")
    print("="*60)
    print(f"Total test cases: {total}")
    print(f"Correct predictions: {correct}")
    print(f"ML Accuracy: {correct/total*100:.1f}%")
    
    print("\nDetailed results:")
    for r in results:
        status = "✅" if r['correct'] else "❌"
        print(f"{status} {r['image']}: Expected={r['expected']}, Got={r['predicted']} (conf={r['ml_confidence']:.2%})")

if __name__ == "__main__":
    test_ml_accuracy()