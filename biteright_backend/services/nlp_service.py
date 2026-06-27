# biteright_backend/services/nlp_service.py
"""
Improved NLP Service for BiteRight - Enhanced allergen detection with better pattern matching
"""

import re
import json
import os
from typing import List, Dict, Set, Tuple
from difflib import SequenceMatcher
from collections import defaultdict

# Comprehensive allergen database with patterns, synonyms, and detection rules
ALLERGEN_DATABASE = {
    'peanuts': {
        'keywords': ['peanut', 'peanuts', 'ground nut', 'arachis', 'peanut butter', 'peanut oil', 'peanut flour', 'peanut protein', 'groundnut'],
        'patterns': [r'\bpeanut\b', r'\bpeanuts?\b', r'ground\s+nuts?', r'arachis', r'\bgroundnut\b'],
        'synonyms': ['peanut butter', 'peanut oil', 'monkey nut'],
        'severity': 'high'
    },
    'tree_nuts': {
        'keywords': ['almond', 'almonds', 'walnut', 'walnuts', 'cashew', 'cashews', 'pecan', 'pecans',
                     'pistachio', 'pistachios', 'hazelnut', 'hazelnuts', 'macadamia', 'brazil nut',
                     'chestnut', 'pine nut', 'coconut', 'desiccated coconut', 'toasted coconut',
                     'coconut milk', 'coconut cream', 'coconut oil', 'praline', 'marzipan'],
        'patterns': [r'\b(almond|walnut|cashew|pecan|pistachio|hazelnut|macadamia|chestnut|pine\s+nut|coconut|desiccated\s+coconut|toasted\s+coconut)s?\b'],
        'synonyms': ['tree nut', 'nut oil', 'nut butter'],
        'severity': 'high'
    },
    'milk': {
        'keywords': ['milk', 'dairy', 'whey', 'casein', 'lactose', 'butter', 'cream', 'cheese',
                     'yogurt', 'yoghurt', 'buttermilk', 'ghee', 'curds', 'milk solids',
                     'nonfat milk', 'whole milk', 'skim milk', 'milk powder', 'skimmed milk',
                     'condensed milk', 'evaporated milk', 'milk protein', 'caseinate',
                     'sodium caseinate', 'calcium caseinate', 'lactalbumin', 'lactoglobulin',
                     'butter oil', 'butterfat', 'whey powder', 'whey protein'],
        'patterns': [r'\bmilk\b', r'\bdairy\b', r'\bwhey\b', r'\bcasein\b', r'\blactose\b',
                     r'\bbutter\b', r'\bcream\b', r'\bcheese\b', r'\byoghu?rt\b', r'\bghee\b',
                     r'\bcaseinate\b', r'butter\s+oil'],
        'synonyms': ['milky', 'dairy product', 'lacto', 'milkfat'],
        'severity': 'high'
    },
    'eggs': {
        'keywords': ['egg', 'eggs', 'albumin', 'ovalbumin', 'albumen', 'egg white', 'egg yolk',
                     'mayonnaise', 'meringue', 'lecithin (egg)', 'powdered eggs', 'dried eggs',
                     'egg wash', 'egg lecithin'],
        'patterns': [r'\begg(s)?\b', r'\balbumin\b', r'\bovalbumin\b', r'\balbumen\b',
                     r'egg\s+white', r'egg\s+yolk', r'\bmayonnaise\b'],
        'synonyms': ['ova', 'ovo', 'egg product'],
        'severity': 'high'
    },
    'soy': {
        'keywords': [
            'soy', 'soya', 'soybean', 'soybeans', 'tofu', 'tempeh', 'edamame', 'miso', 'natto',
            'soy protein', 'soy lecithin', 'soy sauce', 'soy sauce powder', 'tamari',
            'soy milk', 'soy flour', 'soy oil', 'soybean oil', 'textured vegetable protein', 'tvp',
            'hydrolyzed soy protein', 'hydrolyzed vegetable protein',
            'lecithins (soya)', 'lecithins (soy)', 'emulsifier (soya)', 'emulsifier (soy)'
        ],
        'patterns': [
            r'\bsoy\b', r'\bsoya\b', r'\bsoybean(s)?\b', r'\btofu\b', r'\btempeh\b',
            r'\bedamame\b', r'\bmiso\b', r'lecithins?\s*\(\s*soy', r'emulsifier\s*\(\s*soy'
        ],
        'synonyms': ['soya bean', 'soyabean', 'soya milk', 'soybean paste'],
        'severity': 'medium'
    },
    'wheat': {
        'keywords': ['wheat', 'wheat flour', 'whole wheat', 'durum', 'semolina', 'spelt', 'farina',
                     'couscous', 'wheat bran', 'wheat germ', 'cracked wheat', 'bulgur', 'einkorn',
                     'kamut', 'triticale', 'wheat starch', 'wheat protein', 'unbleached wheat flour',
                     'durum wheat', 'durum wheat semolina', 'whole grain wheat', 'wheat flakes'],
        'patterns': [r'\bwheat\b', r'\bdurum\b', r'\bsemolina\b', r'\bspelt\b', r'\bfarina\b',
                     r'\bcouscous\b', r'\bbulgur\b', r'whole\s+grain\s+wheat'],
        'synonyms': ['gluten (wheat)', 'wheat starch'],
        'severity': 'medium'
    },
    'gluten': {
        'keywords': ['gluten', 'barley', 'rye', 'malt', 'malt extract', 'malt syrup', 'malt vinegar',
                     "brewer's yeast", 'triticale', 'seitan', 'vital wheat gluten',
                     'hydrolyzed wheat protein', 'oats', 'rolled oats', 'whole grain oats',
                     'oat bran', 'wheat flakes', 'corn and barley malt', 'barley malt extract'],
        'patterns': [r'\bgluten\b', r'\bbarley\b', r'\brye\b', r'\bmalt\b', r'\bseitan\b',
                     r'\boats?\b', r'rolled\s+oats', r'oat\s+bran', r'barley\s+malt'],
        'synonyms': ['gluten protein', 'wheat gluten', 'barley malt'],
        'severity': 'medium'
    },
    'fish': {
        'keywords': ['fish', 'tuna', 'salmon', 'cod', 'mackerel', 'anchovy', 'sardine', 'trout',
                     'haddock', 'halibut', 'tilapia', 'catfish', 'bass', 'snapper', 'grouper',
                     'swordfish', 'skipjack', 'bonito', 'fish oil', 'fish sauce', 'surimi',
                     'fish stock', 'fish broth', 'anchovy paste', 'ikan', 'ikan bilis'],
        'patterns': [r'\bfish\b', r'\btuna\b', r'\bsalmon\b', r'\bcod\b', r'\banchovy\b',
                     r'\bsardine\b', r'\btrout\b', r'\bskipjack\b', r'fish\s+sauce', r'fish\s+oil'],
        'synonyms': ['seafood (fish)', 'fin fish'],
        'severity': 'high'
    },
    'shellfish': {
        'keywords': ['shrimp', 'prawn', 'crab', 'lobster', 'crayfish', 'crawfish', 'oyster',
                     'clam', 'mussel', 'scallop', 'abalone', 'calamari', 'squid', 'octopus',
                     'langoustine', 'shellfish', 'prawns', 'shrimps'],
        'patterns': [r'\bshrimp\b', r'\bprawn\b', r'\bcrab\b', r'\blobster\b', r'\boyster\b',
                     r'\bclam\b', r'\bmussel\b', r'\bscallop\b', r'\bcalamari\b',
                     r'\bsquid\b', r'\bshellfish\b'],
        'synonyms': ['crustaceans', 'mollusks', 'prawn cocktail', 'crab meat'],
        'severity': 'high'
    },
    'sesame': {
        'keywords': ['sesame', 'tahini', 'sesame seed', 'sesame seeds', 'sesame oil',
                     'benne', 'gingelly', 'sesame paste', 'sesame flour'],
        'patterns': [r'\bsesame\b', r'\btahini\b', r'sesame\s+seeds?', r'sesame\s+oil'],
        'synonyms': ['sesame seed oil', 'tahini paste'],
        'severity': 'medium'
    },
    'celery': {
        'keywords': ['celery', 'celery seed', 'celery salt', 'celery root', 'celeriac', 'celery stalk'],
        'patterns': [r'\bcelery\b', r'celery\s+seed', r'celeriac'],
        'synonyms': ['celeriac'],
        'severity': 'low'
    },
    'mustard': {
        'keywords': ['mustard', 'mustard seed', 'mustard powder', 'mustard flour', 'dijon',
                     'yellow mustard', 'brown mustard'],
        'patterns': [r'\bmustard\b', r'mustard\s+seed', r'dijon'],
        'synonyms': ['mustard greens', 'mustard oil'],
        'severity': 'low'
    },
    'sulphites': {
        'keywords': ['sulphur dioxide', 'sulfur dioxide', 'sodium sulphite', 'sodium sulfite',
                     'potassium sulphite', 'potassium sulfite', 'sodium bisulphite', 'sodium bisulfite',
                     'sodium metabisulphite', 'sodium metabisulfite', 'potassium metabisulphite',
                     'potassium metabisulfite', 'sulphites', 'sulfites'],
        'patterns': [r'sulphur\s+dioxide', r'sulfur\s+dioxide', r'metabisulphite',
                     r'metabisulfite', r'sulphites?', r'sulfites?'],
        'synonyms': ['e220', 'e221', 'e222', 'e223', 'e224', 'e225', 'e226', 'e227', 'e228'],
        'severity': 'medium'
    }
}

