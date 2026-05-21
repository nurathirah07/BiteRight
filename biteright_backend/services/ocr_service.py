import cv2
import pytesseract
import numpy as np
from PIL import Image
import io
import re
import os

# Configure Tesseract path (Windows only - adjust to your installation path)
pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

def preprocess_image_multiple(image_bytes):
    """Apply multiple preprocessing techniques and return the best one"""
    # Convert bytes to numpy array
    nparr = np.frombuffer(image_bytes, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    
    if img is None:
        return None, "Failed to decode image"
    
    # Resize image (make it larger for better OCR)
    height, width = img.shape[:2]
    scale_factor = max(2, 1500 / min(height, width))
    new_width = int(width * scale_factor)
    new_height = int(height * scale_factor)
    img = cv2.resize(img, (new_width, new_height), interpolation=cv2.INTER_CUBIC)
    
    processed_images = []
    
    # Strategy 1: Basic grayscale + threshold
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    _, thresh1 = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    processed_images.append(('Basic Threshold', thresh1))
    
    # Strategy 2: Adaptive threshold
    thresh2 = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 15, 8)
    processed_images.append(('Adaptive Threshold', thresh2))
    
    # Strategy 3: Denoise + sharpen
    denoised = cv2.medianBlur(gray, 3)
    kernel = np.array([[-1,-1,-1], [-1,9,-1], [-1,-1,-1]])
    sharpened = cv2.filter2D(denoised, -1, kernel)
    _, thresh3 = cv2.threshold(sharpened, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    processed_images.append(('Sharpened', thresh3))
    
    # Strategy 4: Morphological operations
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (2,2))
    morphed = cv2.morphologyEx(thresh1, cv2.MORPH_CLOSE, kernel)
    processed_images.append(('Morphological', morphed))
    
    return processed_images, None

def extract_with_multiple_strategies(image_bytes):
    """Try multiple OCR strategies and return the best result"""
    processed_images, error = preprocess_image_multiple(image_bytes)
    
    if error:
        return {'success': False, 'error': error}
    
    best_result = None
    best_confidence = 0
    
    # Try different page segmentation modes
    psm_modes = [6, 8, 11, 12]  # Different layout analysis modes
    
    for strategy_name, processed_img in processed_images:
        for psm in psm_modes:
            try:
                config = f'--oem 3 --psm {psm}'
                text = pytesseract.image_to_string(processed_img, config=config)
                
                # Calculate confidence based on text length and readability
                score = len(text.strip())
                
                # Bonus for finding "INGREDIENTS" keyword
                if 'INGREDIENTS' in text.upper() or 'INGREDIENT' in text.upper():
                    score += 500
                
                # Bonus for having commas (likely ingredient list)
                if ',' in text:
                    score += 200
                
                if score > best_confidence:
                    best_confidence = score
                    best_result = text
                    
            except Exception as e:
                continue
    
    if not best_result:
        return {
            'success': False,
            'error': "No text extracted from image"
        }
    
    return {
        'success': True,
        'raw_text': best_result,
        'strategy_used': 'Multiple strategies'
    }

def extract_ingredients(image_bytes):
    """Enhanced extraction with multiple strategies"""
    try:
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
        # Remove excessive whitespace and newlines
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
                # Normalize common ingredient names
                ingredient = ingredient.lower()
                
                # Fix common OCR errors
                fixes = {
                    'wheat': 'wheat',
                    'flour': 'flour',
                    'soy': 'soy',
                    'milk': 'milk',
                    'egg': 'egg',
                    'sugar': 'sugar',
                    'salt': 'salt',
                    'oil': 'oil',
                }
                
                for wrong, correct in fixes.items():
                    if wrong in ingredient:
                        ingredient = correct
                
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