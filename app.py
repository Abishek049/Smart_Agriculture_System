from flask import Flask, request, render_template, jsonify
import joblib
import numpy as np
import serial
import serial.tools.list_ports
import threading
import time
import os
import sys
import subprocess
import atexit
import signal

app = Flask(__name__)

# Initialize global variables
ser = None
temperature = None
humidity = None
error = None
connected = False
arduino_port = "COM5"  # Default port
connection_attempts = 0  # Track connection attempts
serial_thread = None  # Store thread reference
thread_running = False  # Flag to control thread execution

def force_release_port(port_name):
    """Attempt to force-release a COM port (Windows only)"""
    if sys.platform != 'win32':
        return False
    
    try:
        # Try to run an external command to reset the port
        print(f"Attempting to force-release {port_name}...")
        # For Windows, using mode command to reset the port
        subprocess.run(f"mode {port_name} BAUD=9600 PARITY=n DATA=8 STOP=1", 
                      shell=True, 
                      stdout=subprocess.PIPE, 
                      stderr=subprocess.PIPE)
        
        # More aggressive approach - try to use device manager to disable and re-enable the port
        # Warning: This requires admin privileges
        if "PermissionError" in str(error):
            try:
                print("Attempting aggressive port reset (requires admin privileges)...")
                # This approach is more reliable but requires running as admin
                # The commands below are examples and may need adjustment
                devcon_path = os.environ.get("DEVCON_PATH")
                if devcon_path and os.path.exists(devcon_path):
                    # Find the device ID for the COM port
                    find_cmd = f'"{devcon_path}" find =ports'
                    result = subprocess.run(find_cmd, shell=True, capture_output=True, text=True)
                    lines = result.stdout.splitlines()
                    
                    for line in lines:
                        if f"({port_name})" in line:
                            dev_id = line.split(":")[0].strip()
                            print(f"Found device ID for {port_name}: {dev_id}")
                            
                            # Disable and re-enable the device
                            subprocess.run(f'"{devcon_path}" disable "{dev_id}"', shell=True)
                            time.sleep(1)
                            subprocess.run(f'"{devcon_path}" enable "{dev_id}"', shell=True)
                            time.sleep(2)
                            print(f"Reset {port_name} via device manager")
                            break
            except Exception as e:
                print(f"Advanced port reset failed: {e}")
        
        return True
    except Exception as e:
        print(f"Failed to force-release port: {e}")
        return False

def find_arduino_port():
    """Find Arduino port automatically"""
    ports = list(serial.tools.list_ports.comports())
    print(f"Available ports: {[p.device for p in ports]}")
    
    for port in ports:
        # Look for common Arduino identifiers
        if any(id in port.description.lower() for id in ["arduino", "ch340", "usb serial"]):
            print(f"Found likely Arduino port: {port.device}")
            return port.device
    
    # If no Arduino identifiers, return the first available port
    if ports:
        print(f"No Arduino port found, using first available port: {ports[0].device}")
        return ports[0].device
    
    return None

def cleanup_resources():
    """Clean up all resources properly"""
    global ser, connected, thread_running
    
    print("Cleaning up resources...")
    thread_running = False  # Signal the thread to stop
    
    # Close serial connection
    if ser:
        try:
            ser.close()
            print("Serial connection closed")
        except Exception as e:
            print(f"Error closing serial connection: {e}")
        
        ser = None
    
    connected = False
    
    # Wait for thread to finish
    if serial_thread and serial_thread.is_alive():
        try:
            serial_thread.join(timeout=1)
            print("Serial thread joined")
        except Exception as e:
            print(f"Error joining thread: {e}")

def connect_to_arduino(port=None, retry=True):
    """Attempt to connect to Arduino with retry and force-release options"""
    global ser, error, connected, arduino_port, temperature, humidity, connection_attempts
    
    # Reset values
    error = None
    
    # Close any existing connection
    if ser:
        try:
            ser.close()
            print("Closed previous connection")
            time.sleep(1)  # Give time for port to release
        except:
            pass
        ser = None
    
    # Determine port to use
    if port is None:
        port = find_arduino_port()
        if port:
            arduino_port = port
        else:
            arduino_port = "COM5"  # Fallback
            error = "No available COM ports found. Please connect Arduino."
            connected = False
            return False
    else:
        arduino_port = port
    
    # Implement exponential backoff for retries
    if connection_attempts > 0:
        backoff_time = min(5, 1 * (2 ** (connection_attempts - 1)))  # Cap at 5 seconds
        print(f"Backing off for {backoff_time} seconds before retry #{connection_attempts}")
        time.sleep(backoff_time)
    
    connection_attempts += 1
    
    # Try connecting to the port
    try:
        print(f"Attempting to connect to {arduino_port}...")
        ser = serial.Serial(arduino_port, 9600, timeout=2)
        time.sleep(2)  # Allow time for connection
        
        # Test read to verify connection
        for _ in range(5):  # Increased number of attempts
            if ser and ser.in_waiting > 0:
                data = ser.readline().decode().strip()
                print(f"Test read: {data}")
                if "," in data:
                    temp, hum = data.split(",")
                    try:
                        temperature = float(temp)
                        humidity = float(hum)
                        connected = True
                        connection_attempts = 0  # Reset counter on success
                        print(f"Successfully connected to Arduino on {arduino_port}")
                        return True
                    except ValueError:
                        pass
            time.sleep(0.5)
        
        # If we're here, no valid data was received
        if ser:
            ser.close()
        ser = None
        error = f"Connected to {arduino_port} but received no valid data. Check Arduino sketch."
        connected = False
        return False
        
    except serial.SerialException as e:
        ser = None
        connected = False
        
        if "PermissionError" in str(e) and retry:
            # Try to force-release the port and retry once
            print(f"Permission error on {arduino_port}, attempting to force-release...")
            if force_release_port(arduino_port):
                time.sleep(3)  # Increased delay to 3 seconds
                # Retry connection without allowing another retry
                return connect_to_arduino(arduino_port, retry=False)
        
        error = f"Failed to connect to {arduino_port}: {str(e)}"
        print(error)
        return False
        
    except Exception as e:
        ser = None
        connected = False
        error = f"Error connecting to {arduino_port}: {str(e)}"
        print(error)
        return False

