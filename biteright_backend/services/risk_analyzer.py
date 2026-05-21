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
    "shared equipment",
    "same line",
    "same facility",
]

SCIENTIFIC_NAME_ALIASES = {
    "arachis hypogaea": "peanuts",
    "arachis oil": "peanuts",
    "glycine max": "soy",
    "triticum aestivum": "wheat",
    "hordeum vulgare": "gluten",
    "secale cereale": "gluten",
    "sesamum indicum": "sesame",
    "gallus gallus": "eggs",
    "gadus morhua": "fish",
    "salmo salar": "fish",
    "thunnus": "fish",
    "crustacea": "shellfish",
}

EXTRA_ALLERGEN_ALIASES = {
    "peanuts": [
        "peanut butter",
        "peanut oil",
        "groundnut",
        "ground nut",
        "kacang tanah",
    ],
    "tree_nuts": [
        "almond",
        "almonds",
        "walnut",
        "walnuts",
        "cashew",
        "cashews",
        "pecan",
        "pecans",
        "pistachio",
        "pistachios",
        "hazelnut",
        "hazelnuts",
        "macadamia",
        "brazil nut",
        "pine nut",
        "praline",
        "marzipan",
    ],
    "milk": [
        "milk solids",
        "skim milk",
        "nonfat milk",
        "whole milk",
        "condensed milk",
        "evaporated milk",
        "milk powder",
        "caseinate",
        "sodium caseinate",
        "calcium caseinate",
        "lactalbumin",
        "lactoglobulin",
        "ghee",
        "susu",
    ],
    "eggs": ["egg white", "egg yolk", "lysozyme", "albumen", "telur"],
    "soy": [
        "soybean",
        "soybeans",
        "soy protein",
        "textured vegetable protein",
        "hydrolyzed soy protein",
        "hydrolyzed vegetable protein",
        "tamari",
        "tauhu",
    ],
    "wheat": [
        "wheat flour",
        "whole wheat",
        "bread flour",
        "cake flour",
        "atta",
        "farina",
        "couscous",
    ],
    "gluten": [
        "wheat flour",
        "barley malt",
        "malt extract",
        "malt vinegar",
        "triticale",
        "seitan",
    ],
    "fish": ["fish sauce", "ikan bilis", "bonito", "surimi"],
    "shellfish": ["prawns", "oyster", "oysters", "mussel", "mussels", "clam", "clams", "squid"],
    "sesame": ["sesame oil", "sesame seed", "sesame seeds", "benne", "til"],
}

DIETARY_EXTRA_FORBIDDEN = {
    "halal": [
        "ham",
        "bacon",
        "lard",
        "pork fat",
        "pork gelatin",
        "wine",
        "beer",
        "liquor",
        "rum",
        "brandy",
        "ethanol",
        "vanilla extract",
    ],
    "vegetarian": ["beef", "pork", "lamb", "poultry", "anchovy", "anchovies", "prawn", "shrimp"],
    "vegan": ["butter", "cheese", "cream", "lactose", "milk powder", "albumin", "shellac", "carmine"],
    "keto": ["dextrose", "maltodextrin", "glucose", "fructose", "tapioca starch", "corn starch"],
    "diabetic": ["glucose", "fructose", "sucrose", "molasses", "maltodextrin", "agave"],
    "low_sodium": ["disodium", "sodium bicarbonate", "sodium chloride", "sodium citrate"],
}

OCR_FIXES = {
    "miik": "milk",
    "mik": "milk",
    "mllk": "milk",
    "soyabean": "soybean",
    "soya bean": "soybean",
    "peant": "peanut",
    "peanutt": "peanut",
    "peantus": "peanuts",
    "seseme": "sesame",
    "sesam": "sesame",
    "wbeat": "wheat",
    "wheaf": "wheat",
    "glulen": "gluten",
}


def normalize_key(value):
    return str(value or "").strip().lower().replace("-", "_").replace(" ", "_")


