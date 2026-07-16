# biteright_backend/services/ocr_service.py
"""
OCR Service for BiteRight - Enhanced for ingredient label extraction
"""

import os
import re
import cv2
import numpy as np
import pytesseract
import requests
from PIL import Image


def _configure_tesseract():
    """Locate Tesseract OCR binary."""
    env_path = os.environ.get('TESSERACT_CMD') or os.environ.get('TESSERACT_PATH')
    
    if env_path and os.path.exists(env_path):
        print(f"✓ Using TESSERACT_CMD: {env_path}")
        return env_path
    
    candidates = [
        r'C:\Program Files\Tesseract-OCR\tesseract.exe',
        r'C:\Program Files (x86)\Tesseract-OCR\tesseract.exe',
        '/usr/bin/tesseract',
        '/usr/local/bin/tesseract',
        '/opt/homebrew/bin/tesseract',
    ]
    
    for candidate in candidates:
        if os.path.exists(candidate):
            print(f"✓ Found Tesseract at: {candidate}")
            return candidate
    
    print("✗ Tesseract not found!")
    return None


TESSERACT_PATH = _configure_tesseract()
if TESSERACT_PATH:
    pytesseract.pytesseract.tesseract_cmd = TESSERACT_PATH


def preprocess_image_advanced(image_bytes):
    """
    Advanced preprocessing with multiple techniques for difficult images
    """
    nparr = np.frombuffer(image_bytes, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    
    if img is None:
        return None, "Failed to decode image"
    
    height, width = img.shape[:2]
    processed_versions = []
    
    # 1. Original size
    original_gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    processed_versions.append(("Original", original_gray))
    
    # 2. Upscaled version (2x)
    if width < 1500:
        new_width = int(width * 2)
        new_height = int(height * 2)
        upscaled = cv2.resize(img, (new_width, new_height), interpolation=cv2.INTER_CUBIC)
        upscaled_gray = cv2.cvtColor(upscaled, cv2.COLOR_BGR2GRAY)
        processed_versions.append(("Upscaled 2x", upscaled_gray))
    
    # 3. Upscaled version (3x for very small text)
    if width < 1000:
        new_width = int(width * 3)
        new_height = int(height * 3)
        upscaled3 = cv2.resize(img, (new_width, new_height), interpolation=cv2.INTER_CUBIC)
        upscaled3_gray = cv2.cvtColor(upscaled3, cv2.COLOR_BGR2GRAY)
        processed_versions.append(("Upscaled 3x", upscaled3_gray))
    
    # For each grayscale version, apply different enhancements
    final_versions = []
    
    for name, gray in processed_versions:
        # Version A: Denoised + Sharpened
        denoised = cv2.fastNlMeansDenoising(gray, None, 10, 7, 21)
        kernel = np.array([[-1, -1, -1], [-1, 9, -1], [-1, -1, -1]])
        sharpened = cv2.filter2D(denoised, -1, kernel)
        final_versions.append((f"{name}_Sharp", sharpened))
        
        # Version B: CLAHE for contrast
        clahe = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8, 8))
        enhanced = clahe.apply(gray)
        final_versions.append((f"{name}_CLAHE", enhanced))
        
        # Version C: Binary threshold (Otsu)
        _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        final_versions.append((f"{name}_Binary", binary))
        
        # Version D: Adaptive threshold
        adaptive = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 15, 8)
        final_versions.append((f"{name}_Adaptive", adaptive))
        
        # Version E: Morphological cleaning
        kernel_morph = np.ones((2, 2), np.uint8)
        cleaned = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel_morph)
        cleaned = cv2.morphologyEx(cleaned, cv2.MORPH_OPEN, kernel_morph)
        final_versions.append((f"{name}_Cleaned", cleaned))
    
    return final_versions, None