# Function to continuously read from serial
def read_serial_data():
    global temperature, humidity, error, connected, ser, thread_running
    
    thread_running = True
    print("Serial reading thread started")
    
    while thread_running:
        # If not connected, try periodically
        if not connected or not ser:
            time.sleep(5)  # Wait before trying to reconnect
            if thread_running:  # Check if we should still be running
                connect_to_arduino(arduino_port)
            continue
        
        try:
            if ser and ser.in_waiting > 0:
                data = ser.readline().decode().strip()
                print(f"Received: {data}")
                
                if "," in data:
                    try:
                        temp, hum = data.split(",")
                        temperature = float(temp)
                        humidity = float(hum)
                    except ValueError as e:
                        print(f"Error parsing data: {e}")
                else:
                    print(f"Invalid data format: {data}")
        except Exception as e:
            print(f"Serial reading error: {e}")
            error = f"Lost connection to Arduino: {e}"
            connected = False
            try:
                if ser:
                    ser.close()
                ser = None
            except:
                pass
        
        time.sleep(0.1)  # Small delay
    
    print("Serial reading thread exiting")

# Start the serial reading thread
def start_serial_thread():
    global serial_thread, thread_running
    
    # If thread exists, check if it's still running
    if serial_thread and serial_thread.is_alive():
        # Thread is already running, no need to start a new one
        return
    
    # If we had a thread before but it's not alive anymore, or we haven't had one yet
    thread_running = True
    serial_thread = threading.Thread(target=read_serial_data, daemon=True)
    serial_thread.start()

# Register cleanup functions
atexit.register(cleanup_resources)

# Handle signals for more reliable cleanup
def signal_handler(sig, frame):
    print(f"Received signal {sig}, cleaning up...")
    cleanup_resources()
    sys.exit(0)

signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

@app.route("/", methods=["GET", "POST"])
def index():
    global temperature, humidity, error, connected, arduino_port
    prediction = None
    
    # Make sure serial thread is running
    start_serial_thread()
    
    # Handle POST requests
    if request.method == "POST":
        # Connect button pressed
        if "connect_port" in request.form:
            port = request.form.get("port")
            if port:
                connect_to_arduino(port)
        # Predict button pressed
        elif "predict" in request.form:
            try:
                if temperature is None or humidity is None:
                    raise ValueError("Failed to get sensor data. Make sure Arduino is connected.")
                
                # Load model and make prediction
                model = joblib.load("crop_recommendation_model_dht.pkl")
                prediction = model.predict([[temperature, humidity]])[0]
                print(f"Prediction made: {prediction}")
            except Exception as e:
                error = str(e)
                print(f"Prediction error: {error}")
    
    # Get available ports
    available_ports = [p.device for p in serial.tools.list_ports.comports()]
    
    return render_template(
        "index.html", 
        temperature=temperature, 
        humidity=humidity, 
        prediction=prediction, 
        error=error,
        connected=connected,
        arduino_port=arduino_port,
        available_ports=available_ports
    )

@app.route("/reset_connection", methods=["POST"])
def reset_connection():
    """API endpoint to reset connection"""
    global ser, connected, connection_attempts
    
    # Force close any existing connection
    if ser:
        try:
            ser.close()
        except:
            pass
        ser = None
    
    connected = False
    connection_attempts = 0  # Reset attempts counter
    
    # Try to force-release the port
    port = request.form.get("port", arduino_port)
    force_release_port(port)
    time.sleep(2)
    
    # Try to connect
    success = connect_to_arduino(port)
    return jsonify({
        "success": success,
        "connected": connected,
        "error": error
    })

@app.route("/data", methods=["GET"])
def get_data():
    """API endpoint to get current sensor data"""
    return jsonify({
        "temperature": temperature,
        "humidity": humidity,
        "connected": connected,
        "error": error
    })

if __name__ == "__main__":
    # Inform user of workarounds
    print("\n----- ARDUINO CONNECTION HELP -----")
    print("If you get 'Access denied' errors:")
    print("1. Close Arduino IDE or any other program using the port")
    print("2. Try running this script as Administrator")
    print("3. Physically disconnect and reconnect the Arduino")
    print("4. Try a different USB port on your computer")
    print("---------------------------------\n")
    
    # Try to connect on startup
    connect_to_arduino()
    
    # Start serial thread before running the app
    start_serial_thread()
    
    # Run the app
    print("\nStarting Flask server...")
    print("Use Ctrl+C to properly stop the server\n")
    
    try:
        # Using threaded=True helps with resource management
        app.run(debug=True, use_reloader=False, threaded=True)
    except KeyboardInterrupt:
        print("Keyboard interrupt received, shutting down...")
    finally:
        cleanup_resources()