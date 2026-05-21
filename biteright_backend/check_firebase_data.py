# check_firebase_data.py
"""
Check what data is available in your Firebase collections
"""

import firebase_admin
from firebase_admin import credentials, firestore
import os

# Initialize Firebase
cred = credentials.Certificate('serviceAccountKey.json')
firebase_admin.initialize_app(cred)
db = firestore.client()

def list_collections():
    """List all collections in Firestore"""
    print("\nFIRESTORE COLLECTIONS:")
    print("="*60)
    
    collections = db.collections()
    collection_list = list(collections)
    
    if not collection_list:
        print("No collections found in Firestore!")
        return []
    
    for i, collection in enumerate(collection_list, 1):
        print(f"{i}. {collection.id}")
    
    return [col.id for col in collection_list]

def check_collection_data(collection_name):
    """Check data in a specific collection"""
    print(f"\nCOLLECTION: {collection_name}")
    print("="*60)
    
    docs = db.collection(collection_name).limit(5).stream()
    doc_list = list(docs)
    
    print(f"Total documents (limited to first 5): {len(doc_list)}")
    
    if not doc_list:
        print("No documents found in this collection")
        return
    
    for i, doc in enumerate(doc_list, 1):
        print(f"\nDocument {i}:")
        print(f"  ID: {doc.id}")
        data = doc.to_dict()
        
        # Show first few fields
        field_count = 0
        for key, value in data.items():
            if field_count < 5:  # Show first 5 fields only
                print(f"  {key}: {str(value)[:50]}...")
            field_count += 1
        
        if len(data) > 5:
            print(f"  ... and {len(data) - 5} more fields")

def check_specific_product(barcode="test"):
    """Check if a specific product exists"""
    print(f"\nSEARCHING FOR PRODUCT: {barcode}")
    print("="*60)
    
    # Try multiple collection names
    collections_to_try = ['openfoodfacts_products', 'products', 'food_products']
    
    for collection in collections_to_try:
        doc_ref = db.collection(collection).document(barcode).get()
        if doc_ref.exists:
            print(f"Found in collection '{collection}'!")
            print(f"Document data: {doc_ref.to_dict()}")
            return
    
    print("Product not found in any collection")

if __name__ == "__main__":
    print("="*60)
    print("FIREBASE DATA DIAGNOSTIC")
    print("="*60)
    
    # Step 1: List all collections
    collections = list_collections()
    
    if collections:
        # Step 2: Check each collection
        for collection in collections:
            check_collection_data(collection)
    
    # Step 3: Try to find a specific product (optional)
    # check_specific_product("123456789")