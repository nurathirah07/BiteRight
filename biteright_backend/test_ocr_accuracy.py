# biteright_backend/test_ocr_accuracy.py
"""
Comprehensive OCR Accuracy Testing Script
Measures Character Error Rate (CER) and Word Error Rate (WER)
"""

import os
import sys
import cv2
import numpy as np
import pandas as pd
from difflib import SequenceMatcher
import requests
import json
from datetime import datetime

# Prevent encoding issues with Unicode checkmarks on Windows console
sys.stdout.reconfigure(encoding='utf-8')

class OCRAccuracyTester:
    def __init__(self, api_url="http://127.0.0.1:5000"):
        self.api_url = api_url
        self.results = []
    
    def calculate_cer(self, ground_truth, ocr_output):
        """
        Calculate Character Error Rate
        CER = (Substitutions + Insertions + Deletions) / Total Characters
        Lower is better (0 = perfect, 1 = completely wrong)
        """
        if not ground_truth or not ocr_output:
            return 1.0
        
        # Use SequenceMatcher for character-level diff
        matcher = SequenceMatcher(None, ground_truth.lower(), ocr_output.lower())
        ops = matcher.get_opcodes()
        
        substitutions = insertions = deletions = 0
        for tag, i1, i2, j1, j2 in ops:
            if tag == 'replace':
                substitutions += (i2 - i1)
            elif tag == 'insert':
                insertions += (j2 - j1)
            elif tag == 'delete':
                deletions += (i2 - i1)
        
        total_chars = len(ground_truth)
        cer = (substitutions + insertions + deletions) / total_chars if total_chars > 0 else 1.0
        return min(cer, 1.0)
    
    def calculate_wer(self, ground_truth, ocr_output):
        """
        Calculate Word Error Rate
        WER = (S + I + D) / Total Words
        Lower is better (0 = perfect)
        """
        gt_words = ground_truth.lower().split()
        ocr_words = ocr_output.lower().split()
        
        if not gt_words:
            return 1.0 if ocr_words else 0.0
        
        matcher = SequenceMatcher(None, gt_words, ocr_words)
        ops = matcher.get_opcodes()
        
        substitutions = insertions = deletions = 0
        for tag, i1, i2, j1, j2 in ops:
            if tag == 'replace':
                substitutions += (i2 - i1)
            elif tag == 'insert':
                insertions += (j2 - j1)
            elif tag == 'delete':
                deletions += (i2 - i1)
        
        wer = (substitutions + insertions + deletions) / len(gt_words)
        return min(wer, 1.0)
    
    def calculate_accuracy_score(self, cer):
        """Convert CER to accuracy percentage"""
        return max(0, (1 - cer) * 100)
    
    def test_single_image(self, image_path, ground_truth_text):
        """Test OCR on a single image"""
        
        with open(image_path, 'rb') as f:
            files = {'image': f}
            response = requests.post(f"{self.api_url}/extract-ingredients", files=files)
        
        if response.status_code != 200:
            return {
                'success': False,
                'error': response.text,
                'image': os.path.basename(image_path)
            }
        
        result = response.json()
        extracted_text = result.get('cleaned_text', '') or ' '.join(result.get('ingredients', []))
        raw_text = result.get('raw_text', '')
        confidence = result.get('ocr_confidence', 0)
        
        # Calculate metrics
        cer = self.calculate_cer(ground_truth_text, extracted_text)
        wer = self.calculate_wer(ground_truth_text, extracted_text)
        accuracy = self.calculate_accuracy_score(cer)
        
        return {
            'success': True,
            'image': os.path.basename(image_path),
            'ground_truth': ground_truth_text,
            'extracted': extracted_text,
            'raw_text': raw_text[:200],
            'ocr_confidence': confidence,
            'cer': cer,
            'wer': wer,
            'accuracy': accuracy
        }
    
    def run_tests(self, test_data):
        """
        Run OCR tests on multiple images
        test_data: list of dicts with 'image_path' and 'ground_truth'
        """
        
        print("="*70)
        print("OCR ACCURACY TEST SUITE")
        print(f"Test started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("="*70)
        
        for test in test_data:
            print(f"\n📷 Testing: {os.path.basename(test['image_path'])}")
            result = self.test_single_image(test['image_path'], test['ground_truth'])
            self.results.append(result)
            
            if result['success']:
                print(f"   ✓ OCR Success")
                print(f"   📊 CER: {result['cer']:.4f} ({result['accuracy']:.1f}% accuracy)")
                print(f"   📊 WER: {result['wer']:.4f}")
                print(f"   💯 Confidence: {result['ocr_confidence']:.2%}")
                print(f"   📝 Extracted: {result['extracted'][:100]}...")
            else:
                print(f"   ✗ Failed: {result.get('error', 'Unknown')}")
        
        return self.results
    
    def generate_report(self):
        """Generate comprehensive OCR accuracy report"""
        
        successful = [r for r in self.results if r['success']]
        
        if not successful:
            print("\nNo successful tests to report")
            return
        
        # Calculate averages
        avg_cer = sum(r['cer'] for r in successful) / len(successful)
        avg_wer = sum(r['wer'] for r in successful) / len(successful)
        avg_accuracy = sum(r['accuracy'] for r in successful) / len(successful)
        avg_confidence = sum(r['ocr_confidence'] for r in successful) / len(successful)
        
        # Find best and worst
        best = min(successful, key=lambda x: x['cer'])
        worst = max(successful, key=lambda x: x['cer'])
        
        print("\n" + "="*70)
        print("OCR ACCURACY REPORT")
        print("="*70)
        
        print(f"\n📊 OVERALL STATISTICS")
        print("-"*50)
        print(f"Total images tested: {len(self.results)}")
        print(f"Successful OCR: {len(successful)}")
        print(f"Failed OCR: {len(self.results) - len(successful)}")
        print(f"\nAverage Character Error Rate (CER): {avg_cer:.4f}")
        print(f"Average Word Error Rate (WER): {avg_wer:.4f}")
        print(f"Average Accuracy: {avg_accuracy:.1f}%")
        print(f"Average OCR Confidence: {avg_confidence:.2%}")
        
        print(f"\n🏆 BEST PERFORMING IMAGE")
        print("-"*50)
        print(f"Image: {best['image']}")
        print(f"CER: {best['cer']:.4f} ({best['accuracy']:.1f}% accuracy)")
        print(f"WER: {best['wer']:.4f}")
        print(f"Extracted: {best['extracted'][:100]}...")
        
        print(f"\n⚠️ WORST PERFORMING IMAGE")
        print("-"*50)
        print(f"Image: {worst['image']}")
        print(f"CER: {worst['cer']:.4f} ({worst['accuracy']:.1f}% accuracy)")
        print(f"WER: {worst['wer']:.4f}")
        print(f"Extracted: {worst['extracted'][:100]}...")
        
        # Performance by text length
        print(f"\n📈 PERFORMANCE BY TEXT LENGTH")
        print("-"*50)
        short_text = [r for r in successful if len(r['ground_truth']) < 50]
        medium_text = [r for r in successful if 50 <= len(r['ground_truth']) < 150]
        long_text = [r for r in successful if len(r['ground_truth']) >= 150]
        
        if short_text:
            print(f"Short text (<50 chars): {sum(r['accuracy'] for r in short_text)/len(short_text):.1f}% ({len(short_text)} samples)")
        if medium_text:
            print(f"Medium text (50-150 chars): {sum(r['accuracy'] for r in medium_text)/len(medium_text):.1f}% ({len(medium_text)} samples)")
        if long_text:
            print(f"Long text (>150 chars): {sum(r['accuracy'] for r in long_text)/len(long_text):.1f}% ({len(long_text)} samples)")
        
        # Save results
        os.makedirs('test_results', exist_ok=True)
        with open('test_results/ocr_accuracy_report.json', 'w') as f:
            json.dump({
                'summary': {
                    'avg_cer': avg_cer,
                    'avg_wer': avg_wer,
                    'avg_accuracy': avg_accuracy,
                    'avg_confidence': avg_confidence,
                    'total_tests': len(self.results),
                    'successful': len(successful)
                },
                'details': self.results
            }, f, indent=2, default=str)
        
        print(f"\n📁 Detailed results saved to: test_results/ocr_accuracy_report.json")
        
        return {
            'avg_cer': avg_cer,
            'avg_wer': avg_wer,
            'avg_accuracy': avg_accuracy
        }


# ============= CREATE GROUND TRUTH DATA =============

def create_ground_truth_for_images():
    """
    Create ground truth data for your test images
    You need to manually fill this based on actual ingredient labels
    """
    
    ground_truth_data = [
        {
            'image_filename': 'almond milk.jpg',
            'ground_truth': 'almondmilk, calcium carbonate, natural flavors, sea salt, potassium citrate, sunflower lecithin, gellan gum, vitamin a palmitate, vitamin dz, d-alpha-tocopheroi. . contains almonds'
        },
        {
            'image_filename': 'biscuits.jpg',
            'ground_truth': 'flour, vegetable oil, wholemeal wheat flour, sugar, partially inverted sugar syrup, raising agents, salt, dried skimmed milk'
        },
        {
            'image_filename': 'canned tuna.jpg',
            'ground_truth': 'chunk light skipjack tuna, water. contains fish  ingredients'
        },
        {
            'image_filename': 'cereal.jpg',
            'ground_truth': 'rice, whole grain wheat, sugars, vitamins and minerals: dicalcium phosphate, ascorbic acid, dl-alpha-tocopheryl acetate, niacinamide, magnesium oxide, iron, zinc oxide, biotin, d-calcium pantothenate, vitamin a palmitate, manganese sulfate monohydrate, copper oxide, pyridoxine hydrochloride, riboflavin, thiamine hydrochloride, potassium iodide, folic acid, cholecalciferol  contains: wheat, barley, soy, oats'
        },
        {
            'image_filename': 'egg noodles.jpeg',
            'ground_truth': 'durum wheat semolina, durum wheat flour, eggs, niacin, iron, thiamin mononitrate, riboflavin, folic acid. contains: wheat, egg'
        },
        {
            'image_filename': 'granola bar.jpg',
            'ground_truth': 'granola, corn syrup, semisweet chocolate chips, crisp rice, salt, calcium carbonate). fructose, sugar, canola and/or soybean oil, glycerin, liquid invert sugar, dried unsweetened coconut, soy lecithin - an emusifier, honey, wheat flakes, ascorbic acid, citric acid, rosemary extract, natural flavor'
        },
        {
            'image_filename': 'ice cream.png',
            'ground_truth': 'cherry and coconut flavoured ice cream milk, cream, liquid sugar, water, milk solids non fat, glucose syrup, emulsifier, vegetable gums, colour, flavour, old gold dark chocolate, cherry sauce, sugar, food acid, toasted coconut'
        },
        {
            'image_filename': 'instant noodles.jpg',
            'ground_truth': 'noodles: wheat flour, palm oil, salt, potassium carbonate, sodium tripolyphosphate scuium carbonate, sodium hexametaphosphate, algin acid, sodium phosphate, guar gum, tocopherols, ascorbyl palmitate . soup base : salt, soy sauce powder, sugar, monosodium glutamate, caramel color, autolyzed yeast ted green onion, white pepper powder, maltodeytrin, ginger powder, citric acid, disodium guanylate, disodium inosinate, rice oil, natural and artificial sesame flavor'
        },
        {
            'image_filename': 'milk_chocolate.jpg',
            'ground_truth': 'sugar, cocoa butter, whole milk powder, cocoa mass, sweet whey powder, milk solids % minimum'
        },
        {
            'image_filename': 'olive oil.jpeg',
            'ground_truth': 'water, vegetable oil blend, less than % of salt, vegetable monoglycerides, natural and artificial flavors, potassium sorbate, lactic acid and calcium disodium edta, vitamin a palmitate, beta carotene, vitamin d'
        },
        {
            'image_filename': 'peanut_butter.png',
            'ground_truth': 'roasted peanuts, sugar, rapeseed oil, cottonseed oil, salt'
        },
        {
            'image_filename': 'potato chips.jpg',
            'ground_truth': 'potatoes, canola oil, sunflower oil, sugar, salt, food acids, buttermilk powder, sour cream powder, yeast extract, mineral salt, onion powder, garlic powder, spices, corn starch, tomato powder, natural colours, natural flavours, antioxidants (tocopherols, ascorbic acid, rosemary extract'
        },
        {
            'image_filename': 'rice.png',
            'ground_truth': 'rice, wild rice, salt, autolyzed yeast extract, dried parsley, onions, garlic, spices, turmeric, natural flavor'
        },
        {
            'image_filename': 'salt.jpg',
            'ground_truth': 'salt, calcium silicate, sodium thiosulphate, potassium iodide, sodium bicarbonate'
        },
        {
            'image_filename': 'seitan.jpg',
            'ground_truth': 'seitan %, apple vinegar sunflower oil, garlic powder, milk, nuts, celery, mustard, sesame and lupin'
        },
        {
            'image_filename': 'soy_sauce.jpg',
            'ground_truth': 'ments: sugar %, water %, brown sugar %, glucose syrup %, soy sauce  % alleroy a'
        },
        {
            'image_filename': 'whey protein.jpg',
            'ground_truth': 'whey protein blend, natural vanilla flavours, xanthan gum, sunflower lecithin, sodium chlaride, stevia, vegetarian enzyme blend'
        },
        {
            'image_filename': 'white sugar.jpg',
            'ground_truth': 'cane sugar'
        },
        {
            'image_filename': 'whole wheat bread.jpg',
            'ground_truth': 'whole wheat flour, water, unbleached wheat flour, honey, yeast, sea salt, sunflower seeds, sesame seeds, flaxseed, millet, oats, cracked whole wheat, oat bran'
        },
        {
            'image_filename': 'yogurt.jpg',
            'ground_truth': 'cultured pasteurized grade a milk, cream, pectin. contains milk'
        }
    ]
    
    return ground_truth_data


# ============= RUN THE TESTS =============

def run_ocr_accuracy_tests():
    """Main function to run OCR accuracy tests"""
    
    # Check if Flask is running
    try:
        requests.get("http://127.0.0.1:5000/", timeout=5)
        print("✓ Flask API is running")
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"✗ Flask API is not running! Error: {e}")
        print("Please start Flask first: python app.py")
        return
    
    # Create ground truth data
    ground_truth_data = create_ground_truth_for_images()
    
    # Prepare test data
    test_data = []
    images_dir = "test_data/images"
    
    for gt in ground_truth_data:
        image_path = os.path.join(images_dir, gt['image_filename'])
        if os.path.exists(image_path):
            test_data.append({
                'image_path': image_path,
                'ground_truth': gt['ground_truth']
            })
        else:
            print(f"⚠ Image not found: {image_path}")
    
    if not test_data:
        print("No test images found!")
        return
    
    # Run tests
    tester = OCRAccuracyTester()
    tester.run_tests(test_data)
    results = tester.generate_report()
    
    # Provide interpretation
    print("\n" + "="*70)
    print("INTERPRETATION GUIDE")
    print("="*70)
    
    avg_cer = results['avg_cer']
    if avg_cer < 0.1:
        print("✅ EXCELLENT: CER < 10% - OCR is very accurate")
    elif avg_cer < 0.2:
        print("👍 GOOD: CER 10-20% - OCR is acceptable with minor errors")
    elif avg_cer < 0.3:
        print("⚠️ FAIR: CER 20-30% - OCR needs improvement")
    else:
        print("❌ POOR: CER > 30% - OCR requires significant improvement")
    
    return results


if __name__ == "__main__":
    run_ocr_accuracy_tests()