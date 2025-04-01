from flask import Flask, request, render_template, jsonify
import joblib
import serial
import serial.tools.list_ports
import threading
import time
import atexit
import signal
import sys

app = Flask(__name__)

# Global variables
ser = None
sensor_data = {"temperature": None, "humidity": None, "error": None, "connected": False}
serial_thread = None
thread_running = False
arduino_port = "COM5"

def find_arduino_port():
    """Automatically detect the Arduino port"""
    ports = list(serial.tools.list_ports.comports())
    for port in ports:
        if any(id in port.description.lower() for id in ["arduino", "ch340", "usb serial"]):
            return port.device
    return ports[0].device if ports else None

def cleanup_resources():
    """Close serial connection and stop thread"""
    global ser, thread_running
    thread_running = False
    if ser:
        ser.close()
    ser = None

def connect_to_arduino(port=None):
    """Attempt to connect to Arduino"""
    global ser, sensor_data, arduino_port
    if port is None:
        port = find_arduino_port() or arduino_port
    arduino_port = port

    if ser:
        ser.close()

    try:
        ser = serial.Serial(arduino_port, 9600, timeout=2)
        time.sleep(2)
        sensor_data["connected"] = True
        return True
    except serial.SerialException as e:
        sensor_data.update({"connected": False, "error": str(e)})
        return False

def read_serial_data():
    """Read data from Arduino in a separate thread"""
    global ser, thread_running, sensor_data
    thread_running = True
    while thread_running:
        if not sensor_data["connected"] or not ser:
            time.sleep(5)
            connect_to_arduino()
            continue
        try:
            if ser.in_waiting > 0:
                data = ser.readline().decode().strip()
                if "," in data:
                    temp, hum = map(float, data.split(","))
                    sensor_data.update({"temperature": temp, "humidity": hum})
        except Exception as e:
            sensor_data.update({"connected": False, "error": str(e)})
        time.sleep(0.1)

def start_serial_thread():
    """Start the serial reading thread if not running"""
    global serial_thread, thread_running
    if not thread_running:
        serial_thread = threading.Thread(target=read_serial_data, daemon=True)
        serial_thread.start()

@app.route("/")
def home():
    return render_template("main.html")

@app.route("/weather")
def weather():
    return render_template("weather.html")

@app.route("/index", methods=["GET", "POST"])
def index():
    start_serial_thread()
    prediction = None

    if request.method == "POST":
        if "connect_port" in request.form:
            connect_to_arduino(request.form.get("port"))
        elif "predict" in request.form and sensor_data["temperature"] is not None:
            try:
                model = joblib.load("large_crop_data_model.pkl")
                prediction = model.predict([[sensor_data["temperature"], sensor_data["humidity"]]])[0]
                print(f"----------------{prediction}-------------------------")
            except Exception as e:
                sensor_data["error"] = str(e)

    return render_template(
        "index.html",
        **sensor_data,
        prediction=prediction,
        available_ports=[p.device for p in serial.tools.list_ports.comports()]
    )

@app.route("/data", methods=["GET"])
def get_data():
    return jsonify(sensor_data)

if __name__ == "__main__":
    atexit.register(cleanup_resources)
    signal.signal(signal.SIGINT, lambda sig, frame: (cleanup_resources(), sys.exit(0)))
    signal.signal(signal.SIGTERM, lambda sig, frame: (cleanup_resources(), sys.exit(0)))

    connect_to_arduino()
    start_serial_thread()

    app.run(debug=True, use_reloader=False, threaded=True)