def extract_text_with_config(image, psm_mode):
    """
    Extract text with specific PSM mode
    """
    try:
        # Different configs for different text types
        configs = [
            f'--oem 3 --psm {psm_mode}',
            f'--oem 3 --psm {psm_mode} -c tessedit_char_whitelist="ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz ,.-/()%"',
        ]
        
        best_text = ""
        best_score = 0
        
        for config in configs:
            text = pytesseract.image_to_string(image, config=config)
            
            # Score based on content
            score = 0
            text_lower = text.lower()
            
            if 'ingredient' in text_lower:
                score += 200
            if 'contains' in text_lower:
                score += 150
            if 'wheat' in text_lower or 'milk' in text_lower or 'soy' in text_lower:
                score += 100
            
            # Count real words
            words = re.findall(r'\b[a-z]{3,}\b', text_lower)
            score += len(words) * 2
            
            # Count commas (ingredient separators)
            score += text.count(',') * 10
            
            if score > best_score:
                best_score = score
                best_text = text
        
        return best_text, best_score
    except Exception as e:
        return "", 0


def extract_with_ocr_space(image_bytes, api_key='4a3c5654e388957'):
    """
    Extract text using OCR.Space API
    """
    try:
        response = requests.post(
            'https://api.ocr.space/parse/image',
            files={'filename': ('image.jpg', image_bytes, 'image/jpeg')},
            data={
                'apikey': api_key,
                'language': 'eng',
                'OCREngine': '2'
            },
            timeout=15
        )
        result = response.json()
        if not result.get('IsErroredOnProcessing') and result.get('ParsedResults'):
            text = result['ParsedResults'][0]['ParsedText']
            return text, True
        return "", False
    except Exception as e:
        print(f"OCR Space API error: {e}")
        return "", False


def _estimate_ocr_confidence(raw_text: str, parsed_ingredients: list) -> float:
    """
    Estimate real OCR extraction confidence from text quality signals.

    Signals used (each contributes 0-1, weighted sum capped at 0.92):
      1. Word quality  — fraction of tokens that are well-formed English words
                         (3+ chars, not all digits, no run of unlikely chars)
      2. Structure     — does the text contain an ingredients header?
      3. Comma ratio   — fraction of ingredients separated by commas (good parsing signal)
      4. Ingredient count — more parsed ingredients = more content extracted
      5. Noise penalty — high rate of non-alpha characters lowers confidence
    """
    if not raw_text or not parsed_ingredients:
        return 0.40

    text_lower = raw_text.lower()
    total_chars = max(len(raw_text), 1)

    # 1. Well-formed word ratio
    all_tokens = re.findall(r'\S+', raw_text)
    if all_tokens:
        good_tokens = [
            t for t in all_tokens
            if re.fullmatch(r"[a-zA-Z''\-]{3,}", t)
        ]
        word_quality = len(good_tokens) / len(all_tokens)
    else:
        word_quality = 0.0

    # 2. Structural signal — ingredients header present
    has_header = 1.0 if re.search(r'\b(ingredients?|contains)\b', text_lower) else 0.0

    # 3. Comma ratio — commas per ingredient (up to 1.0 at ≥0.5 commas/ingredient)
    comma_count = raw_text.count(',')
    ing_count = max(len(parsed_ingredients), 1)
    comma_ratio = min(1.0, (comma_count / ing_count) / 0.5)

    # 4. Ingredient count signal (saturates at 15 ingredients)
    ing_signal = min(1.0, ing_count / 15)

    # 5. Noise penalty — fraction of chars that are clearly noise
    noise_chars = len(re.findall(r'[^a-zA-Z0-9 ,.()\-/%\'\n]', raw_text))
    noise_ratio = noise_chars / total_chars
    noise_penalty = max(0.0, 1.0 - noise_ratio * 5)  # 20% noise → 0 penalty left

    # Weighted combination
    raw_conf = (
        word_quality  * 0.35 +
        has_header    * 0.20 +
        comma_ratio   * 0.20 +
        ing_signal    * 0.15 +
        noise_penalty * 0.10
    )

    # Scale to [0.40, 0.92] — we never claim perfect confidence from OCR alone
    confidence = 0.40 + raw_conf * 0.52
    return round(min(0.92, max(0.40, confidence)), 2)


