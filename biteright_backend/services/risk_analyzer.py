# biteright_backend/services/risk_analyzer.py
"""
Enhanced Risk Analyzer with improved allergen detection and matching.
"""

import re
from difflib import SequenceMatcher

from dietary_options import ALLERGEN_OPTIONS, DIETARY_OPTIONS


INGREDIENT_PREFIX_RE = re.compile(
    r"\b(?:ingredients?|contains|allergy advice|allergen information)\b\s*:?",
    re.IGNORECASE,
)

CROSS_CONTACT_PATTERNS = [
    "may contain",
    "may contain traces",
    "processed in a facility",
    "manufactured in a facility",
    "produced in a facility",
    "made in a facility",
    "made on shared equipment",
    "shared equipment",
    "same line",
    "same facility",
]

# Expanded scientific name mappings
SCIENTIFIC_NAME_ALIASES = {
    "arachis hypogaea": "peanuts",
    "arachis oil": "peanuts",
    "glycine max": "soy",
    "triticum aestivum": "wheat",
    "triticum durum": "wheat",
    "triticum spelta": "wheat",
    "hordeum vulgare": "gluten",
    "secale cereale": "gluten",
    "sesamum indicum": "sesame",
    "gallus gallus": "eggs",
    "gadus morhua": "fish",
    "salmo salar": "fish",
    "thunnus": "fish",
    "crustacea": "shellfish",
    "mollusca": "shellfish",
    "prunus dulcis": "tree_nuts",
    "juglans regia": "tree_nuts",
    "anacardium occidentale": "tree_nuts",
    "cocos nucifera": "tree_nuts",
}

# Expanded allergen aliases
EXTRA_ALLERGEN_ALIASES = {
    "peanuts": [
        "peanut butter", "peanut oil", "groundnut", "ground nut", "kacang tanah",
        "arachis", "monkey nut", "goober", "peanut flour", "peanut paste"
    ],
    "tree_nuts": [
        "almond", "almonds", "walnut", "walnuts", "cashew", "cashews", "pecan", "pecans",
        "pistachio", "pistachios", "hazelnut", "hazelnuts", "macadamia", "brazil nut",
        "pine nut", "chestnut", "praline", "marzipan", "nougat", "nut paste", "coconut",
        "coconut milk", "coconut cream", "coconut oil", "desiccated coconut", "toasted coconut"
    ],
    "milk": [
        "milk solids", "skim milk", "skimmed milk", "nonfat milk", "whole milk",
        "condensed milk", "evaporated milk", "milk powder", "milk protein",
        "caseinate", "sodium caseinate", "calcium caseinate", "lactalbumin",
        "lactoglobulin", "ghee", "susu", "dairy", "whey", "whey powder", "whey protein",
        "butter", "butterfat", "buttermilk", "cream", "sour cream", "yogurt", "yoghurt",
        "cheese", "lactose", "butter oil"
    ],
    "eggs": [
        "egg white", "egg yolk", "lysozyme", "albumen", "albumin", "telur", "ovalbumin",
        "ovoglobulin", "mayonnaise", "meringue", "pasta (egg)", "egg wash", "egg lecithin"
    ],
    "soy": [
        "soybean", "soybeans", "soy protein", "textured vegetable protein",
        "hydrolyzed soy protein", "hydrolyzed vegetable protein", "tamari", "tauhu",
        "tofu", "tempeh", "edamame", "soy lecithin", "soy sauce", "soy sauce powder",
        "miso", "natto", "soy flour", "soy milk", "soy oil", "vegetable protein",
        "lecithins (soya)", "lecithins (soy)", "emulsifier (soya)", "emulsifier (soy)"
    ],
    "wheat": [
        "wheat flour", "whole wheat", "bread flour", "cake flour", "atta", "farina",
        "couscous", "durum", "semolina", "spelt", "einkorn", "emmer", "triticale",
        "wheat bran", "wheat germ", "wheat starch", "wheat protein", "gluten", "seitan",
        "unbleached wheat flour", "whole grain wheat", "wheat flakes", "cracked wheat",
        "durum wheat", "durum wheat semolina"
    ],
    "gluten": [
        "wheat", "barley", "rye", "malt", "malt extract", "malt syrup", "malt vinegar",
        "brewer's yeast", "triticale", "spelt", "seitan", "vital wheat gluten",
        "wheat gluten", "gluten flour", "hydrolyzed wheat protein", "modified wheat starch",
        "oats", "rolled oats", "whole grain oats", "oat bran", "wheat flakes",
        "corn and barley malt", "barley malt extract"
    ],
    "fish": [
        "fish sauce", "ikan bilis", "bonito", "surimi", "anchovy", "anchovies",
        "fish oil", "fish meal", "fish gelatin", "caviar", "roe", "fish stock",
        "skipjack", "tuna", "salmon", "cod", "mackerel", "sardine", "trout"
    ],
    "shellfish": [
        "prawns", "oyster", "oysters", "mussel", "mussels", "clam", "clams",
        "squid", "calamari", "cuttlefish", "octopus", "scallop", "abalone",
        "crab", "crab meat", "lobster", "crayfish", "langoustine", "shrimp paste"
    ],
    "sesame": [
        "sesame oil", "sesame seed", "sesame seeds", "benne", "til", "tahini",
        "sesame paste", "halvah", "sesame flour", "sesame salt", "gomasio"
    ],
}