# Safe ingredients / processing aids that should NOT trigger allergen alerts on their own.
# These are refined derivatives or alternatives where the allergen protein is absent or negligible.
SAFE_INGREDIENTS = {
    # Tree-nut-named but allergy-safe
    'coconut_water':       ['coconut water', 'coconut juice'],
    'coconut_aminos':      ['coconut aminos'],
    # Plant milks that share names with allergens
    'rice_milk':           ['rice milk', 'rice drink'],
    'oat_milk':            ['oat milk', 'oat drink'],
    # Flavourings / extracts — negligible allergen load
    'almond_extract':      ['almond extract', 'almond flavor', 'almond flavour'],
    'almond_essence':      ['almond essence'],
    # Non-soy liquid aminos
    'liquid_aminos':       ['liquid aminos'],
    # Refined plant oils — no protein, not an allergen trigger
    'sunflower_lecithin':  ['sunflower lecithin'],
    'sunflower_oil':       ['sunflower oil'],
    'canola_oil':          ['canola oil', 'rapeseed oil'],
    'olive_oil':           ['olive oil', 'extra virgin olive oil', 'virgin olive oil'],
    'vegetable_oil':       ['vegetable oil', 'palm oil', 'avocado oil', 'flaxseed oil'],
    # Cocoa butter is NOT dairy butter
    'cocoa_butter':        ['cocoa butter'],
    # Cream of tartar is NOT dairy cream
    'cream_of_tartar':     ['cream of tartar'],
    # Water chestnut is NOT a tree nut
    'water_chestnut':      ['water chestnut', 'water chestnuts'],
    # Nut-free peanut alternatives
    'sunbutter':           ['sunflower butter', 'sunbutter'],
    # Dairy-free creamers
    'coconut_cream_alt':   ['coconut cream'],   # flagged separately when tree_nuts is a concern
}