def extract_ingredients(image_bytes):
    """
    Main function - tries OCR API first, falls back to Tesseract strategies
    """
    try:
        # 1. Try OCR Space API
        best_text = ""
        best_score = 0
        best_strategy = ""
        
        api_text, api_success = extract_with_ocr_space(image_bytes)
        
        if api_success and api_text.strip():
            score = 0
            text_lower = api_text.lower()
            if 'ingredient' in text_lower: score += 200
            if 'contains' in text_lower: score += 150
            if 'wheat' in text_lower or 'milk' in text_lower or 'soy' in text_lower: score += 100
            words = re.findall(r'\b[a-z]{3,}\b', text_lower)
            score += len(words) * 2
            score += api_text.count(',') * 10
            
            best_text = api_text
            best_score = score
            best_strategy = "OCR Space API"
            
        # 2. If API text has a low score, try Tesseract as fallback
        if best_score < 50:
            if not TESSERACT_PATH:
                if not best_text.strip():
                    return {
                        'success': False,
                        'error': 'OCR API failed and Tesseract OCR not installed. Please install from: https://github.com/UB-Mannheim/tesseract/wiki'
                    }

            else:
                # Tesseract fallback logic
                processed_versions, error = preprocess_image_advanced(image_bytes)
                
                if not error:
                    psm_modes = [6, 4, 11, 3]
                    
                    for version_name, processed_img in processed_versions:
                        for psm in psm_modes:
                            text, score = extract_text_with_config(processed_img, psm)
                            
                            if score > best_score:
                                best_score = score
                                best_text = text
                                best_strategy = f"Tesseract: {version_name}, PSM {psm}"
                    
                    # One more Tesseract fallback with aggressive preprocessing
                    if best_score < 20:
                        nparr = np.frombuffer(image_bytes, np.uint8)
                        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                        if img is not None:
                            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
                            gray = cv2.equalizeHist(gray)
                            _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
                            
                            for psm in [6, 4]:
                                text, score = extract_text_with_config(binary, psm)
                                if score > best_score:
                                    best_score = score
                                    best_text = text
                                    best_strategy = f"Tesseract: Extreme contrast, PSM {psm}"
        
        if not best_text.strip() or best_score < 10:
            return {
                'success': False,
                'error': 'No readable text found. Please ensure the image shows an ingredient label clearly.'
            }
        
        # Clean and parse the extracted text
        cleaned_text = clean_extracted_text(best_text)
        ingredients = parse_ingredients_list(cleaned_text)
        
        # Fallback: if no structured ingredients, extract words
        if not ingredients:
            words = re.findall(r'\b[a-z]{3,}\b', cleaned_text.lower())
            skip_words = {'the', 'and', 'for', 'with', 'from', 'this', 'that', 'are', 'was', 'were',
                         'nutrition', 'facts', 'serving', 'size', 'calories', 'daily', 'value',
                         'distributed', 'by', 'keep', 'refrigerated', 'store', 'best', 'before',
                         'product', 'of', 'inc', 'llc', 'copyright', 'www', 'http'}
            ingredients = [w for w in words if w not in skip_words and len(w) > 3][:15]
        
        if not ingredients:
            return {
                'success': False,
                'error': 'Could not identify ingredients. Please ensure the image shows an ingredient list.'
            }
        
        # ── Real OCR confidence based on text quality ──────────────────────
        # We measure the actual readability of what was extracted, not just
        # the internal scoring variable (which was designed to pick the best
        # strategy, not reflect extraction quality).
        confidence = _estimate_ocr_confidence(best_text, ingredients)
        
        return {
            'success': True,
            'raw_text': best_text[:1000],
            'cleaned_text': ', '.join(ingredients),
            'ingredients_list': ingredients,
            'strategy_used': best_strategy,
            'ocr_confidence': round(confidence, 2)
        }
        
    except Exception as e:
        return {
            'success': False,
            'error': f"OCR processing failed: {str(e)}"
        }