# Expanded dietary forbidden items
DIETARY_EXTRA_FORBIDDEN = {
    "halal": [
        "ham", "bacon", "lard", "pork fat", "pork gelatin", "wine", "beer", "liquor",
        "rum", "brandy", "ethanol", "vanilla extract", "rennet", "pepperoni", "salami",
        "prosciutto", "bacon bits", "pork", "gelatin", "alcohol", "non-halal"
    ],
    "vegetarian": [
        "beef", "pork", "lamb", "poultry", "chicken", "turkey", "duck", "anchovy",
        "anchovies", "prawn", "shrimp", "lard", "tallow", "suet", "gelatin", "rennet",
        "meat extract", "chicken stock", "beef stock", "bone broth", "fish oil"
    ],
    "vegan": [
        # Dairy
        "butter", "buttermilk", "butterfat", "butter oil", "cheese", "cream",
        "sour cream", "lactose", "milk powder", "skimmed milk", "skim milk",
        "whole milk powder", "milk solids", "whey", "whey powder", "whey protein",
        "casein", "caseinate", "ghee", "yogurt", "yoghurt", "condensed milk",
        "evaporated milk", "lactalbumin",
        # Eggs
        "egg", "eggs", "egg white", "egg yolk", "albumin", "ovalbumin",
        "egg powder", "dried egg", "mayonnaise",
        # Animal-derived additives
        "honey", "bee pollen", "royal jelly", "beeswax", "carmine", "cochineal",
        "shellac", "lanolin", "gelatin", "isinglass", "rennet",
        # Fish and seafood
        "fish", "tuna", "salmon", "cod", "anchovy", "anchovies", "sardine",
        "shrimp", "prawn", "crab", "lobster", "shellfish", "fish sauce",
        "fish oil", "fish stock", "fish gelatin",
        # Meat
        "meat", "beef", "pork", "chicken", "turkey", "lamb", "lard", "tallow",
        "suet", "meat extract", "chicken stock", "beef stock", "bone broth",
        # Wheat-gluten products (seitan is NOT vegan-problematic from an animal standpoint,
        # but many vegan products list it; keep for dietary completeness)
        "seitan", "vital wheat gluten",
    ],
    "keto": [
        "dextrose", "maltodextrin", "glucose", "fructose", "tapioca starch", "corn starch",
        "sugar", "cane sugar", "brown sugar", "powdered sugar", "honey", "maple syrup",
        "agave", "corn syrup", "rice syrup", "malt syrup", "wheat flour", "white flour",
        "rice flour", "potato starch", "potato flour", "breadcrumbs", "pasta", "rice"
    ],
    "diabetic": [
        "glucose", "fructose", "sucrose", "molasses", "maltodextrin", "agave", "honey",
        "corn syrup", "high fructose corn syrup", "dextrose", "maltose", "brown sugar",
        "cane sugar", "powdered sugar", "confectioners sugar", "invert sugar", "syrup"
    ],
    "low_sodium": [
        "disodium", "sodium bicarbonate", "sodium chloride", "sodium citrate",
        "monosodium glutamate", "msg", "sodium phosphate", "sodium tripolyphosphate",
        "sodium hexametaphosphate", "sodium carbonate", "sodium benzoate", "salt",
        "sea salt", "table salt", "kosher salt", "rock salt", "celery salt", "garlic salt"
    ],
}

