"""
NLP Service for BiteRight - using pyenchant for spell checking.
Enhanced with hidden allergen detection and scientific name normalization.
"""

import nltk
from nltk.tokenize import word_tokenize
from nltk.corpus import stopwords
from nltk.stem import WordNetLemmatizer
import re
from difflib import SequenceMatcher
import os

# Try to import pyenchant
USE_PYENCHANT = False
try:
    import enchant
    USE_PYENCHANT = True
    print("Using pyenchant for spell checking")
except ImportError:
    print("pyenchant not available, using simple spell checker")

# Download required NLTK data
try:
    nltk.download('punkt', quiet=True)
    nltk.download('stopwords', quiet=True)
    nltk.download('wordnet', quiet=True)
    nltk.download('omw-1.4', quiet=True)
    print("NLTK data loaded successfully")
except Exception as e:
    print(f"NLTK download warning: {e}")

# Initialize lemmatizer
try:
    lemmatizer = WordNetLemmatizer()
except Exception as e:
    print(f"Lemmatizer error: {e}")
    lemmatizer = None

# Common ingredient patterns and stopwords
STOPWORDS = set(stopwords.words('english'))
INGREDIENT_STOPWORDS = {'contains', 'may', 'contain', 'ingredients', 'and', 'or', 'with', 'less', 'than', '2%'}