def normalize_text(value):
    text = str(value or "").lower()
    text = text.replace("&", " and ")
    for wrong, correct in OCR_FIXES.items():
        text = re.sub(rf"\b{re.escape(wrong)}\b", correct, text)
    text = re.sub(r"[\u2018\u2019]", "'", text)
    text = re.sub(r"[^a-z0-9%+'\-/\s,;:.()]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def split_ingredient_text(text):
    text = INGREDIENT_PREFIX_RE.sub(" ", str(text or ""))
    text = re.sub(r"\b(?:nutrition facts?|serving size|calories|barcode|net weight)\b.*", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"\s+", " ", text).strip(" .,:;")
    if not text:
        return []

    separators = r",|;|\n|\. (?=[A-Z])"
    parts = re.split(separators, text)
    ingredients = []
    for part in parts:
        part = part.strip(" .,:;")
        if not part:
            continue
        subparts = re.split(r"\s+(?:and|or)\s+(?=[a-zA-Z(])", part, flags=re.IGNORECASE)
        for subpart in subparts:
            cleaned = subpart.strip(" .,:;")
            if len(cleaned) > 1 and re.search(r"[a-zA-Z]", cleaned):
                ingredients.append(cleaned)
    return list(dict.fromkeys(ingredients))


def parse_ingredients_input(ingredients_input):
    if isinstance(ingredients_input, list):
        values = []
        for item in ingredients_input:
            values.extend(split_ingredient_text(str(item)))
        return values
    return split_ingredient_text(str(ingredients_input)) or [str(ingredients_input or "").strip()]


def _allergen_rules():
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
    rules = {}
    for diet in DIETARY_OPTIONS:
        diet_id = normalize_key(diet["id"])
        forbidden = [str(item).lower() for item in diet.get("forbidden", [])]
        forbidden.extend(DIETARY_EXTRA_FORBIDDEN.get(diet_id, []))
        rules[diet_id] = {
            "id": diet_id,
            "name": diet.get("label", diet_id),
            "severity": diet.get("severity", "medium"),
            "severity_score": diet.get("severity_score", 50),
            "forbidden": sorted({normalize_text(a) for a in forbidden if a}, key=len, reverse=True),
        }
    return rules


ALLERGEN_RULES = _allergen_rules()
DIETARY_RULES = _dietary_rules()


def _selected_allergy_ids(user_allergies):
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
        for rule in ALLERGEN_RULES.values():
            rule_keys = {rule["id"], normalize_key(rule["name"])}
            rule_keys.update(normalize_key(keyword) for keyword in rule["keywords"])
            if profile_key in rule_keys:
                ids.add(rule["id"])
                severity_by_id[rule["id"]] = severity
                break
        else:
            ids.add(profile_key)
            severity_by_id[profile_key] = severity
    return ids, severity_by_id


def _selected_diet_ids(user_dietary):
    selected = set()
    for diet in user_dietary or []:
        diet_id = normalize_key(diet.get("id") if isinstance(diet, dict) else diet)
        if diet_id in DIETARY_RULES:
            selected.add(diet_id)
    return selected


def _phrase_match(text, keyword):
    if not keyword:
        return False
    return re.search(rf"(?<![a-z0-9]){re.escape(keyword)}(?![a-z0-9])", text) is not None


def _fuzzy_match_token(tokens, keyword):
    if " " in keyword or len(keyword) < 5:
        return None
    candidates = [token for token in tokens if len(token) >= 4]
    if not candidates:
        return None
    best = max((SequenceMatcher(None, token, keyword).ratio(), token) for token in candidates)
    if best[0] >= 0.88:
        return best[1]
    return None


def _find_keyword_match(text, keywords):
    tokens = re.findall(r"[a-z0-9]+", text)
    for keyword in keywords:
        if _phrase_match(text, keyword):
            return keyword, "exact", 0.98
        fuzzy_token = _fuzzy_match_token(tokens, keyword)
        if fuzzy_token:
            return fuzzy_token, "fuzzy", 0.82
    return None, None, 0.0


def _cross_contact_matches(full_text, allergy_ids):
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
                matches.append((rule, keyword, match_type or "cross_contact", min(confidence, 0.86)))
    return matches


def _severity_score(severity, default_score):
    if severity == "high":
        return max(default_score, 85)
    if severity == "medium":
        return max(default_score, 55)
    return max(default_score, 25)


def build_personalized_analysis(ingredients, user_allergies, user_dietary, raw_text=None):
    parsed_ingredients = parse_ingredients_input(ingredients)
    allergy_ids, allergy_severity = _selected_allergy_ids(user_allergies)
    dietary_ids = _selected_diet_ids(user_dietary)
    full_text = normalize_text(raw_text if raw_text else " ".join(parsed_ingredients))

    details = []
    allergen_alerts = []
    dietary_alerts = []
    detected_allergens = set()
    max_risk_score = 0
    confidence_values = []

    for ingredient in parsed_ingredients:
        normalized = normalize_text(ingredient)
        is_trace_context = any(pattern in normalized for pattern in CROSS_CONTACT_PATTERNS)
        status = "safe"
        reasons = []
        matches = []
        ingredient_confidence = 0.72

        for rule_id in allergy_ids:
            rule = ALLERGEN_RULES.get(rule_id)
            if not rule:
                continue
            keyword, match_type, confidence = _find_keyword_match(normalized, rule["keywords"])
            if not keyword:
                continue

            severity = allergy_severity.get(rule_id, rule["severity"])
            status = "caution" if is_trace_context else "unsafe"
            ingredient_confidence = max(ingredient_confidence, confidence)
            detected_allergens.add(rule["name"])
            risk = _severity_score(severity, rule["severity_score"])
            if is_trace_context:
                risk = min(risk, 80)
            max_risk_score = max(max_risk_score, risk)
            reason = (
                f"Label warning may contain {rule['name']} ({keyword})"
                if is_trace_context
                else f"{ingredient} matches your {rule['name']} allergy"
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

        for diet_id in dietary_ids:
            rule = DIETARY_RULES[diet_id]
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

    if any(item["status"] == "unsafe" for item in details):
        risk_level = "unsafe"
    elif any(item["status"] == "caution" for item in details):
        risk_level = "caution"
    else:
        risk_level = "safe"

    if risk_level == "unsafe":
        recommendations = [
            "Do not consume this product unless the label is verified by a trusted source.",
            "Choose an alternative without the flagged allergen or dietary conflict.",
        ]
    elif risk_level == "caution":
        recommendations = [
            "Review the flagged ingredient or trace warning before consuming.",
            "If this is a severe allergy, confirm with the manufacturer.",
        ]
    else:
        recommendations = [
            "No conflicts were detected for the current profile.",
            "Keep the ingredient text and user profile updated for the most accurate result.",
        ]

    return {
        "risk_level": risk_level,
        "risk_score": min(int(max_risk_score), 100),
        "confidence": round(sum(confidence_values) / len(confidence_values), 2) if confidence_values else 0.0,
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
        details.append({
            "ingredient": ingredient,
            "normalized": normalized,
            "status": "caution" if matches else "safe",
            "confidence": 0.92 if matches else 0.72,
            "reasons": [f"{ingredient} may contain {match['name']}" for match in matches],
            "matches": matches,
        })

    return {
        "ingredients": parsed_ingredients,
        "risk_level": "caution" if detected else "safe",
        "risk_score": 35 if detected else 0,
        "alerts": [f"Contains or may contain {name}" for name in sorted(detected)] or ["No common allergens detected"],
        "allergens_detected": sorted(detected),
        "ingredient_details": details,
        "confidence": 0.9 if detected else 0.75,
    }
