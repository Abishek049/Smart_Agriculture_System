from flask import Flask, request, render_template
import joblib
import numpy as np
import serial
import time

app = Flask(__name__)

# Initialize Serial Connection
try:
    ser = serial.Serial("COM5", 9600, timeout=2)  # Change COM port
    time.sleep(2)  # Allow time for connection
except Exception as e:
    ser = None
    print(f"Serial Error: {e}")

@app.route("/", methods=["GET", "POST"])
def index():
    temperature = None
    humidity = None
    prediction = None
    error = None

    # Read from Serial
    if ser:
        ser.flush()  # Clear buffer
        try:
            if ser.in_waiting > 0:
                data = ser.readline().decode().strip()
                if "," in data:
                    temp, hum = data.split(",")
                    temperature = float(temp)
                    humidity = float(hum)
                else:
                    error = "Invalid sensor data format"
        except Exception as e:
            error = f"Failed to read sensor data: {e}"
    else:
        error = "Serial connection not established"

    if request.method == "POST":
        try:
            pH = float(request.form["pH"])
            rainfall = float(request.form["rainfall"])

            if temperature is None or humidity is None:
                raise ValueError("Failed to get sensor data.")

            model = joblib.load("crop_recommendation_model_dht.pkl")
            prediction = model.predict([[temperature, humidity]])[0]

        except Exception as e:
            error = str(e)

    return render_template(
        "index.html", temperature=temperature, humidity=humidity, prediction=prediction, error=error
    )

if __name__ == "__main__":
    app.run(debug=True)
