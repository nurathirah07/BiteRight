# check_data_balance.py
"""
Check the distribution of your training data
"""

import pandas as pd
import os

print("="*60)
print("DATA BALANCE CHECK")
print("="*60)

if os.path.exists('training_data_balanced.csv'):
    df = pd.read_csv('training_data_balanced.csv')
    print(f"\nLoaded training_data_balanced.csv")
elif os.path.exists('training_data.csv'):
    df = pd.read_csv('training_data.csv')
    print(f"\nLoaded training_data.csv")
else:
    print("No training data found!")
    exit()

print(f"\nData Info:")
print(f"   Total samples: {len(df)}")
print(f"   Columns: {list(df.columns)}")

print(f"\nClass Distribution:")
positive = df['has_allergens'].sum()
negative = len(df) - positive
print(f"   Positive (has allergens): {positive}")
print(f"   Negative (no allergens): {negative}")

if negative == 0:
    print("\nWARNING: No negative samples found!")
    print("   The model cannot train with only one class.")
    print("\nSolutions:")
    print("   1. Add synthetic negative samples")
    print("   2. Use sample data that includes both classes")
    print("   3. Get more diverse data from Firebase")