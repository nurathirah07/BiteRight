"""
Complete AI Pipeline: Data Extraction -> Training -> Integration
SIMPLE VERSION - Guaranteed to work
"""

import subprocess
import os
import time
import sys

def run_step(step_name, script_name):
    """Run a Python script and time it"""
    print(f"\n{'='*60}")
    print(step_name)
    print(f"{'='*60}")
    
    if not os.path.exists(script_name):
        print(f"Script not found: {script_name}")
        return False
    
    print(f"Running: python {script_name}")
    start = time.time()
    
    try:
        # Run the script and show output in real-time
        result = subprocess.run([sys.executable, script_name])
        elapsed = time.time() - start
        
        if result.returncode == 0:
            print(f"Completed in {elapsed:.1f} seconds")
            return True
        else:
            print(f"Failed with return code {result.returncode}")
            
    except Exception as e:
        print(f"Error: {e}")
        return False

def main():
    print("="*60)
    print("BITERIGHT - AI PIPELINE")
    print("="*60)
    
    # Step 1: Extract training data
    print("\nSTEP 1: EXTRACT TRAINING DATA")
    if not run_step("Extract Training Data", "create_training_data.py"):
        print("\nData extraction failed")
        return
    
    # Step 2: Train model
    print("\nSTEP 2: TRAIN MODEL")
    if not run_step("Train Model", "ai_classifier.py"):
        print("\nModel training failed")
        return
    
    # Success!
    print("\n" + "="*60)
    print("PIPELINE COMPLETE!")
    print("="*60)
    print("\nYour Random Forest model is trained and ready!")
    print("\nNext steps:")
    print("   1. Restart your Flask app to load the model")
    print("   2. Test with ingredients:")
    print("      python -c \"from ai_classifier import AllergenClassifier;")
    print("      clf = AllergenClassifier(); clf.load_model();")
    print("      print(clf.predict('milk chocolate'))\"")
    print("      print(clf.predict('salt'))\"")

if __name__ == "__main__":
    main()