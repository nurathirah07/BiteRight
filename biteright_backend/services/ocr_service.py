import cv2
import pytesseract
import numpy as np
from PIL import Image
import io
import re
import os
import shutil


def _configure_tesseract():
    """Locate Tesseract OCR binary across common install paths."""
    env_path = os.environ.get('TESSERACT_CMD') or os.environ.get('TESSERACT_PATH')
    candidates = [
        env_path,
        shutil.which('tesseract'),
        r'C:\Program Files\Tesseract-OCR\tesseract.exe',
        r'C:\Program Files (x86)\Tesseract-OCR\tesseract.exe',
        '/usr/bin/tesseract',
        '/usr/local/bin/tesseract',
        '/opt/homebrew/bin/tesseract',
    ]
    for candidate in candidates:
        if candidate and os.path.isfile(candidate):
            pytesseract.pytesseract.tesseract_cmd = candidate
            return candidate
    return None


TESSERACT_PATH = _configure_tesseract()

def preprocess_image_multiple(image_bytes):
    """Apply complementary preprocessing techniques for noisy package labels."""
    nparr = np.frombuffer(image_bytes, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    
    if img is None:
        return None, "Failed to decode image"
    
    height, width = img.shape[:2]
    scale_factor = min(4.0, max(1.5, 1800 / max(min(height, width), 1)))
    new_width = int(width * scale_factor)
    new_height = int(height * scale_factor)
    img = cv2.resize(img, (new_width, new_height), interpolation=cv2.INTER_CUBIC)
    
    processed_images = []

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    gray = cv2.fastNlMeansDenoising(gray, None, 12, 7, 21)
    clahe = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8, 8)).apply(gray)

    kernel = np.array([[0, -1, 0], [-1, 5, -1], [0, -1, 0]])
    sharpened = cv2.filter2D(clahe, -1, kernel)

    _, otsu = cv2.threshold(sharpened, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    processed_images.append(("CLAHE + Otsu", otsu))

    adaptive = cv2.adaptiveThreshold(
        sharpened,
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        31,
        9,
    )
    processed_images.append(("Adaptive Gaussian", adaptive))

    return processed_images, None

def _ocr_score(text, avg_confidence):
    cleaned = text.strip()
    if not cleaned:
        return 0

    alpha_ratio = sum(ch.isalpha() for ch in cleaned) / max(len(cleaned), 1)
    separator_bonus = cleaned.count(",") * 25 + cleaned.count(";") * 20
    ingredient_bonus = 600 if re.search(r"\bingredients?\b", cleaned, re.IGNORECASE) else 0
    allergen_bonus = 250 if re.search(r"\bcontains?\b", cleaned, re.IGNORECASE) else 0
    readable_bonus = int(alpha_ratio * 300)
    return len(cleaned) + separator_bonus + ingredient_bonus + allergen_bonus + readable_bonus + int(avg_confidence * 8)

def _run_tesseract(image, config):
    data = pytesseract.image_to_data(
        image,
        config=config,
        output_type=pytesseract.Output.DICT,
    )
    words = []
    confidences = []
    for word, conf in zip(data.get("text", []), data.get("conf", [])):
        word = str(word).strip()
        try:
            confidence = float(conf)
        except (TypeError, ValueError):
            confidence = -1
        if word:
            words.append(word)
        if confidence >= 0:
            confidences.append(confidence)
    text = " ".join(words)
    avg_confidence = sum(confidences) / len(confidences) if confidences else 0
    return text, avg_confidence

def extract_with_multiple_strategies(image_bytes):
    """Try OCR strategies and return the best result (bounded for speed)."""
    processed_images, error = preprocess_image_multiple(image_bytes)
    
    if error:
        return {'success': False, 'error': error}
    
    best_result = None
    best_score = 0
    best_strategy = None
    best_ocr_confidence = 0
    
    # Fewer PSM modes keeps extraction under mobile timeouts.
    psm_modes = [6, 11]
    early_exit_score = 1400
    done = False

    for strategy_name, processed_img in processed_images:
        if done:
            break
        for psm in psm_modes:
            try:
                config = f"--oem 3 --psm {psm} -c preserve_interword_spaces=1"
                text, avg_confidence = _run_tesseract(processed_img, config)
                score = _ocr_score(text, avg_confidence)

                if score > best_score:
                    best_score = score
                    best_result = text
                    best_strategy = f"{strategy_name}, PSM {psm}"
                    best_ocr_confidence = avg_confidence

                if score >= early_exit_score and re.search(
                    r"\bingredients?\b", text, re.IGNORECASE
                ):
                    done = True
                    break
            except Exception:
                continue
    
    if not best_result:
        return {
            'success': False,
            'error': "No text extracted from image"
        }
    
    return {
        'success': True,
        'raw_text': best_result,
        'strategy_used': best_strategy or 'Multiple strategies',
        'ocr_confidence': round(best_ocr_confidence / 100, 2),
    }

def extract_ingredients(image_bytes):
    """Enhanced extraction with multiple strategies"""
    try:
        if not TESSERACT_PATH:
            return {
                'success': False,
                'error': (
                    'Tesseract OCR is not installed. Install Tesseract and set '
                    'TESSERACT_CMD to its executable path.'
                ),
            }

        # First try multiple strategies
        result = extract_with_multiple_strategies(image_bytes)
        
        if not result['success']:
            return result
        
        extracted_text = result['raw_text']
        
        if not extracted_text.strip():
            return {
                'success': False,
                'error': "No text extracted from image"
            }
        
        # Clean the text
        cleaned_result = clean_extracted_text(extracted_text)
        
        return {
            'success': True,
            'raw_text': extracted_text.strip(),
            'cleaned_text': cleaned_result['ingredients'],
            'ingredients_list': cleaned_result['ingredients_list'],
            'strategy_used': result.get('strategy_used'),
            'ocr_confidence': result.get('ocr_confidence', 0.0),
            'warning': cleaned_result.get('warning')
        }
    except Exception as e:
        return {
            'success': False,
            'error': f"OCR processing failed: {str(e)}"
        }

def clean_extracted_text(text):
    """Enhanced cleaning for ingredient lists"""
    result = {
        'ingredients': [],
        'ingredients_list': [],
        'warning': None
    }
    
    try:
        text = fix_common_ocr_errors(text)
        text = re.sub(r'\s+', ' ', text.strip())
        
        # Try to find the "INGREDIENTS:" section
        ingredients_patterns = [
            r'INGREDIENTS?:?\s*(.*?)(?=\n\n|\n[A-Z]|\Z)',
            r'INGREDIENTS?:?\s*(.*?)(?=\.\s*[A-Z]|$)',
            r'Contains:?\s*(.*?)(?=\.|$)',
            r'^([A-Za-z\s,]+?)(?=\d|Nutrition|Calories|Serving)'
        ]
        
        ingredients_text = None
        for pattern in ingredients_patterns:
            match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
            if match:
                ingredients_text = match.group(1).strip()
                break
        
        # If no specific section found, try to extract from full text
        if not ingredients_text:
            # Look for comma-separated lists that look like ingredients
            comma_lists = re.findall(r'([A-Za-z\s,]+(?:, [A-Za-z\s]+)+)', text)
            if comma_lists:
                ingredients_text = max(comma_lists, key=len)
            else:
                ingredients_text = text
                result['warning'] = "Could not identify ingredient section, using full text"
        
        # Clean the ingredient text
        ingredients_text = re.sub(r'\([^)]*\)', '', ingredients_text)  # Remove parentheses
        ingredients_text = re.sub(r'\d+%?', '', ingredients_text)  # Remove percentages
        ingredients_text = re.sub(r'\d+\s*(g|ml|mg|oz|lb|tsp|tbsp)', '', ingredients_text, flags=re.IGNORECASE)
        
        # Split by commas
        ingredients_list = [ing.strip() for ing in ingredients_text.split(',') if ing.strip()]
        
        # Clean each ingredient
        cleaned_ingredients = []
        for ingredient in ingredients_list:
            # Remove common non-ingredient words
            ingredient = re.sub(r'\b(contains|may contain|less than|and|or)\b.*$', '', ingredient, flags=re.IGNORECASE)
            ingredient = ingredient.strip(' .,:;')
            
            # Only keep if it has letters and is longer than 2 characters
            if ingredient and len(ingredient) > 2 and re.search(r'[a-zA-Z]', ingredient):
                ingredient = ingredient.lower()
                cleaned_ingredients.append(ingredient)
        
        # Remove duplicates while preserving order
        seen = set()
        unique_ingredients = []
        for ing in cleaned_ingredients:
            if ing not in seen:
                seen.add(ing)
                unique_ingredients.append(ing)
        
        result['ingredients'] = ', '.join(unique_ingredients)
        result['ingredients_list'] = unique_ingredients
        
    except Exception as e:
        result['warning'] = f"Text cleaning error: {str(e)}"
        result['ingredients'] = text
        result['ingredients_list'] = [text]
    
    return result

def fix_common_ocr_errors(text):
    fixes = {
        "ingrediants": "ingredients",
        "ingredlents": "ingredients",
        "contalns": "contains",
        "miik": "milk",
        "mllk": "milk",
        "wbeat": "wheat",
        "wheaf": "wheat",
        "soya bean": "soybean",
        "peant": "peanut",
        "peanutt": "peanut",
        "seseme": "sesame",
        "glulen": "gluten",
        "sait": "salt",
        "suger": "sugar",
    }
    for wrong, correct in fixes.items():
        text = re.sub(rf"\b{re.escape(wrong)}\b", correct, text, flags=re.IGNORECASE)
    return text

def extract_ingredients_from_path(image_path):
    """Extract ingredients from image file path"""
    try:
        with open(image_path, 'rb') as f:
            image_bytes = f.read()
        return extract_ingredients(image_bytes)
    except Exception as e:
        return {
            'success': False,
            'error': f"Failed to read image file: {str(e)}"
        }