# Expanded OCR fixes
OCR_FIXES = {
    "miik": "milk",
    "mik": "milk",
    "mllk": "milk",
    "soyabean": "soybean",
    "soya bean": "soybean",
    "soyabeans": "soybeans",
    "peant": "peanut",
    "peanutt": "peanut",
    "peantus": "peanuts",
    "seseme": "sesame",
    "sesam": "sesame",
    "wbeat": "wheat",
    "wheaf": "wheat",
    "glulen": "gluten",
    "glutan": "gluten",
    "almomd": "almond",
    "almod": "almond",
    "cashewes": "cashews",
    "pistashio": "pistachio",
    "cocnut": "coconut",
    "cocount": "coconut",
    "buter": "butter",
    "buttar": "butter",
    "suger": "sugar",
    "suggar": "sugar",
    "flower": "flour",
    "yeest": "yeast",
    "creem": "cream",
    "chesse": "cheese",
    "yoghurt": "yogurt",
}


def normalize_key(value):
    """Normalize keys for consistent matching."""
    return str(value or "").strip().lower().replace("-", "_").replace(" ", "_")


def normalize_text(value):
    """Enhanced text normalization for ingredient matching."""
    text = str(value or "").lower()
    text = text.replace("&", " and ")
    
    # Apply OCR fixes
    for wrong, correct in OCR_FIXES.items():
        text = re.sub(rf"\b{re.escape(wrong)}\b", correct, text)
    
    # Fix common character issues
    text = re.sub(r"[\u2018\u2019\u201c\u201d]", "'", text)
    text = re.sub(r"[\u2013\u2014]", "-", text)
    
    # Remove special characters but keep important ones
    text = re.sub(r"[^a-z0-9%+'\-/\s,;:.()]", " ", text)
    
    # Normalize whitespace
    return re.sub(r"\s+", " ", text).strip()


def split_ingredient_text(text):
    """Split ingredient text into individual ingredients."""
    text = INGREDIENT_PREFIX_RE.sub(" ", str(text or ""))
    text = re.sub(r"\b(?:nutrition facts?|serving size|calories|barcode|net weight)\b.*", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"\b(?:vitamins?|minerals?):.*$", " ", text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"\s+", " ", text).strip(" .,:;")
    
    if not text:
        return []

    # Try comma separation first
    if ',' in text:
        parts = re.split(r',\s*', text)
    else:
        separators = r";|\n|\. (?=[A-Z])|\s+and\s+"
        parts = re.split(separators, text)
    
    ingredients = []
    for part in parts:
        part = part.strip(" .,:;")
        if not part:
            continue
        # Clean the part
        part = re.sub(r'\s+or\s+', ' ', part, flags=re.IGNORECASE)
        part = re.sub(r'\s+and\s+', ' ', part, flags=re.IGNORECASE)
        if len(part) > 1 and re.search(r"[a-zA-Z]", part):
            ingredients.append(part)
    
    return list(dict.fromkeys(ingredients))


def _dedupe_ingredients(ingredients):
    """Remove duplicate ingredients."""
    seen = set()
    unique = []
    for ingredient in ingredients:
        key = normalize_text(ingredient)
        if not key or key in seen:
            continue
        seen.add(key)
        unique.append(ingredient.strip())
    return unique


def parse_ingredients_input(ingredients_input):
    """Parse ingredients from various input formats."""
    if isinstance(ingredients_input, list):
        values = []
        for item in ingredients_input:
            if item is None:
                continue
            values.extend(split_ingredient_text(str(item)))
        if values:
            return _dedupe_ingredients(values)
        joined = " ".join(str(item).strip() for item in ingredients_input if str(item).strip())
        if joined:
            return parse_ingredients_input(joined)
        return []

    text = str(ingredients_input or "").strip()
    values = split_ingredient_text(text)
    if values:
        return _dedupe_ingredients(values)
    return [text] if text else []


