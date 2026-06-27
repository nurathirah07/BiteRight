"""
Defines all available dietary restrictions and allergen options
Users select from these lists for consistent data
"""

# Common food allergens with their scientific names and synonyms
ALLERGEN_OPTIONS = [
    {
        "id": "peanuts",
        "label": "Peanuts",
        "category": "nuts",
        "severity": "high",
        "severity_score": 100,
        "severity_options": ["high", "medium", "low"],
        "synonyms": ["peanut", "ground nut", "arachis", "earth nut", "monkey nut"],
        "warning": "Can cause severe allergic reactions including anaphylaxis",
        "reaction_types": ["Anaphylaxis", "Hives", "Swelling", "Breathing difficulty"]
    },
    {
        "id": "tree_nuts",
        "label": "Tree Nuts",
        "category": "nuts",
        "severity": "high",
        "severity_score": 95,
        "severity_options": ["high", "medium", "low"],
        "synonyms": ["almond", "walnut", "cashew", "pecan", "pistachio", "hazelnut", "macadamia", "brazil nut"],
        "warning": "Includes almonds, walnuts, cashews, pecans, pistachios",
        "reaction_types": ["Anaphylaxis", "Skin reactions", "Respiratory issues"]
    },
    {
        "id": "shellfish",
        "label": "Shellfish",
        "category": "seafood",
        "severity": "high",
        "severity_score": 95,
        "severity_options": ["high", "medium", "low"],
        "synonyms": ["shrimp", "prawn", "crab", "lobster", "crayfish", "krill"],
        "warning": "Crustaceans only - can cause severe reactions",
        "reaction_types": ["Anaphylaxis", "Vomiting", "Diarrhea", "Stomach cramps"]
    },
    {
        "id": "fish",
        "label": "Fish",
        "category": "seafood",
        "severity": "high",
        "severity_score": 90,
        "severity_options": ["high", "medium", "low"],
        "synonyms": ["salmon", "tuna", "cod", "mackerel", "anchovy", "sardine", "tilapia"],
        "warning": "All finned fish - includes salmon, tuna, cod",
        "reaction_types": ["Anaphylaxis", "Hives", "Nausea"]
    },
    {
        "id": "milk",
        "label": "Milk / Dairy",
        "category": "dairy",
        "severity": "medium",
        "severity_score": 60,
        "severity_options": ["high", "medium", "low"],
        "synonyms": ["milk", "dairy", "lactose", "whey", "casein", "butter", "cream", "cheese", "yogurt", "ghee"],
        "warning": "Contains lactose and milk proteins",
        "reaction_types": ["Digestive issues", "Hives", "Nasal congestion"]
    },
    {
        "id": "eggs",
        "label": "Eggs",
        "category": "eggs",
        "severity": "medium",
        "severity_score": 55,
        "severity_options": ["high", "medium", "low"],
        "synonyms": ["egg", "albumin", "ovalbumin", "mayonnaise", "meringue"],
        "warning": "Avoid eggs and egg-derived ingredients",
        "reaction_types": ["Skin inflammation", "Nasal congestion", "Digestive issues"]
    },
    {
        "id": "wheat",
        "label": "Wheat",
        "category": "gluten",
        "severity": "medium",
        "severity_score": 50,
        "severity_options": ["high", "medium", "low"],
        "synonyms": ["wheat", "flour", "semolina", "spelt", "durum", "bran", "cereal"],
        "warning": "Contains gluten",
        "reaction_types": ["Celiac reaction", "Bloating", "Headaches"]
    },
    {
        "id": "gluten",
        "label": "Gluten",
        "category": "gluten",
        "severity": "medium",
        "severity_score": 50,
        "severity_options": ["high", "medium", "low"],
        "synonyms": ["gluten", "wheat", "barley", "rye", "oats", "malt", "brewer's yeast"],
        "warning": "Found in wheat, barley, rye, and oats",
        "reaction_types": ["Celiac disease", "Gluten sensitivity", "Digestive issues"]
    },
    {
        "id": "soy",
        "label": "Soy",
        "category": "legumes",
        "severity": "medium",
        "severity_score": 45,
        "severity_options": ["high", "medium", "low"],
        "synonyms": ["soy", "soya", "tofu", "tempeh", "edamame", "soy lecithin", "miso", "soy sauce"],
        "warning": "Common in processed foods",
        "reaction_types": ["Hives", "Itching", "Tingling mouth"]
    },
    {
        "id": "sesame",
        "label": "Sesame",
        "category": "seeds",
        "severity": "medium",
        "severity_score": 45,
        "severity_options": ["high", "medium", "low"],
        "synonyms": ["sesame", "tahini", "sesamol", "gingelly"],
        "warning": "Common in breads and sauces",
        "reaction_types": ["Anaphylaxis", "Hives", "Swelling"]
    }
]