# ============= PYENCHANT CHECKER IMPLEMENTATION =============
if USE_PYENCHANT:
    class PyEnchantSpellChecker:
        """Spell checker using pyenchant with ingredient-specific corrections."""
        
        def __init__(self):
            self.dictionary = enchant.Dict("en_US")
            self.common_words = set()
            self.common_misspellings = {}
            self.dictionary_path = "ingredient_dictionary.txt"
            self.create_ingredient_dictionary()
            self.load_dictionary()

            print("pyenchant initialized with ingredient dictionary")
        
        def create_ingredient_dictionary(self):
            """Create a dictionary file with common ingredients and their frequencies"""
            
            # Comprehensive list of ingredients with frequency counts
            ingredient_dict = {
                # Common allergens
                'peanuts': 1000, 'peanut': 1000, 'milk': 1000, 'eggs': 1000, 'soy': 900,
                'wheat': 900, 'gluten': 900, 'shellfish': 800, 'fish': 800, 'tree nuts': 800,
                'almonds': 800, 'walnuts': 700, 'cashews': 700, 'pecans': 600, 'pistachios': 600,
                'hazelnuts': 600, 'macadamia': 500, 'sesame': 700, 'sunflower': 600,
                
                # Dairy products
                'butter': 900, 'cream': 800, 'cheese': 900, 'yogurt': 800, 'whey': 700,
                'casein': 700, 'lactose': 700, 'milk solids': 600,
                
                # Grains and flours
                'flour': 900, 'corn': 800, 'rice': 800, 'oats': 700, 'barley': 600,
                'rye': 500, 'spelt': 400, 'quinoa': 500, 'buckwheat': 400,
                
                # Sweeteners
                'sugar': 1000, 'honey': 800, 'syrup': 700, 'molasses': 500, 'corn syrup': 700,
                'maple syrup': 600, 'agave': 400,
                
                # Oils and fats
                'oil': 900, 'vegetable oil': 800, 'olive oil': 800, 'coconut oil': 700,
                'canola oil': 700, 'palm oil': 600, 'shortening': 500, 'margarine': 500,
                
                # Spices and flavorings
                'vanilla': 800, 'chocolate': 900, 'cocoa': 800, 'cinnamon': 600,
                'nutmeg': 500, 'ginger': 600, 'garlic': 700, 'onion': 700, 'pepper': 700,
                'salt': 1000, 'baking soda': 700, 'baking powder': 700, 'yeast': 600,
                
                # Fruits and vegetables
                'tomato': 700, 'potato': 700, 'carrot': 600, 'celery': 600, 'spinach': 600,
                'lettuce': 500, 'cabbage': 500, 'broccoli': 500, 'cauliflower': 400,
                
                # Meats and proteins
                'beef': 700, 'chicken': 800, 'pork': 700, 'lamb': 500, 'tofu': 600,
                'tempeh': 400, 'seitan': 300,
                
                # Seafood
                'shrimp': 600, 'crab': 500, 'lobster': 400, 'salmon': 500, 'tuna': 500,
                'cod': 400, 'mackerel': 300, 'anchovy': 300,
                
                # Additives and preservatives
                'lecithin': 600, 'monosodium glutamate': 500, 'msg': 500, 'gelatin': 500,
                'pectin': 400, 'carrageenan': 400, 'xanthan gum': 300,
                
                # Common misspellings (included to improve correction)
                'peanutt': 1, 'peantus': 1, 'allmond': 1, 'allmonds': 1, 'wellnut': 1,
                'wellnuts': 1, 'cashewes': 1, 'choclate': 1, 'choclatey': 1, 'vinella': 1,
                'vanila': 1, 'buter': 1, 'buttar': 1, 'suger': 1, 'suggar': 1, 'flourr': 1,
                'flower': 1, 'yeest': 1, 'bakin': 1, 'sodum': 1, 'creem': 1, 'chesse': 1,
                'yougurt': 1, 'yoghurt': 1, 'cocnut': 1, 'cocount': 1, 'seseme': 1, 'sesem': 1
            }
            
            self.common_words = {word for word, count in ingredient_dict.items() if count > 1}
            self.common_misspellings = {
                'peantus': 'peanuts', 'peanutt': 'peanuts',
                'allmond': 'almond', 'allmonds': 'almonds',
                'wellnut': 'walnut', 'wellnuts': 'walnuts',
                'cashewes': 'cashews',
                'choclate': 'chocolate', 'choclatey': 'chocolate',
                'vinella': 'vanilla', 'vanila': 'vanilla',
                'buter': 'butter', 'buttar': 'butter',
                'suger': 'sugar', 'suggar': 'sugar',
                'flourr': 'flour', 'flower': 'flour',
                'yeest': 'yeast', 'bakin': 'baking',
                'sodum': 'soda', 'creem': 'cream',
                'chesse': 'cheese', 'yougurt': 'yogurt',
                'yoghurt': 'yogurt', 'cocnut': 'coconut',
                'cocount': 'coconut', 'seseme': 'sesame',
                'sesem': 'sesame'
            }

            # Keep a personal word list for inspection and future expansion.
            with open(self.dictionary_path, 'w', encoding='utf-8') as f:
                for word in sorted(self.common_words):
                    f.write(f"{word}\n")
            
            print(f"Created ingredient dictionary with {len(ingredient_dict)} entries")
        
        def load_dictionary(self):
            """Load ingredient terms into the pyenchant session dictionary."""
            if os.path.exists(self.dictionary_path):
                for word in self.common_words:
                    if word.isalpha():
                        self.dictionary.add_to_session(word)
                print(f"Loaded dictionary: {self.dictionary_path}")
            else:
                print(f"Dictionary file not found: {self.dictionary_path}")
        
        def check(self, word):
            """
            Check if word is spelled correctly and return correction with confidence
            
            Returns:
                tuple: (is_correct, corrected_word, confidence_score)
            """
            try:
                # Skip very short words
                if len(word) < 3:
                    return True, word, 1.0
                
                word_lower = word.lower()
                if word_lower in self.common_words or self.dictionary.check(word_lower):
                    return True, word, 1.0

                if word_lower in self.common_misspellings:
                    return True, self.common_misspellings[word_lower], 0.92

                suggestions = self.suggest(word_lower)
                if suggestions:
                    best = suggestions[0]
                    confidence = SequenceMatcher(None, word_lower, best).ratio()
                    if confidence >= 0.72:
                        return True, best, max(0.5, min(1.0, confidence))

                return False, word, 0.5
                
            except Exception as e:
                print(f"pyenchant check error for '{word}': {e}")
                return False, word, 0.5
        
        def suggest(self, word):
            """
            Get multiple spelling suggestions for a word
            
            Returns:
                list: Up to 3 suggested corrections
            """
            try:
                if len(word) < 3:
                    return []
                
                word_lower = word.lower()
                ranked = []
                for candidate in self.common_words:
                    score = SequenceMatcher(None, word_lower, candidate).ratio()
                    if score > 0.6:
                        ranked.append((candidate, score))

                for candidate in self.dictionary.suggest(word_lower)[:8]:
                    candidate = candidate.lower()
                    if candidate.isalpha():
                        score = SequenceMatcher(None, word_lower, candidate).ratio()
                        ranked.append((candidate, score))

                ranked.sort(key=lambda item: item[1], reverse=True)
                seen = set()
                suggestions = []
                for candidate, _ in ranked:
                    if candidate not in seen:
                        seen.add(candidate)
                        suggestions.append(candidate)
                    if len(suggestions) == 3:
                        break
                return suggestions
                
            except Exception as e:
                print(f"pyenchant suggest error for '{word}': {e}")
                return []
        
        def add_word(self, word, count=1):
            """
            Add a new word to the dictionary dynamically
            """
            self.common_words.add(word.lower())
            self.dictionary.add_to_session(word.lower())
    
    # Create the spell checker instance
    spell_checker = PyEnchantSpellChecker()
    print("Using pyenchant spell checker")