def _to_risk_score(risk_level: str, hazard_score: int, allergen_count: int = 1) -> int:
    """Convert detection results to a dynamic risk score (0 = safest, 100 = most dangerous).
    
    Safe:    0-25  (0 if completely clean, up to 25 if non-profile allergens present)
    Caution: 30-59 (cross-contact or dietary violations, scaled by hazard severity)
    Unsafe:  60-100 (personal allergen match, scaled by severity and count)
    """
    hazard_score = int(hazard_score or 0)
    if risk_level == "safe":
        # Completely clean: 0. If hazard_score > 0 (general allergens but not personal), up to 25.
        return min(25, int(hazard_score * 0.25)) if hazard_score > 0 else 0
    if risk_level == "caution":
        # Scale 30-59 based on hazard
        base = 30 + min(29, int(hazard_score * 0.35))
        # Each additional allergen nudges score up slightly
        return min(59, base + (allergen_count - 1) * 3)
    # Unsafe: 60-100, severity-driven
    if hazard_score >= 85:   # high severity
        base = 85
    elif hazard_score >= 55: # medium severity
        base = 65
    else:                    # low severity
        base = 60
    # Each additional matching allergen increases danger
    return min(100, base + (allergen_count - 1) * 5)


def _allergen_rules():
    """Build allergen rules from configuration."""
    rules = {}
    for allergen in ALLERGEN_OPTIONS:
        allergen_id = normalize_key(allergen["id"])
        aliases = {
            allergen_id,
            normalize_key(allergen.get("label")),
            str(allergen.get("label", "")).lower(),
            *[str(s).lower() for s in allergen.get("synonyms", [])],
            *EXTRA_ALLERGEN_ALIASES.get(allergen_id, []),
        }
        rules[allergen_id] = {
            "id": allergen_id,
            "name": allergen.get("label", allergen_id).replace(" / ", "/"),
            "severity": allergen.get("severity", "medium"),
            "severity_score": allergen.get("severity_score", 50),
            "keywords": sorted({normalize_text(a) for a in aliases if a}, key=len, reverse=True),
        }
    for scientific_name, allergen_id in SCIENTIFIC_NAME_ALIASES.items():
        target_id = normalize_key(allergen_id)
        if target_id in rules:
            rules[target_id]["keywords"] = sorted(
                {*rules[target_id]["keywords"], normalize_text(scientific_name)},
                key=len,
                reverse=True,
            )
    return rules


def _dietary_rules():
    """Build dietary rules from configuration."""
    rules = {}
    for diet in DIETARY_OPTIONS:
        diet_id = normalize_key(diet["id"])
        forbidden = [str(item).lower() for item in diet.get("forbidden", [])]
        forbidden.extend(DIETARY_EXTRA_FORBIDDEN.get(diet_id, []))
        # Load safe_ingredients: these are plant-based or allergen-free items that share
        # names with forbidden terms and must NOT be flagged as violations.
        safe_items = [str(s).lower() for s in diet.get("safe_ingredients", [])]
        rules[diet_id] = {
            "id": diet_id,
            "name": diet.get("label", diet_id),
            "severity": diet.get("severity", "medium"),
            "severity_score": diet.get("severity_score", 50),
            "forbidden": sorted({normalize_text(a) for a in forbidden if a}, key=len, reverse=True),
            "safe_ingredients": safe_items,  # used to guard per-ingredient checks
        }
    return rules


ALLERGEN_RULES = _allergen_rules()
DIETARY_RULES = _dietary_rules()


