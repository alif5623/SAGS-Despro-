from flask import Flask, request
import os
import requests
import threading
import RPi.GPIO as GPIO
import time

# Flask app setup
app = Flask(__name__)
UPLOAD_FOLDER = '/home/pi/Desktop/Uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# GPIO setup
IR_SENSOR_PIN = 4
GPIO.setmode(GPIO.BCM)
GPIO.setup(IR_SENSOR_PIN, GPIO.IN)

# PC server details
PC_TRIGGER_URL = "http://10.15.48.46:5000/trigger"  # Replace with PC's actual IP

# Flask route to handle image uploads
@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return 'No file part', 400
    file = request.files['file']
    if file.filename == '':
        return 'No selected file', 400
    file_path = os.path.join(UPLOAD_FOLDER, file.filename)
    file.save(file_path)
    return f"File {file.filename} uploaded successfully!", 200

# Function to monitor IR sensor and send trigger to PC
def monitor_sensor():
    while True:
        if not GPIO.input(IR_SENSOR_PIN):  # Object detected
            print("Object detected! Sending trigger to PC...")
            try:
                response = requests.post(PC_TRIGGER_URL, json={"trigger": "object_detected"})
                print(f"Trigger sent. Response: {response.text}")
            except Exception as e:
                print(f"Failed to send trigger: {e}")
            time.sleep(2)  # Delay to prevent spamming

# Start Flask app and sensor monitoring in parallel
if __name__ == '__main__':
    sensor_thread = threading.Thread(target=monitor_sensor)
    sensor_thread.daemon = True  # Ensure thread closes when the program exits
    sensor_thread.start()

    app.run(host='0.0.0.0', port=5000)
