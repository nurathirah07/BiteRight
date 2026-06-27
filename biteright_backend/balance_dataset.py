import pandas as pd

# Load your augmented data
df = pd.read_csv('data/training_data_augmented.csv')

# Find the smaller class
min_class_size = min((df['has_allergens'] == 1).sum(), (df['has_allergens'] == 0).sum())

# Sample both classes equally
df_balanced = pd.concat([
    df[df['has_allergens'] == 1].sample(n=min_class_size, random_state=42),
    df[df['has_allergens'] == 0].sample(n=min_class_size, random_state=42)
]).sample(frac=1, random_state=42)  # Shuffle

# Save
df_balanced.to_csv('data/training_data_balanced.csv', index=False)
print(f"Balanced dataset saved: {len(df_balanced)} rows")