# Phrases that negate the presence of an allergen in a clause.
# e.g. "contains no wheat", "free from gluten", "does not contain milk"
NEGATION_PHRASES = [
    r'(?:contains?\s+)?(?:no|zero)\s+',
    r'free\s+from\s+',
    r'does\s+not\s+contain\s+',
    r'without\s+',
    r'\bno\s+added\s+',
    r'\bnon[\-\s]',
    r'\b(?:dairy|gluten|nut|egg|soy|wheat)[\-\s]free\b',
]

# Short tokens (≤3 chars) that ARE valid allergen indicators and must not be filtered.
SHORT_ALLERGEN_WHITELIST = {
    'egg', 'eggs',   # eggs allergen
    'rye',           # gluten
    'cod',           # fish
    'soy',           # soy
    'roe',           # fish roe
    'oat',           # gluten/oats
    'tvp',           # textured vegetable protein (soy)
    'msg',           # low_sodium
}

# Allergen mapping for normalization
ALLERGEN_MAP = {
    'tree nuts': 'tree_nuts',
    'tree_nuts': 'tree_nuts',
    'peanuts': 'peanuts',
    'peanut': 'peanuts',
    'milk': 'milk',
    'dairy': 'milk',
    'eggs': 'eggs',
    'egg': 'eggs',
    'soy': 'soy',
    'soybeans': 'soy',
    'wheat': 'wheat',
    'gluten': 'gluten',
    'fish': 'fish',
    'shellfish': 'shellfish',
    'sesame': 'sesame',
    'sesame-seeds': 'sesame',
    'mustard': 'mustard',
    'celery': 'celery',
    'sulphur-dioxide-and-sulphites': 'sulphites',
    'coconut': 'tree_nuts',
}


