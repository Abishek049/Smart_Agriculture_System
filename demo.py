import joblib
import numpy as np

# Load the trained model
model = joblib.load("crop_recommendation_model.pkl")

def predict(temperature, humidity, pH, rainfall):
    try:
        # Make prediction
        prediction = model.predict([[temperature, humidity, pH, rainfall]])
        return {"recommended_crop": prediction[0]}
    except Exception as e:
        return {"error": str(e)}

def main():
    # Get user input
    try:
        temperature = float(input("Enter Temperature (°C): "))
        humidity = float(input("Enter Humidity (%): "))
        pH = float(input("Enter Soil pH: "))
        rainfall = float(input("Enter Rainfall (mm): "))

        # Get prediction
        result = predict(temperature, humidity, pH, rainfall)
        print("\nResult:", result)

    except ValueError:
        print("Invalid input! Please enter numeric values.")

if __name__ == "__main__":
    main()