def _selected_allergy_ids(user_allergies):
    """Extract selected allergy IDs from user profile."""
    ids = set()
    severity_by_id = {}
    for allergy in user_allergies or []:
        if isinstance(allergy, dict):
            raw_id = allergy.get("id") or allergy.get("label") or allergy.get("name")
            severity = allergy.get("severity", "medium")
        else:
            raw_id = allergy
            severity = "medium"

        profile_key = normalize_key(raw_id)
        matched = False
        for rule in ALLERGEN_RULES.values():
            rule_keys = {rule["id"], normalize_key(rule["name"])}
            rule_keys.update(normalize_key(keyword) for keyword in rule["keywords"])
            if profile_key in rule_keys:
                ids.add(rule["id"])
                severity_by_id[rule["id"]] = severity
                matched = True
                break
        if not matched:
            ids.add(profile_key)
            severity_by_id[profile_key] = severity
    return ids, severity_by_id


def _selected_diet_ids(user_dietary):
    """Extract selected dietary IDs from user profile."""
    selected = set()
    for diet in user_dietary or []:
        diet_id = normalize_key(diet.get("id") if isinstance(diet, dict) else diet)
        if diet_id in DIETARY_RULES:
            selected.add(diet_id)
    return selected


def _phrase_match(text, keyword):
    """Check if keyword appears as a whole word in text."""
    if not keyword:
        return False
    return re.search(rf"(?<![a-z0-9]){re.escape(keyword)}(?![a-z0-9])", text) is not None


def _fuzzy_match_token(tokens, keyword):
    """Fuzzy match a keyword against tokens."""
    if " " in keyword or len(keyword) < 5:
        return None
    candidates = [token for token in tokens if len(token) >= 4]
    if not candidates:
        return None
    best = max((SequenceMatcher(None, token, keyword).ratio(), token) for token in candidates)
    if best[0] >= 0.85:
        return best[1]
    return None


def _find_keyword_match(text, keywords):
    """Find best matching keyword in text."""
    tokens = re.findall(r"[a-z0-9]+", text)
    for keyword in keywords:
        if _phrase_match(text, keyword):
            return keyword, "exact", 0.98
        fuzzy_token = _fuzzy_match_token(tokens, keyword)
        if fuzzy_token:
            return fuzzy_token, "fuzzy", 0.85
    return None, None, 0.0


def _cross_contact_matches(full_text, allergy_ids):
    """Find cross-contamination warnings."""
    matches = []
    warning_clauses = [
        clause.strip()
        for clause in re.split(r"[.;]", full_text)
        if any(pattern in clause for pattern in CROSS_CONTACT_PATTERNS)
    ]
    for clause in warning_clauses:
        for rule_id in allergy_ids:
            rule = ALLERGEN_RULES.get(rule_id)
            if not rule:
                continue
            keyword, match_type, confidence = _find_keyword_match(clause, rule["keywords"])
            if keyword:
                matches.append((rule, keyword, match_type or "cross_contact", min(confidence, 0.85)))
    return matches


def _severity_score(severity, default_score):
    """Calculate severity score based on allergen severity."""
    if severity == "high":
        return max(default_score, 85)
    if severity == "medium":
        return max(default_score, 55)
    return max(default_score, 25)


def _ingredient_base_confidence(ingredient_str: str) -> float:
    """Compute a realistic base confidence for a safe ingredient based on string quality.
    Longer, well-formed ingredient strings score higher (better OCR quality signal).
    """
    s = ingredient_str.strip()
    if not s:
        return 0.60
    words = s.split()
    word_count = len(words)
    char_count = len(s)
    # Penalise very short or single-char tokens (likely OCR noise)
    if char_count <= 2:
        return 0.60
    # Multi-word ingredient names are more reliably parsed
    if word_count == 1:
        base = min(0.70 + char_count * 0.005, 0.82)  # e.g. WATER→0.73, CREAM→0.75
    elif word_count == 2:
        base = min(0.78 + char_count * 0.002, 0.88)  # e.g. LIQUID SUGAR→0.84
    else:
        base = min(0.84 + char_count * 0.001, 0.92)  # e.g. MILK SOLIDS NON FAT→0.90
    return round(base, 2)


