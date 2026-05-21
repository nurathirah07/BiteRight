import firebase_admin
from firebase_admin import credentials, firestore
import json

# Initialize Firebase (same as in app.py)
cred = credentials.Certificate('serviceAccountKey.json')
firebase_admin.initialize_app(cred)
db = firestore.client()

# Common allergens with their scientific names and synonyms
allergens_data = [
    {
        "standard_name": "peanuts",
        "category": "nuts",
        "synonyms": ["arachis hypogaea", "ground nuts", "earth nuts", "peanut butter", "monkey nuts"],
        "severity": "high"
    },
    {
        "standard_name": "milk",
        "category": "dairy",
        "synonyms": ["dairy", "lactose", "whey", "casein", "milk solids", "butter", "cream", "yogurt"],
        "severity": "medium"
    },
    {
        "standard_name": "eggs",
        "category": "eggs",
        "synonyms": ["albumin", "ovalbumin", "egg white", "egg yolk", "mayonnaise"],
        "severity": "medium"
    },
    {
        "standard_name": "soy",
        "category": "legumes",
        "synonyms": ["soya", "soybean", "tofu", "tempeh", "edamame", "soy lecithin", "miso"],
        "severity": "medium"
    },
    {
        "standard_name": "wheat",
        "category": "gluten",
        "synonyms": ["gluten", "flour", "semolina", "spelt", "durum", "cereal", "bran"],
        "severity": "medium"
    },
    {
        "standard_name": "shellfish",
        "category": "seafood",
        "synonyms": ["shrimp", "prawn", "crab", "lobster", "crayfish", "krill"],
        "severity": "high"
    },
    {
        "standard_name": "fish",
        "category": "seafood",
        "synonyms": ["salmon", "tuna", "cod", "mackerel", "anchovy", "sardine"],
        "severity": "high"
    },
    {
        "standard_name": "tree nuts",
        "category": "nuts",
        "synonyms": ["almond", "walnut", "cashew", "pecan", "pistachio", "hazelnut", "macadamia"],
        "severity": "high"
    }
]

# Add to Firestore
print("Seeding allergen database...")
for allergen in allergens_data:
    allergen_keyword = allergen["standard_name"].replace(" ", "_")
    db.collection('master_allergens').document(allergen_keyword).set({
        "allergen_keyword": allergen_keyword,
        "standard_name": allergen["standard_name"],
        "category": allergen["category"],
        "synonym_list": allergen["synonyms"],
        "severity": allergen["severity"],
        "updated_at": firestore.SERVER_TIMESTAMP,
    }, merge=True)
    print(f"Added: {allergen['standard_name']}")

print("Allergen database seeded successfully!")