def clean_extracted_text(text):
    """
    Clean OCR extracted text
    """
    if not text:
        return ""
    
    # Convert to lowercase
    text = text.lower()
    
    # Remove common OCR garbage
    garbage_patterns = [
        r'[^a-z\s,.;:()%/-]',
        r'\b[a-z]{1,2}\s+[a-z]{1,2}\s+[a-z]{1,2}\b',
        r'\b(?:www|http|https|ftp|com|net|org)\S*',
        r'\b[0-9]{5,}\b',
        r'\.{3,}',
    ]
    
    for pattern in garbage_patterns:
        text = re.sub(pattern, ' ', text)
    
    # Fix common OCR errors
    fixes = {
        '0': 'o', '1': 'i', '5': 's', '8': 'b', '@': 'a', '$': 's',
        'wbeat': 'wheat', 'wheaf': 'wheat', 'wheet': 'wheat',
        'miik': 'milk', 'mllk': 'milk', 'milc': 'milk',
        'soya': 'soy', 'peant': 'peanut', 'peanutt': 'peanut',
        'seseme': 'sesame', 'glulen': 'gluten', 'buter': 'butter',
        'suger': 'sugar', 'flower': 'flour', 'yeest': 'yeast',
        'creem': 'cream', 'chesse': 'cheese', 'yogurt': 'yogurt',
        'cocnut': 'coconut', 'almod': 'almond', 'vegtable': 'vegetable',
        'protien': 'protein', 'choclate': 'chocolate', 'vanila': 'vanilla'
    }
    
    for wrong, correct in fixes.items():
        text = re.sub(rf'\b{re.escape(wrong)}\b', correct, text)
    
    # Normalize spaces
    text = re.sub(r'\s+', ' ', text)
    text = text.strip(' .,:;')
    
    return text


def parse_ingredients_list(text):
    """
    Parse individual ingredients from cleaned text
    """
    if not text:
        return []
    
    # Try to find ingredients section using lookahead boundaries for flattened text
    patterns = [
        r'ingredients?:?\s*(.*?)(?=\s+(?:contains(?::?\s+)(?!2%|2\s*%|less|or\s+less|percent|\d)\w+|allergy|allergen|nutrition|facts|serving|distributed|manufactured|warning|may\s+contain|packaged|produced|store|keep|refrigerated)\b|$)',
        r'contains?:?\s*(.*?)(?=\s+(?:nutrition|facts|serving|distributed|manufactured|warning|store|keep|refrigerated)\b|$)',
    ]
    
    ingredients_text = text
    for pattern in patterns:
        match = re.search(pattern, text, re.DOTALL)
        if match:
            ingredients_text = match.group(1)
            break
    
    # Remove parentheses content
    ingredients_text = re.sub(r'\([^)]*\)', '', ingredients_text)
    
    # Remove percentages
    ingredients_text = re.sub(r'\d+%', '', ingredients_text)
    
    # Split by commas or "and"
    if ',' in ingredients_text:
        parts = re.split(r',\s*', ingredients_text)
    else:
        parts = re.split(r'\s+and\s+', ingredients_text)
    
    # Clean each part
    ingredients = []
    skip_terms = {'contains', 'may', 'contain', 'and', 'or', 'with', 'less', 'than',
                  'nutrition', 'facts', 'serving', 'size', 'calories', 'distributed',
                  'keep', 'refrigerated', 'store', 'best', 'before', 'ingredients'}
    
    for part in parts:
        part = part.strip().strip(' .,:;()[]{}')
        
        if len(part) < 2:
            continue
        if part in skip_terms:
            continue
        if part.isdigit():
            continue
        
        # Must have at least one vowel (looks like a word)
        if re.search(r'[aeiou]', part) and len(part) < 50:
            ingredients.append(part)
    
    # Remove duplicates
    seen = set()
    unique = []
    for ing in ingredients:
        if ing not in seen:
            seen.add(ing)
            unique.append(ing)
    
    return unique[:25]


def extract_ingredients_from_path(image_path):
    """Extract ingredients from image file path."""
    try:
        with open(image_path, 'rb') as f:
            image_bytes = f.read()
        return extract_ingredients(image_bytes)
    except Exception as e:
        return {
            'success': False,
            'error': f"Failed to read image file: {str(e)}"
        }