else:
    # ============= SIMPLE FALLBACK SPELL CHECKER =============
    class SimpleSpellChecker:
        """Simple spell checker without external dependencies (fallback)"""
        
        def __init__(self):
            # Common ingredient words dictionary
            self.common_words = {
                'sugar', 'salt', 'flour', 'water', 'oil', 'milk', 'eggs', 'butter',
                'wheat', 'soy', 'corn', 'rice', 'yeast', 'baking', 'powder', 'soda',
                'vanilla', 'chocolate', 'cocoa', 'cream', 'cheese', 'yogurt', 'peanuts',
                'almonds', 'walnuts', 'cashews', 'pecans', 'coconut', 'syrup', 'honey',
                'molasses', 'oats', 'barley', 'rye', 'spelt', 'sesame', 'sunflower',
                'palm', 'canola', 'olive', 'vegetable', 'shortening', 'margarine',
                'cinnamon', 'nutmeg', 'ginger', 'cloves', 'allspice', 'pepper',
                'tomato', 'potato', 'onion', 'garlic', 'carrot', 'celery', 'spinach',
                'beef', 'chicken', 'pork', 'fish', 'shrimp', 'crab', 'lobster'
            }
            
            # Common misspellings mapping
            self.common_misspellings = {
                'peantus': 'peanuts', 'peanutt': 'peanuts',
                'allmond': 'almond', 'allmonds': 'almonds',
                'wellnut': 'walnut', 'wellnuts': 'walnuts',
                'cashewes': 'cashews',
                'choclate': 'chocolate', 'choclatey': 'chocolate',
                'vinella': 'vanilla', 'vanila': 'vanilla',
                'buter': 'butter', 'buttar': 'butter',
                'suger': 'sugar', 'suggar': 'sugar',
                'flourr': 'flour', 'flower': 'flour',
                'yeest': 'yeast', 'bakin': 'baking',
                'sodum': 'soda', 'creem': 'cream',
                'chesse': 'cheese', 'yougurt': 'yogurt',
                'yoghurt': 'yogurt', 'cocnut': 'coconut',
                'cocount': 'coconut', 'seseme': 'sesame',
                'sesem': 'sesame'
            }
        
        def check(self, word):
            """Check if word is spelled correctly"""
            word_lower = word.lower()
            
            if word_lower in self.common_words:
                return True, word, 1.0
            
            if word_lower in self.common_misspellings:
                corrected = self.common_misspellings[word_lower]
                return True, corrected, 0.9
            
            best_match = None
            best_ratio = 0.0
            
            for common_word in self.common_words:
                similarity = SequenceMatcher(None, word_lower, common_word).ratio()
                if similarity > best_ratio:
                    best_ratio = similarity
                    best_match = common_word
            
            if best_ratio > 0.8:
                return True, best_match, best_ratio
            
            return False, word, 0.5
        
        def suggest(self, word):
            """Get suggestions for misspelled word"""
            suggestions = []
            word_lower = word.lower()
            
            for common_word in self.common_words:
                similarity = SequenceMatcher(None, word_lower, common_word).ratio()
                if similarity > 0.6:
                    suggestions.append((common_word, similarity))
            
            suggestions.sort(key=lambda x: x[1], reverse=True)
            return [s[0] for s in suggestions[:3]]
    
    # Create simple spell checker instance
    spell_checker = SimpleSpellChecker()
    print("Using simple spell checker (fallback)")

