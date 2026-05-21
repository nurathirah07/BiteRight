"""
Fix missing packages for the AI pipeline
"""

import subprocess
import sys
import os

def install_package(package):
    """Install a package using pip"""
    print(f"Installing {package}...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", package])
    print(f"{package} installed")

def main():
    print("="*60)
    print("FIXING MISSING PACKAGES")
    print("="*60)
    
    # Check if in virtual environment
    in_venv = hasattr(sys, 'real_prefix') or (hasattr(sys, 'base_prefix') and sys.base_prefix != sys.prefix)
    print(f"\nVirtual environment: {'Active' if in_venv else 'Not active'}")
    print(f"Python: {sys.executable}")
    
    # List of required packages
    required_packages = [
        'pandas',
        'numpy',
        'scikit-learn',
        'joblib',
        'nltk'
    ]
    
    installed = []
    missing = []
    
    # Check each package
    for package in required_packages:
        try:
            if package == 'scikit-learn':
                __import__('sklearn')
            else:
                __import__(package)
            installed.append(package)
            print(f"{package} already installed")
        except ImportError:
            missing.append(package)
            print(f"{package} missing")
    
    # Install missing packages
    if missing:
        print(f"\nInstalling missing packages: {missing}")
        for package in missing:
            try:
                if package == 'scikit-learn':
                    install_package('scikit-learn')
                else:
                    install_package(package)
            except Exception as e:
                print(f"Failed to install {package}: {e}")
                return False
        
        print("\nAll packages installed!")
    else:
        print("\nAll required packages are already installed!")
    
    # Final verification
    print("\nFinal verification:")
    try:
        import pandas as pd
        import numpy as np
        import sklearn
        import joblib
        import nltk
        print("All imports successful!")
        print(f"   Pandas: {pd.__version__}")
        print(f"   NumPy: {np.__version__}")
        print(f"   Scikit-learn: {sklearn.__version__}")
        print(f"   Joblib: {joblib.__version__}")
        return True
    except Exception as e:
        print(f"Import error: {e}")
        return False

if __name__ == "__main__":
    success = main()
    if success:
        print("\n" + "="*60)
        print("READY TO RUN THE PIPELINE!")
        print("="*60)
        print("\nRun: python run_ai_pipeline.py")
    else:
        print(f"\n" + "="*60)
        print("PACKAGE INSTALLATION FAILED")
        print("="*60)