# Dietary lifestyle options (religious, ethical, health)
DIETARY_OPTIONS = [
    {
        "id": "halal",
        "label": "Halal",
        "category": "religious",
        "severity": "high",
        "severity_score": 90,
        "forbidden": ["pork", "alcohol", "gelatin", "non-halal meat", "carnivorous animals", "blood"],
        "warning": "No pork, alcohol, or non-halal meat products",
        "description": "Follows Islamic dietary laws"
    },
    {
        "id": "vegetarian",
        "label": "Vegetarian",
        "category": "lifestyle",
        "severity": "medium",
        "severity_score": 50,
        "forbidden": ["meat", "chicken", "fish", "gelatin", "rennet"],
        "allowed": ["dairy", "eggs"],
        "warning": "No meat, poultry, or fish",
        "description": "No animal flesh products"
    },
    {
        "id": "vegan",
        "label": "Vegan",
        "category": "lifestyle",
        "severity": "high",
        "severity_score": 85,
        "forbidden": ["meat", "dairy", "eggs", "honey", "gelatin", "whey", "casein", "shellac"],
        # Explicitly safe plant-based ingredients that share names with forbidden terms
        # e.g. "olive oil" must NOT trigger a vegan violation despite containing "oil"
        "safe_ingredients": [
            "olive oil", "extra virgin olive oil", "virgin olive oil",
            "coconut oil", "vegetable oil", "sunflower oil",
            "rapeseed oil", "canola oil", "avocado oil", "flaxseed oil",
            "palm oil", "rice bran oil", "sesame oil", "peanut oil",
            "cocoa butter",
            "cream of tartar",
            "coconut cream",
            "coconut milk",
            "almond milk",
            "oat milk",
            "soy milk",
            "rice milk",
        ],
        "warning": "No animal products of any kind",
        "description": "No animal-derived ingredients"
    },
    {
        "id": "keto",
        "label": "Keto / Low Carb",
        "category": "diet",
        "severity": "medium",
        "severity_score": 40,
        "forbidden": ["sugar", "wheat", "rice", "corn", "potato", "high carb", "starch"],
        "warning": "High fat, low carbohydrate diet",
        "description": "Limit carbs to 20-50g per day"
    },
    {
        "id": "low_sodium",
        "label": "Low Sodium",
        "category": "medical",
        "severity": "medium",
        "severity_score": 60,
        "forbidden": ["salt", "sodium", "monosodium glutamate", "sodium nitrate", "sodium benzoate"],
        "warning": "Limit salt and sodium-containing ingredients",
        "description": "Low sodium diet for heart health"
    },
    {
        "id": "diabetic",
        "label": "Diabetic / Low Sugar",
        "category": "medical",
        "severity": "high",
        "severity_score": 80,
        "forbidden": ["sugar", "syrup", "honey", "high fructose corn syrup", "dextrose", "maltose"],
        "warning": "Avoid added sugars and high glycemic ingredients",
        "description": "Monitor blood sugar levels"
    }
]

def get_all_options():
    """Get all available options combined"""
    return {
        "allergens": ALLERGEN_OPTIONS,
        "dietary": DIETARY_OPTIONS
    }

def get_options_by_category():
    """Group options by category for UI organization"""
    result = {
        "allergens": {},
        "dietary": {}
    }
    
    # Group allergens by category
    for allergen in ALLERGEN_OPTIONS:
        cat = allergen["category"]
        if cat not in result["allergens"]:
            result["allergens"][cat] = []
        result["allergens"][cat].append(allergen)
    
    # Group dietary options by category
    for diet in DIETARY_OPTIONS:
        cat = diet["category"]
        if cat not in result["dietary"]:
            result["dietary"][cat] = []
        result["dietary"][cat].append(diet)
    
    return result

def get_severity_score(restriction_id, restriction_type='allergen'):
    """Get the severity score for a restriction"""
    if restriction_type == 'allergen':
        for allergen in ALLERGEN_OPTIONS:
            if allergen['id'] == restriction_id:
                return allergen.get('severity_score', 50)
    else:
        for diet in DIETARY_OPTIONS:
            if diet['id'] == restriction_id:
                return diet.get('severity_score', 50)
    return 50

def get_risk_level_from_score(score):
    """Convert severity score to risk level"""
    if score >= 70:
        return 'high'
    elif score >= 40:
        return 'medium'
    else:
        return 'low'