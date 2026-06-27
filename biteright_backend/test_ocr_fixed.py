# test_ocr_fixed.py
import requests
import json

# Test on a good image
with open('test_data/images/rice.png', 'rb') as f:
    response = requests.post('http://localhost:5000/extract-ingredients', 
                            files={'image': f})
    print("=== Rice.png ===")
    print(json.dumps(response.json(), indent=2))

print("\n" + "="*50)

# Test on peanut butter
with open('test_data/images/peanut_butter.png', 'rb') as f:
    response = requests.post('http://localhost:5000/extract-ingredients', 
                            files={'image': f})
    print("=== Peanut Butter.png ===")
    print(json.dumps(response.json(), indent=2))