def build_personalized_analysis(ingredients, user_allergies, user_dietary, raw_text=None):
    """
    Build personalized analysis based on user profile.
    """
    parsed_ingredients = [
        item for item in parse_ingredients_input(ingredients) if normalize_text(item)
    ]
    if not parsed_ingredients and raw_text:
        parsed_ingredients = [
            item for item in parse_ingredients_input(raw_text) if normalize_text(item)
        ]
    
    allergy_ids, allergy_severity = _selected_allergy_ids(user_allergies)
    dietary_ids = _selected_diet_ids(user_dietary)
    full_text = normalize_text(raw_text if raw_text else " ".join(parsed_ingredients))

    details = []
    allergen_alerts = []
    dietary_alerts = []
    detected_allergens = set()
    max_risk_score = 0
    confidence_values = []

    # Check each ingredient
    for ingredient in parsed_ingredients:
        normalized = normalize_text(ingredient)
        if not normalized:
            continue
        
        is_trace_context = any(pattern in normalized for pattern in CROSS_CONTACT_PATTERNS)
        if not is_trace_context and full_text:
            for pattern in CROSS_CONTACT_PATTERNS:
                idx = full_text.find(pattern)
                if idx != -1:
                    warning_part = full_text[idx:]
                    if normalized in warning_part:
                        prefix_to_ing = warning_part[:warning_part.find(normalized)]
                        if '.' not in prefix_to_ing and ';' not in prefix_to_ing:
                            is_trace_context = True
                            break
        status = "safe"
        reasons = []
        matches = []
        ingredient_confidence = _ingredient_base_confidence(ingredient)

        # Check allergens
        for rule_id in allergy_ids:
            rule = ALLERGEN_RULES.get(rule_id)
            if not rule:
                continue
            keyword, match_type, confidence = _find_keyword_match(normalized, rule["keywords"])
            if not keyword:
                continue

            severity = allergy_severity.get(rule_id, rule["severity"])
            if not is_trace_context:
                status = "unsafe"
            elif status != "unsafe":
                status = "caution"
            
            ingredient_confidence = max(ingredient_confidence, confidence)
            detected_allergens.add(rule["name"])
            
            risk = _severity_score(severity, rule["severity_score"])
            if is_trace_context:
                risk = min(risk, 80)
            max_risk_score = max(max_risk_score, risk)
            
            reason = (
                f"Label warning may contain {rule['name']} ({keyword})"
                if is_trace_context
                else f"{ingredient} contains {rule['name']}"
            )
            reasons.append(reason)
            matches.append({
                "type": "allergen",
                "id": rule["id"],
                "name": rule["name"],
                "keyword": keyword,
                "match_type": "cross_contact" if is_trace_context else match_type,
                "severity": severity,
                "confidence": round(confidence, 2),
            })
            allergen_alerts.append(reason)

        # Check dietary restrictions
        for diet_id in dietary_ids:
            rule = DIETARY_RULES[diet_id]

            # Safe-ingredient guard: if this ingredient is a known-safe item for
            # this diet, skip the forbidden check entirely.
            # E.g. "olive oil" is safe for vegans even though "oil" might match nothing,
            # but "cream of tartar" or "coconut cream" could falsely match "cream".
            safe_list = rule.get("safe_ingredients", [])
            norm_ingredient = normalized  # already normalized above
            if any(safe_item in norm_ingredient or norm_ingredient in safe_item
                   for safe_item in safe_list):
                continue

            keyword, match_type, confidence = _find_keyword_match(normalized, rule["forbidden"])
            if not keyword:
                continue

            if rule["severity"] == "high":
                status = "unsafe"
            elif status != "unsafe":
                status = "caution"
            
            ingredient_confidence = max(ingredient_confidence, min(confidence, 0.94))
            max_risk_score = max(max_risk_score, rule["severity_score"])
            reason = f"{ingredient} may violate your {rule['name']} restriction"
            reasons.append(reason)
            matches.append({
                "type": "dietary",
                "id": diet_id,
                "name": rule["name"],
                "keyword": keyword,
                "match_type": match_type,
                "severity": rule["severity"],
                "confidence": round(confidence, 2),
            })
            dietary_alerts.append(reason)

        confidence_values.append(ingredient_confidence)
        details.append({
            "ingredient": ingredient,
            "normalized": normalized,
            "status": status,
            "confidence": round(ingredient_confidence, 2),
            "reasons": list(dict.fromkeys(reasons)),
            "matches": matches,
        })

    # Second pass: scan the full raw text for allergens hidden inside parenthetical
    # sub-lists (e.g. 'soy sauce (water, soybeans, wheat, salt)' or
    # 'emulsifiers (soy lecithin, 476)') that were split out and might have been missed.
    already_detected_ids = detected_allergens  # set of rule names already flagged
    full_text_extra = normalize_text(raw_text if raw_text else " ".join(parsed_ingredients))

    # Safe processing-aid terms that should NOT trigger allergen hits on their own
    SAFE_PROCESSING_AIDS = {
        'sunflower lecithin', 'sunflower oil', 'cocoa butter', 'coconut aminos',
        'liquid aminos', 'almond extract', 'almond flavor', 'almond flavour',
        'rice milk', 'oat milk',
    }

    for rule_id in allergy_ids:
        if rule_id in already_detected_ids:
            continue
        rule = ALLERGEN_RULES.get(rule_id)
        if not rule:
            continue
        keyword, match_type, confidence = _find_keyword_match(full_text_extra, rule["keywords"])
        if not keyword:
            continue
        # Check the keyword isn't from a known-safe processing aid
        idx = full_text_extra.find(keyword)
        context = full_text_extra[max(0, idx - 30): idx + len(keyword) + 30]
        if any(safe in context for safe in SAFE_PROCESSING_AIDS):
            continue
        severity = allergy_severity.get(rule_id, rule["severity"])
        is_trace = any(pattern in full_text_extra for pattern in CROSS_CONTACT_PATTERNS)
        if not is_trace:
            status = "unsafe"
        else:
            status = "caution"
        ingredient_confidence = max(_ingredient_base_confidence(keyword), confidence)
        detected_allergens.add(rule["name"])
        risk = _severity_score(severity, rule["severity_score"])
        if is_trace:
            risk = min(risk, 80)
        max_risk_score = max(max_risk_score, risk)
        reason = (
            f"Label warning may contain {rule['name']} ({keyword})"
            if is_trace
            else f"Ingredient text contains {rule['name']} ({keyword})"
        )
        allergen_alerts.append(reason)
        confidence_values.append(ingredient_confidence)
        details.append({
            "ingredient": keyword,
            "normalized": normalize_text(keyword),
            "status": status,
            "confidence": round(ingredient_confidence, 2),
            "reasons": [reason],
            "matches": [{
                "type": "allergen",
                "id": rule["id"],
                "name": rule["name"],
                "keyword": keyword,
                "match_type": "full_text_scan",
                "severity": severity,
                "confidence": round(confidence, 2),
            }],
        })

    # Check cross-contact warnings
    existing_cross_contact = {
        (match.get("id"), match.get("keyword"))
        for detail in details
        for match in detail.get("matches", [])
        if match.get("match_type") == "cross_contact"
    }

    for rule, keyword, match_type, confidence in _cross_contact_matches(full_text, allergy_ids):
        if (rule["id"], keyword) in existing_cross_contact:
            continue
        severity = allergy_severity.get(rule["id"], rule["severity"])
        detected_allergens.add(rule["name"])
        max_risk_score = max(max_risk_score, min(_severity_score(severity, rule["severity_score"]), 80))
        reason = f"Label warning may contain {rule['name']} ({keyword})"
        allergen_alerts.append(reason)
        details.append({
            "ingredient": reason,
            "normalized": normalize_text(reason),
            "status": "caution",
            "confidence": round(confidence, 2),
            "reasons": [reason],
            "matches": [{
                "type": "allergen",
                "id": rule["id"],
                "name": rule["name"],
                "keyword": keyword,
                "match_type": match_type,
                "severity": severity,
                "confidence": round(confidence, 2),
            }],
        })
        confidence_values.append(confidence)

    # Determine risk level
    if any(item["status"] == "unsafe" for item in details):
        risk_level = "unsafe"
    elif any(item["status"] == "caution" for item in details):
        risk_level = "caution"
    else:
        risk_level = "safe"

    # Recommendations based on risk level
    if risk_level == "unsafe":
        recommendations = [
            "⚠️ Do not consume this product - it contains ingredients that match your allergy profile.",
            "Choose an alternative product without the flagged allergens.",
        ]
    elif risk_level == "caution":
        recommendations = [
            "⚠️ Review the flagged ingredients carefully before consuming.",
            "Check for cross-contamination warnings on the package.",
            "Contact the manufacturer if you need clarification.",
        ]
    else:
        recommendations = [
            "✅ No allergens detected - this product appears safe for your profile.",
            "Always double-check labels as formulations may change.",
        ]

    hazard_score = min(int(max_risk_score), 100)
    allergen_count = len(detected_allergens)
    
    if confidence_values:
        final_confidence = round(sum(confidence_values) / len(confidence_values), 2)
    elif parsed_ingredients or full_text:
        final_confidence = 0.72
    else:
        final_confidence = 0.0

    # Final risk score (higher = more dangerous)
    risk_score = _to_risk_score(risk_level, hazard_score, allergen_count)

    return {
        "risk_level": risk_level,
        "risk_score": risk_score,
        "hazard_score": hazard_score,
        "confidence": final_confidence,
        "ingredients": [detail["ingredient"] for detail in details] or parsed_ingredients,
        "alerts": list(dict.fromkeys(allergen_alerts + dietary_alerts)),
        "allergen_alerts": list(dict.fromkeys(allergen_alerts)),
        "dietary_alerts": list(dict.fromkeys(dietary_alerts)),
        "allergens_detected": sorted(detected_allergens),
        "ingredient_details": details,
        "recommendations": recommendations,
        "analysis_basis": {
            "ingredients_checked": len(parsed_ingredients),
            "profile_allergies_checked": sorted(allergy_ids),
            "dietary_rules_checked": sorted(dietary_ids),
            "cross_contact_checked": True,
        },
    }