# ============= ALLERGEN DETECTOR CLASS =============
class AllergenDetector:
    def __init__(self):
        self.allergen_database = []
        self.allergen_synonyms = {}
        print("AllergenDetector instance created")
        
    def load_allergens_from_firestore(self, db):
        """Load allergen database from Firestore"""
        try:
            self.allergen_database = []
            self.allergen_synonyms = {}
            count = 0
            for collection_name in ('master_allergens', 'allergens'):
                allergens_ref = db.collection(collection_name).stream()
                for doc in allergens_ref:
                    allergen_data = doc.to_dict()
                    allergen_data['id'] = doc.id
                    self.allergen_database.append(allergen_data)
                    
                    # Build synonym dictionary. Supports both ERD field names and older field names.
                    standard_name = str(
                        allergen_data.get('standard_name')
                        or allergen_data.get('allergen')
                        or doc.id
                    ).lower()
                    self.allergen_synonyms[standard_name] = standard_name
                    
                    synonyms = allergen_data.get('synonym_list', allergen_data.get('synonyms', []))
                    for synonym in synonyms:
                        self.allergen_synonyms[str(synonym).lower()] = standard_name
                    
                    count += 1
                if count > 0:
                    break
            
            print(f"Loaded {count} allergens from database")
            return True
        except Exception as e:
            print(f"Error loading allergens: {e}")
            return False
    
    def preprocess_ingredient_text(self, text):
        """Clean and tokenize ingredient text"""
        try:
            if isinstance(text, str):
                # Convert to lowercase
                text = text.lower()
                
                # Remove special characters and numbers
                text = re.sub(r'[^a-zA-Z\s\-\(\)]', ' ', text)
                
                # Tokenize
                tokens = word_tokenize(text)
                
                # Remove stopwords
                tokens = [t for t in tokens if t not in STOPWORDS and t not in INGREDIENT_STOPWORDS]
                
                # Lemmatize
                if lemmatizer:
                    tokens = [lemmatizer.lemmatize(t) for t in tokens]
                
                # Remove duplicates while preserving order
                seen = set()
                unique_tokens = []
                for token in tokens:
                    if token not in seen:
                        seen.add(token)
                        unique_tokens.append(token)
                
                return unique_tokens
                
            elif isinstance(text, list):
                # If text is already a list of ingredients
                processed = []
                for ingredient in text:
                    tokens = self.preprocess_ingredient_text(ingredient)
                    processed.extend(tokens)
                return processed
            else:
                return []
        except Exception as e:
            print(f"Error preprocessing text: {e}")
            return []
    
    def spell_check_ingredient(self, token):
        """Check and correct spelling of ingredient"""
        try:
            is_correct, corrected, confidence = spell_checker.check(token)
            return corrected, confidence
        except Exception as e:
            print(f"Spell check error for '{token}': {e}")
            return token, 0.5
    
    def normalize_scientific_names(self, ingredient_tokens):
        """
        Convert scientific names to common names
        """
        scientific_mapping = {
            'arachis hypogaea': 'peanut',
            'glycine max': 'soy',
            'triticum aestivum': 'wheat',
            'gadus morhua': 'cod',
            'gallus gallus': 'chicken',
            'bos taurus': 'beef',
            'sus scrofa': 'pork',
            'salmo salar': 'salmon',
            'homarus americanus': 'lobster',
            'crustacea': 'shellfish',
            'mollusca': 'mollusks'
        }
        
        normalized = []
        for token in ingredient_tokens:
            token_lower = token.lower()
            if token_lower in scientific_mapping:
                normalized.append(scientific_mapping[token_lower])
            else:
                normalized.append(token)
        
        return normalized
    
    def detect_hidden_allergens(self, ingredient_tokens):
        """
        Detect hidden allergens that might be disguised under different names
        """
        hidden_allergens = {
            'whey': 'milk',
            'casein': 'milk',
            'lactose': 'milk',
            'albumin': 'eggs',
            'ovalbumin': 'eggs',
            'lecithin': 'soy',
            'textured vegetable protein': 'soy',
            'hydrolyzed vegetable protein': 'soy',
            'miso': 'soy',
            'tempeh': 'soy',
            'tofu': 'soy',
            'seitan': 'wheat',
            'durum': 'wheat',
            'semolina': 'wheat',
            'spelt': 'wheat',
            'triticale': 'gluten',
            'malt': 'gluten',
            'brewer\'s yeast': 'gluten'
        }
        
        hidden = []
        for token in ingredient_tokens:
            token_lower = token.lower()
            for hidden_key, allergen_name in hidden_allergens.items():
                if hidden_key in token_lower:
                    hidden.append({
                        'ingredient': token,
                        'hidden_allergen': allergen_name,
                        'detected_as': hidden_key
                    })
        
        return hidden
    
    def extract_cross_contamination_warnings(self, ingredient_tokens):
        """
        Extract cross-contamination warnings from ingredient text
        """
        cross_contamination_keywords = [
            'may contain', 'processed in a facility', 'manufactured in a facility',
            'shared equipment', 'same line', 'same facility', 'may contain traces',
            'produced in a facility', 'made on shared equipment'
        ]
        
        warnings = []
        for token in ingredient_tokens:
            token_lower = token.lower()
            for keyword in cross_contamination_keywords:
                if keyword in token_lower:
                    warnings.append({
                        'type': 'cross_contamination',
                        'message': token,
                        'severity': 'medium'
                    })
        
        return warnings
    
    def identify_allergens(self, ingredient_tokens, user_allergies):
        """Identify allergens from ingredient tokens with enhanced detection"""
        detected_allergens = []
        hidden_allergens = []
        
        # First, normalize scientific names
        normalized_tokens = self.normalize_scientific_names(ingredient_tokens)
        
        # Detect hidden allergens
        hidden = self.detect_hidden_allergens(normalized_tokens)
        hidden_allergens.extend(hidden)
        
        try:
            for token in normalized_tokens:
                # Spell check the token first
                corrected_token, confidence = self.spell_check_ingredient(token)
                
                # Check direct match with allergen synonyms
                if corrected_token in self.allergen_synonyms:
                    standard_name = self.allergen_synonyms[corrected_token]
                    detected_allergens.append({
                        'ingredient': token,
                        'corrected': corrected_token if corrected_token != token else None,
                        'standard_name': standard_name,
                        'match_type': 'direct',
                        'confidence': confidence
                    })
                    continue
                
                # Check partial matches and spelling variations
                for allergen in self.allergen_database:
                    standard_name = allergen['standard_name'].lower()
                    
                    # Check if token is part of standard name
                    if standard_name in corrected_token or corrected_token in standard_name:
                        similarity = SequenceMatcher(None, corrected_token, standard_name).ratio()
                        if similarity > 0.8:
                            detected_allergens.append({
                                'ingredient': token,
                                'corrected': corrected_token if corrected_token != token else None,
                                'standard_name': standard_name,
                                'match_type': 'partial',
                                'confidence': similarity
                            })
                            break
                    
                    # Check synonyms
                    for synonym in allergen.get('synonyms', []):
                        synonym_lower = synonym.lower()
                        if synonym_lower in corrected_token or corrected_token in synonym_lower:
                            similarity = SequenceMatcher(None, corrected_token, synonym_lower).ratio()
                            if similarity > 0.8:
                                detected_allergens.append({
                                    'ingredient': token,
                                    'corrected': corrected_token if corrected_token != token else None,
                                    'standard_name': standard_name,
                                    'match_type': 'synonym',
                                    'confidence': similarity
                                })
                                break
            
            # Add hidden allergens to detected list
            for hidden_item in hidden_allergens:
                # Check if this hidden allergen is already detected
                already_detected = False
                for d in detected_allergens:
                    if d['standard_name'] == hidden_item['hidden_allergen']:
                        already_detected = True
                        break
                
                if not already_detected:
                    detected_allergens.append({
                        'ingredient': hidden_item['ingredient'],
                        'standard_name': hidden_item['hidden_allergen'],
                        'match_type': 'hidden',
                        'confidence': 0.85,
                        'warning': f"Hidden allergen detected: {hidden_item['detected_as']} contains {hidden_item['hidden_allergen']}"
                    })
            
            # Remove duplicates
            unique_allergens = []
            seen = set()
            for allergen in detected_allergens:
                key = f"{allergen['standard_name']}_{allergen.get('corrected', allergen['ingredient'])}"
                if key not in seen:
                    seen.add(key)
                    unique_allergens.append(allergen)
            
            # Filter based on user's allergies
            user_allergies_lower = [a.lower() for a in user_allergies]
            personal_alerts = [
                a for a in unique_allergens 
                if a['standard_name'] in user_allergies_lower
            ]
            
        except Exception as e:
            print(f"Error identifying allergens: {e}")
            unique_allergens = []
            personal_alerts = []
        
        return {
            'all_detected': unique_allergens,
            'personal_alerts': personal_alerts,
            'hidden_allergens': hidden_allergens,
            'has_allergens': len(unique_allergens) > 0,
            'has_personal_allergens': len(personal_alerts) > 0
        }
    
    def classify_risk_level(self, detected_allergens, user_allergies_with_severity):
        """
        Classify overall risk level based on allergen severity
        user_allergies_with_severity: list of dicts with 'id' and 'severity'
        """
        try:
            if not detected_allergens['has_allergens']:
                return 'safe'
            
            # Create a map of user allergies with severity
            user_severity = {}
            if user_allergies_with_severity:
                for a in user_allergies_with_severity:
                    if isinstance(a, dict):
                        user_severity[a.get('id', '')] = a.get('severity', 'medium')
                    elif isinstance(a, str):
                        user_severity[a] = 'medium'
            
            # Check detected allergens against user's severity preferences
            for alert in detected_allergens['personal_alerts']:
                allergen_id = alert['standard_name']
                if allergen_id in user_severity:
                    severity = user_severity[allergen_id]
                    if severity == 'high':
                        return 'unsafe'
                    elif severity == 'medium':
                        return 'caution'
            
            if detected_allergens['has_personal_allergens']:
                return 'caution'
            
            return 'safe'
                
        except Exception as e:
            print(f"Error classifying risk: {e}")
            return 'unknown'
    
    def generate_alerts(self, detected_allergens):
        """Generate user-friendly alert messages with severity indicators"""
        alerts = []
        
        try:
            for alert in detected_allergens['personal_alerts']:
                message = f"Contains {alert['standard_name'].title()}"
                if alert.get('warning'):
                    message = f"⚠️ {alert['warning']}"
                elif alert.get('corrected'):
                    message += f" (detected as: '{alert['ingredient']}' -> '{alert['corrected']}')"
                else:
                    message += f" (detected as: '{alert['ingredient']}')"
                    
                if alert['confidence'] < 0.9:
                    message += f" [confidence: {alert['confidence']:.0%}]"
                alerts.append(message)
            
            # Add hidden allergen warnings
            for hidden in detected_allergens.get('hidden_allergens', []):
                alerts.append(f"⚠️ Hidden: {hidden['detected_as']} contains {hidden['hidden_allergen']}")
                
        except Exception as e:
            print(f"Error generating alerts: {e}")
        
        return alerts

# Create the detector instance that will be imported
print("Initializing AllergenDetector...")
detector = AllergenDetector()
spell_checker_type = "pyenchant" if USE_PYENCHANT else "simple"
print(f"AllergenDetector initialized (using {spell_checker_type} spell checker)")

# Export for import
__all__ = ['AllergenDetector', 'detector']
