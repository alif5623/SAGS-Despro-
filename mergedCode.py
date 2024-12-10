from flask import Flask, request
import os
import requests
import threading
import RPi.GPIO as GPIO
import time
import cv2
import sqlite3
import re
from inference_sdk import InferenceHTTPClient
import rfid

# Flask app setup
app = Flask(__name__)
UPLOAD_FOLDER = '/home/pi/Desktop/Uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# GPIO setup
IR_SENSOR_PIN = 4
SERVO_PIN = 18
GPIO.setmode(GPIO.BCM)
GPIO.setup(IR_SENSOR_PIN, GPIO.IN)
GPIO.setup(SERVO_PIN, GPIO.OUT)
pwm = GPIO.PWM(SERVO_PIN, 50)
pwm.start(0)

# Roboflow API setup
CLIENT = InferenceHTTPClient(
    api_url="https://infer.roboflow.com",
    api_key="5suwHZqrjic2OqYwcopb"
)
CLIENTPLATE = InferenceHTTPClient(
    api_url="https://detect.roboflow.com",
    api_key="5suwHZqrjic2OqYwcopb"
)

# RFID setup
rfidReader = rfid.RFIDReader()

# PC server details
PC_TRIGGER_URL = "http://10.15.48.46:5000/trigger"

# Helper functions
def set_angle(angle):
    duty = 2 + (angle / 18)
    GPIO.output(SERVO_PIN, True)
    pwm.ChangeDutyCycle(duty)
    time.sleep(0.5)
    GPIO.output(SERVO_PIN, False)
    pwm.ChangeDutyCycle(0)

def extract_plate_number(text):
    result_text = text.get('result', '')
    plate_pattern = r'\b[A-Z]{1,3}[0-9]{3,4}\b|13-954'
    match = re.search(plate_pattern, result_text)
    return match.group(0) if match else None

def search_db(plate):
    connection = sqlite3.connect('SAGS.db')
    cursor = connection.cursor()
    query = f"SELECT name FROM vehicle WHERE plate = '{plate}'"
    cursor.execute(query)
    rows = cursor.fetchall()
    connection.close()
    if rows:
        name = rows[0][0]
        print("Welcome", name)
        set_angle(90)
        while not GPIO.input(IR_SENSOR_PIN):
            time.sleep(0.5)
        set_angle(0)
        return name
    else:
        print("No matching plate found.")
        return None

def detect_plate_number(filepath):
    result = CLIENTPLATE.infer(filepath, model_id="plate-detection-svkgg/1")
    image = cv2.imread(filepath)
    if "predictions" in result:
        for prediction in result["predictions"]:
            x, y, width, height = map(int, (prediction["x"], prediction["y"], prediction["width"], prediction["height"]))
            x1, y1, x2, y2 = x - width // 2, y - height // 2, x + width // 2, y + height // 2
            cropped_image = image[y1:y2, x1:x2]
            cropped_path = "cropped_img.jpg"
            cv2.imwrite(cropped_path, cropped_image)
            result = CLIENT.ocr_image(inference_input=cropped_path)
            plate = extract_plate_number(result)
            print("Detected Plate:", plate)
            if plate:
                search_db(plate)
                return True
    return False

def monitor_sensor():
    while True:
        if not GPIO.input(IR_SENSOR_PIN):  # Object detected
            print("Object detected! Sending trigger to PC...")
            try:
                response = requests.post(PC_TRIGGER_URL, json={"trigger": "object_detected"})
                print(f"Trigger sent. Response: {response.text}")
            except Exception as e:
                print(f"Failed to send trigger: {e}")
            time.sleep(2)

# Flask routes
@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return 'No file part', 400
    file = request.files['file']
    if file.filename == '':
        return 'No selected file', 400
    file_path = os.path.join(UPLOAD_FOLDER, file.filename)
    file.save(file_path)
    print(f"File {file.filename} uploaded successfully.")
    detect_plate_number(file_path)
    return f"File {file.filename} processed successfully!", 200

# Main function
if __name__ == '__main__':
    sensor_thread = threading.Thread(target=monitor_sensor)
    sensor_thread.daemon = True
    sensor_thread.start()

    try:
        app.run(host='0.0.0.0', port=5000)
    except KeyboardInterrupt:
        print("Program stopped by user.")
    finally:
        GPIO.cleanup()
        pwm.stop()
