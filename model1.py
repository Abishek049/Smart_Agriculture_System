import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestClassifier
import joblib
import json

# Load dataset
data = pd.read_csv("large_crop_data.csv")  # Ensure the dataset contains Temperature, Humidity, pH, Rainfall, and CropName columns.

# Feature selection
X = data[['Temperature', 'Humidity']]
y = data['Recommended_Crop']

# Train-test split
X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

# Train model
model = RandomForestClassifier(n_estimators=100, random_state=42)
model.fit(X_train, y_train)

# Save model
joblib.dump(model, 'large_crop_data_model.pkl')

print("Model trained and saved successfully!")