def build_general_analysis(ingredients):
    """Build general analysis without user profile."""
    parsed_ingredients = parse_ingredients_input(ingredients)
    detected = set()
    details = []
    
    for ingredient in parsed_ingredients:
        normalized = normalize_text(ingredient)
        matches = []
        for rule in ALLERGEN_RULES.values():
            keyword, match_type, confidence = _find_keyword_match(normalized, rule["keywords"])
            if keyword:
                detected.add(rule["name"])
                matches.append({
                    "type": "allergen",
                    "id": rule["id"],
                    "name": rule["name"],
                    "keyword": keyword,
                    "match_type": match_type,
                    "severity": rule["severity"],
                    "confidence": round(confidence, 2),
                })
        ingredient_confidence = _ingredient_base_confidence(ingredient)
        if matches:
            confidences = [m["confidence"] for m in matches]
            ingredient_confidence = sum(confidences) / len(confidences)
            
        details.append({
            "ingredient": ingredient,
            "normalized": normalized,
            "status": "caution" if matches else "safe",
            "confidence": round(ingredient_confidence, 2),
            "reasons": [f"{ingredient} may contain {match['name']}" for match in matches],
            "matches": matches,
        })

    if detected:
        alert_message = f"This product contains or may contain: {', '.join(sorted(detected))}"
    else:
        alert_message = "No common allergens detected in this product"

    if details:
        overall_confidence = sum(d["confidence"] for d in details) / len(details)
    elif parsed_ingredients:
        overall_confidence = 0.72
    else:
        overall_confidence = 0.0

    allergen_count = len(detected)
    risk_level_gen = "caution" if detected else "safe"
    # For general (no user profile) scans, use a hazard_score based on detected severity
    hazard_score_gen = 55 if detected else 0  # assume medium severity when no profile
    risk_score_gen = _to_risk_score(risk_level_gen, hazard_score_gen, allergen_count)

    return {
        "ingredients": parsed_ingredients,
        "risk_level": risk_level_gen,
        "risk_score": risk_score_gen,
        "hazard_score": hazard_score_gen,
        "alerts": [alert_message],
        "allergens_detected": sorted(detected),
        "ingredient_details": details,
        "confidence": round(overall_confidence, 2),
        "recommendations": [
            "Create a user profile for personalized allergen detection." if not detected else
            "Create a profile to see if these allergens match your restrictions."
        ],
    }