class AllergenDetector:
    def __init__(self):
        self.allergen_database = ALLERGEN_DATABASE
        self.allergen_patterns = self._compile_patterns()
        self.safe_ingredients = SAFE_INGREDIENTS
        self.allergen_map = ALLERGEN_MAP
        self.allergen_database_list = []
        self.allergen_synonyms = {}
        print(f"AllergenDetector initialized with {len(self.allergen_database)} allergen types")
        
    def _compile_patterns(self) -> Dict:
        """Compile regex patterns for faster matching"""
        patterns = {}
        for allergen, data in self.allergen_database.items():
            all_patterns = data['patterns'] + [rf'\b{re.escape(kw)}\b' for kw in data['keywords']]
            patterns[allergen] = re.compile('|'.join(all_patterns), re.IGNORECASE)
        return patterns
    
    def load_allergens_from_firestore(self, db):
        """Load allergens from Firestore (for backward compatibility)"""
        try:
            self.allergen_database_list = []
            self.allergen_synonyms = {}
            
            # Add all keywords from our database as synonyms
            for allergen_id, data in self.allergen_database.items():
                self.allergen_synonyms[allergen_id] = allergen_id
                for kw in data['keywords']:
                    self.allergen_synonyms[kw] = allergen_id
            
            # Try to load from Firestore if available
            try:
                for collection_name in ('master_allergens', 'allergens'):
                    allergens_ref = db.collection(collection_name).stream()
                    for doc in allergens_ref:
                        allergen_data = doc.to_dict()
                        allergen_data['id'] = doc.id
                        self.allergen_database_list.append(allergen_data)
                        standard_name = str(allergen_data.get('standard_name') or 
                                          allergen_data.get('allergen') or doc.id).lower()
                        self.allergen_synonyms[standard_name] = standard_name
                        synonyms = allergen_data.get('synonym_list', allergen_data.get('synonyms', []))
                        for synonym in synonyms:
                            self.allergen_synonyms[str(synonym).lower()] = standard_name
                    if self.allergen_database_list:
                        break
                print(f"Loaded {len(self.allergen_database_list)} allergens from database")
            except Exception as e:
                print(f"Firestore allergen load skipped: {e}")
            
            return True
        except Exception as e:
            print(f"Error loading allergens: {e}")
            return False
    
    def preprocess_text(self, text: str) -> str:
        """Clean and normalize text for detection"""
        if not text or not isinstance(text, str):
            return ""
        
        # Convert to lowercase
        text = text.lower()
        
        # Remove special characters but keep important ones
        text = re.sub(r'[^\w\s\-\(\)]', ' ', text)
        
        # Remove extra whitespace
        text = re.sub(r'\s+', ' ', text).strip()
        
        return text
    
    def preprocess_ingredient_text(self, text):
        """Backward compatibility method"""
        if isinstance(text, str):
            processed = self.preprocess_text(text)
            return processed.split() if processed else []
        elif isinstance(text, list):
            result = []
            for item in text:
                processed = self.preprocess_text(str(item))
                if processed:
                    result.extend(processed.split())
            return list(set(result))
        return []
    
    def _safe_terms_flat(self) -> list:
        """Return a flat list of all safe-ingredient phrases (lowercase)."""
        return [term for variants in self.safe_ingredients.values() for term in variants]

    def _is_safe_context(self, text: str, match_start: int, match_end: int) -> bool:
        """Check if the matched allergen keyword at (match_start, match_end) is part of
        a safe ingredient (like 'cocoa butter' for milk, 'water chestnut' for tree nuts).
        """
        for safe_term in self._safe_terms_flat():
            start = 0
            while True:
                idx = text.find(safe_term, start)
                if idx == -1:
                    break
                safe_start = idx
                safe_end = idx + len(safe_term)
                if safe_start <= match_start and match_end <= safe_end:
                    return True
                start = idx + 1
        return False

    def _extract_negated_terms(self, text: str) -> set:
        """Build a set of lowercase allergen-relevant terms that appear inside
        negation clauses (e.g. 'contains no wheat', 'gluten-free', 'free from milk').
        """
        negated = set()
        
        # 1. Match suffix negations: X-free or X free
        suffix_pattern = re.compile(
            r'\b(dairy|gluten|nut|nuts|egg|eggs|soy|soya|wheat|peanut|peanuts)[\-\s]free\b(?:\s+([a-z0-9\-]+))?',
            re.IGNORECASE
        )
        for m in suffix_pattern.finditer(text):
            allergen_prefix = m.group(1).strip().lower()
            negated.add(allergen_prefix)
            if allergen_prefix == 'nut':
                negated.add('nuts')
            elif allergen_prefix == 'nuts':
                negated.add('nut')
            elif allergen_prefix == 'egg':
                negated.add('eggs')
            elif allergen_prefix == 'eggs':
                negated.add('egg')
            elif allergen_prefix == 'peanut':
                negated.add('peanuts')
            elif allergen_prefix == 'peanuts':
                negated.add('peanut')
            elif allergen_prefix == 'soya':
                negated.add('soy')
            
            if m.group(2):
                followed_word = m.group(2).strip().lower()
                negated.add(followed_word)
                
        # 2. Match standard prefix negation phrases
        prefix_pattern = re.compile(
            r'\b(?:contains?\s+no|contains?\s+zero|free\s+from|does\s+not\s+contain|without|no\s+added|non[\-\s])\s+([a-z0-9\-\s]{1,40})',
            re.IGNORECASE
        )
        for m in prefix_pattern.finditer(text):
            captured = m.group(1).strip().lower()
            negated.update(captured.split())
        return negated

    def detect_allergens_from_text(self, text: str) -> List[Dict]:
        """Detect allergens from ingredient text.

        Fixes applied vs. original:
          1. Position-aware safe-ingredient context window (±40 chars around each match span).
          2. Negation pre-pass: 'contains no X' / 'free from X' suppress allergen hits.
          3. Minimum match length ≥3 chars (configurable whitelist for short-but-valid tokens).
          4. re.finditer instead of findall — exact (start, end) positions for Fix 1 & 4.
          5. Post-processing deduplication uses ingredient *position* not just allergen type.
        """
        if not text:
            return []

        processed_text = self.preprocess_text(text)

        # Fix 2: build negated-term set before any allergen scanning
        negated_terms = self._extract_negated_terms(processed_text)

        detected = []

        for allergen, pattern in self.allergen_patterns.items():
            # Fix 4: use finditer to get exact match positions
            iter_matches = list(pattern.finditer(processed_text))
            if not iter_matches:
                continue

            real_matches = []  # list of (matched_term, position)
            seen_terms = set()

            for m in iter_matches:
                # Flatten tuple groups from alternation patterns
                matched_term = next((g for g in ([m.group(0)] + list(m.groups() or [])) if g), '')
                matched_term = matched_term.strip().lower()
                if not matched_term or matched_term in seen_terms:
                    continue
                seen_terms.add(matched_term)

                # Fix 3: Minimum length guard — drop ≤2-char tokens unless whitelisted
                if len(matched_term) <= 2 and matched_term not in SHORT_ALLERGEN_WHITELIST:
                    continue

                # Fix 2: Negation check — suppress if the matched term was negated
                if matched_term in negated_terms or any(tok in negated_terms for tok in matched_term.split()):
                    continue

                # Fix 1 & 4: Position-aware safe-ingredient context window
                if self._is_safe_context(processed_text, m.start(), m.end()):
                    continue

                real_matches.append((matched_term, m.start()))

            if not real_matches:
                continue

            allergen_data = self.allergen_database[allergen]
            match_count = len(real_matches)
            # Confidence scales: 1 match → 0.72, 2 → 0.82, 3+ capped at 0.95
            match_confidence = round(min(0.72 + (match_count - 1) * 0.10, 0.95), 2)

            # Fix 4 (post-processing): deduplicate by ingredient position — if the same
            # allergen token appears 3+ times they are likely different ingredients, not noise
            unique_term_list = [term for term, _pos in real_matches[:3]]

            detected.append({
                'allergen': allergen,
                'standard_name': allergen,
                'severity': allergen_data['severity'],
                'matched_terms': unique_term_list,
                'confidence': match_confidence,
                'match_positions': [pos for _term, pos in real_matches[:3]],
            })

        # De-duplicate by allergen type (keep highest confidence)
        seen: set = set()
        unique_detected = []
        for d in sorted(detected, key=lambda x: -x['confidence']):
            if d['allergen'] not in seen:
                seen.add(d['allergen'])
                unique_detected.append(d)

        return unique_detected
    
    def check_user_allergies(self, detected_allergens: List[Dict], user_allergies: List) -> Tuple[List[Dict], bool]:
        """Check which detected allergens match user's allergies"""
        # Handle user_allergies that can be dicts (from Firestore) or strings
        user_allergies_lower = []
        for a in user_allergies:
            if isinstance(a, dict):
                # Extract the allergy id/name from dict
                allergy_str = a.get('id') or a.get('name') or a.get('label') or str(a)
            else:
                allergy_str = str(a)
            user_allergies_lower.append(allergy_str.lower().strip())
        
        # Normalize user allergies
        normalized_user_allergies = set()
        for allergy in user_allergies_lower:
            normalized = self.allergen_map.get(allergy, allergy)
            normalized_user_allergies.add(normalized)
        
        personal_alerts = []
        for allergen_info in detected_allergens:
            allergen_name = allergen_info['allergen'].lower()
            
            # Direct match
            if allergen_name in normalized_user_allergies:
                personal_alerts.append(allergen_info)
                continue
            
            # Check for parent categories (e.g., 'tree_nuts' covers 'almonds')
            if allergen_name == 'tree_nuts':
                for user_allergy in normalized_user_allergies:
                    if user_allergy in ['almond', 'walnut', 'cashew', 'pecan', 'pistachio', 'hazelnut', 'macadamia', 'coconut']:
                        personal_alerts.append(allergen_info)
                        break
            
            # Check for gluten cross-reactivity
            if allergen_name == 'gluten' and 'wheat' in normalized_user_allergies:
                personal_alerts.append(allergen_info)
            elif allergen_name == 'wheat' and 'gluten' in normalized_user_allergies:
                personal_alerts.append(allergen_info)
        
        has_personal_allergens = len(personal_alerts) > 0
        return personal_alerts, has_personal_allergens
    
    def calculate_risk_score(self, detected_allergens: List[Dict], personal_allergens: List[Dict]) -> int:
        """Calculate risk score from 0-100 (higher = more dangerous).
        Consistent with risk_analyzer._to_risk_score ranges:
          safe    → 0-25
          caution → 30-59
          unsafe  → 60-100
        """
        if not detected_allergens:
            return 0

        has_personal = len(personal_allergens) > 0

        if not has_personal:
            # Caution range: general allergens but none match user profile
            count = len(detected_allergens)
            return min(59, 30 + (count - 1) * 5)

        # Unsafe range: personal allergen match — scale by worst severity
        severity_base = {'high': 85, 'medium': 65, 'low': 60}
        worst_base = max(
            severity_base.get(a.get('severity', 'medium'), 65)
            for a in personal_allergens
        )
        extra = (len(personal_allergens) - 1) * 5
        return min(100, worst_base + extra)
    
    def classify_risk_level(self, personal_alerts: List[Dict], detected_allergens: List[Dict]) -> str:
        """Classify risk level based on detected allergens"""
        if not detected_allergens:
            return 'safe'
        
        if personal_alerts:
            return 'unsafe'
        
        return 'caution'
    
    def generate_alerts(self, personal_alerts: List[Dict]) -> List[str]:
        """Generate user-friendly alerts"""
        alerts = []
        for alert in personal_alerts:
            allergen = alert['allergen']
            severity = alert.get('severity', 'medium')
            matched_terms = alert.get('matched_terms', [])
            
            if severity == 'high':
                icon = "⚠️🔴"
            elif severity == 'medium':
                icon = "⚠️🟡"
            else:
                icon = "⚠️"
            
            display_name = allergen.replace('_', ' ').title()
            message = f"{icon} Contains {display_name}"
            if matched_terms:
                message += f" (detected: {', '.join(matched_terms[:2])})"
            
            alerts.append(message)
        
        return alerts
    
    def identify_allergens(self, ingredient_tokens, user_allergies):
        """Backward compatibility method"""
        if isinstance(ingredient_tokens, list):
            text = ' '.join(ingredient_tokens)
        else:
            text = str(ingredient_tokens)
        
        detected = self.detect_allergens_from_text(text)
        personal_alerts, has_personal = self.check_user_allergies(detected, user_allergies)
        
        return {
            'all_detected': [{'standard_name': d['allergen']} for d in detected],
            'personal_alerts': [{'standard_name': d['allergen']} for d in personal_alerts],
            'has_allergens': len(detected) > 0,
            'has_personal_allergens': has_personal
        }
    
    def analyze_ingredients(self, ingredients_text: str, user_allergies: List[str] = None) -> Dict:
        """Main analysis function"""
        if user_allergies is None:
            user_allergies = []
        
        # Detect allergens from text
        detected_allergens = self.detect_allergens_from_text(ingredients_text)
        
        # Check against user allergies
        personal_alerts, has_personal = self.check_user_allergies(detected_allergens, user_allergies)
        
        # Calculate risk score
        risk_score = self.calculate_risk_score(detected_allergens, personal_alerts)
        
        # Classify risk level
        risk_level = self.classify_risk_level(personal_alerts, detected_allergens)
        
        # Calculate dynamic confidence
        if detected_allergens:
            confidences = [d.get('confidence', 0.85) for d in detected_allergens]
            confidence = round(sum(confidences) / len(confidences), 2)
        else:
            # For safe products: confidence based on richness of ingredient text
            # Short/sparse text → lower confidence, detailed list → higher
            word_count = len(ingredients_text.split())
            char_count = len(ingredients_text)
            # Scale: <10 words → 0.65, 10–30 words → 0.72–0.82, 30+ words → up to 0.90
            if word_count < 5:
                confidence = 0.65
            elif word_count < 15:
                confidence = round(0.65 + (word_count - 5) * 0.015, 2)  # 0.65–0.80
            elif word_count < 40:
                confidence = round(0.80 + (word_count - 15) * 0.003, 2)  # 0.80–0.87
            else:
                confidence = 0.90
            confidence = min(confidence, 0.92)  # cap at 0.92 for safe products

        return {
            'detected_allergens': [d['allergen'] for d in detected_allergens],
            'personal_allergens': [d['allergen'] for d in personal_alerts],
            'has_allergens': len(detected_allergens) > 0,
            'has_personal_allergens': has_personal,
            'risk_level': risk_level,
            'risk_score': risk_score,
            'alerts': self.generate_alerts(personal_alerts),
            'detailed_detections': detected_allergens,
            'confidence': round(confidence, 2),
            'detection_method': 'Enhanced NLP Pattern Matching'
        }


# Global instance
detector = AllergenDetector()
print("AllergenDetector instance created")

__all__ = ['AllergenDetector', 'detector']