from flask import Flask, request
import os
import cv2
from inference_sdk import InferenceHTTPClient
import time
import sqlite3
import re
import RPi.GPIO as GPIO
import rfid
import threading
import requests
import hashlib
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.serialization import load_pem_private_key

# Flask app setup
app = Flask(__name__)
UPLOAD_FOLDER = '/home/pi/Desktop/Uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs('captured', exist_ok=True)

# GPIO setup
sensor_pin = 4
servo_pin = 18
rfid_tag = ""
db = "SAGS.db"
GPIO.setmode(GPIO.BCM)
GPIO.setup(servo_pin, GPIO.OUT)
GPIO.setup(sensor_pin, GPIO.IN)
pwm = GPIO.PWM(servo_pin, 50)
pwm.start(0)

# Global state variables
plateDetected = False
rfid_done = False
yolo_done = False

# Initialize RFID reader
rfidReader = rfid.RFIDReader()
connection = sqlite3.connect(db)
cursor = connection.cursor()

# Initialize inference clients
CLIENT = InferenceHTTPClient(
    api_url="https://infer.roboflow.com",
    api_key="5suwHZqrjic2OqYwcopb"
)

CLIENTPLATE = InferenceHTTPClient(
    api_url="https://detect.roboflow.com",
    api_key="5suwHZqrjic2OqYwcopb"
)

# PC server details
PC_TRIGGER_URL = "http://192.168.18.96:5000/trigger"

# Helper Functions
def set_angle(angle):
    duty = 2 + (angle/18)
    GPIO.output(servo_pin, True)
    pwm.ChangeDutyCycle(duty)
    time.sleep(0.5)
    GPIO.output(servo_pin, False)
    pwm.ChangeDutyCycle(0)

def extract_plate_number(text):
    result_text = text.get('result', '')
    results_text = result_text.replace(" ", "")
    print(results_text)
    plate_pattern = r'\b[A-Z]{1,3}[0-9]{3,4}\b|13-954'
    match = re.search(plate_pattern, result_text)
    return match.group(0) if match else None

def searchDB(plate):
    # Create a new connection for this thread
    connection = sqlite3.connect(db)
    cursor = connection.cursor()
    try:
        query = f"SELECT name, plate FROM vehicle WHERE plate = ?"
        print("Query: ", query)
        cursor.execute(query, (plate,))
        rows = cursor.fetchall()
        global rfid_tag
        if rows:
            name = rows[0][0]
            plate_number = rows[0][1]
            input_rfid_tag = rfid_tag
            verify_rfid(db, name, plate_number, input_rfid_tag)

            print("Welcome ", name)
            set_angle(90)
            while not GPIO.input(sensor_pin):
                time.sleep(0.5)
            set_angle(0)
            return name
        else:
            print("No matching plate found.")
            return None
    except sqlite3.Error as e:
        print(f"Database error: {e}")
        return None
    finally:
        connection.close()  # Ensure the connection is closed


def millis_time():
    return round(time.time() * 1000)

def ocr(filepath):
    result = CLIENT.ocr_image(inference_input=filepath)
    print("OCR Result: ", result)
    plate = extract_plate_number(result)
    print("Plate Number: ", plate)
    searchDB(plate)
    global plateDetected
    plateDetected = True

def detectPlateNumber(filepath):
    print("Detect Plate Number Function")
    filepath = '797614.jpg'
    result = CLIENTPLATE.infer(filepath, model_id="plate-detection-svkgg/1")
    print(result)
    image = cv2.imread(filepath)
    if image is None:
        print("Error: Unable to load the image.")
        return False

    confidence = 0
    if "predictions" in result:
        for prediction in result["predictions"]:
            x = int(prediction["x"])
            y = int(prediction["y"])
            width = int(prediction["width"])
            height = int(prediction["height"])
            confidence = prediction["confidence"]

            x1 = x - width // 2
            y1 = y - height // 2
            x2 = x + width // 2
            y2 = y + height // 2

            cv2.rectangle(image, (x1, y1), (x2, y2), (0, 255, 0), 2)
            cropped_image = image[y1:y2, x1:x2]
            cropped_path = f"cropped_img.jpg"
            cv2.imwrite(cropped_path, cropped_image)
    print("Confidence ", confidence)
    ocr(image)
    # if confidence > 0.85:
    #     ocr(image)
    cv2.imwrite("Labeled_Result.jpg", image)
    return True

def handle_rfid():
    global rfid_done
    global rfid_tag
    max_attempts = 5
    attempt = 0
    
    while attempt < max_attempts:
        rfid_result = rfidReader.read_response()
        if rfid_result:
            print(f"RFID found: {rfid_result}")
            rfid_tag = rfid_result
            rfid_done = True
            return
        print(f"RFID read failed, retrying... ({attempt + 1}/{max_attempts})")
        attempt += 1
        time.sleep(1)

    print("RFID not found.")
    rfid_done = False

# Function to calculate ID from name and plate number
def calculate_id(name, plate_number):
    # Extract only digits from the plate number
    numeric_part = int(''.join(re.findall(r'\d', plate_number)))
    
    # Get the last digit of the numeric part
    n = numeric_part % 10
    
    # Rotate the name
    rotated_name = name[-n:] + name[:-n]
    
    # Convert the rotated name to ASCII codes and merge them into a single number
    ascii_number = int(''.join(str(ord(c)) for c in rotated_name))
    
    # Divide the ASCII number by the numeric part of the plate number
    division_result = ascii_number / numeric_part
    
    # Hash the result of the division using SHA256
    id_hash = hashlib.sha256(str(division_result).encode()).hexdigest()
    
    return id_hash

# Function to decrypt RFID tag
def decrypt_rfid_tag(encrypted_rfid, private_key_pem):
    # Load the private key
    private_key = load_pem_private_key(private_key_pem.encode(), password=None)
    # Decrypt the encrypted RFID tag
    decrypted = private_key.decrypt(
        encrypted_rfid,
        padding.OAEP(
            mgf=padding.MGF1(algorithm=hashes.SHA256()),
            algorithm=hashes.SHA256(),
            label=None
        )
    )
    return decrypted.decode('utf-8')  # Convert bytes to string

def verify_rfid(database, name, plate_number, input_rfid_tag):
    connection = sqlite3.connect(database)  # Create a new connection
    cursor = connection.cursor()
    try:
        # Fetch the encrypted RFID tag from the vehicle table
        cursor.execute(
            "SELECT rfid FROM vehicle WHERE name = ? AND plate = ?",
            (name, plate_number)
        )
        result = cursor.fetchone()
        if result is None:
            print("No matching vehicle found.")
            return False
        
        encrypted_rfid = bytes.fromhex(result[0])  # Convert hex to bytes
        
        # Calculate the ID
        id_hash = calculate_id(name, plate_number)
        
        # Fetch the private key from the key table
        cursor.execute("SELECT private_key FROM key WHERE id = ?", (id_hash,))
        key_result = cursor.fetchone()
        if key_result is None:
            print("No matching private key found.")
            return False
        
        private_key_pem = key_result[0]
        print("Private key: ", private_key_pem)
        # Decrypt the RFID tag
        decrypted_rfid_tag = decrypt_rfid_tag(encrypted_rfid, private_key_pem)
        
        # Verify the RFID tag
        if decrypted_rfid_tag == input_rfid_tag:
            print("RFID tag matches.")
            return True
        else:
            print("RFID tag does not match.")
            return False
    except sqlite3.Error as e:
        print(f"Database error: {e}")
        return False
    except Exception as e:
        print(f"Error: {e}")
        return False
    finally:
        connection.close()  # Ensure connection is closed

    
# Flask Routes
@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return 'No file part', 400
    file = request.files['file']
    if file.filename == '':
        return 'No selected file', 400
    file_path = os.path.join(UPLOAD_FOLDER, file.filename)
    file.save(file_path)
    
    # Trigger processing after file upload
    process_thread = threading.Thread(target=process_detection, args=(file_path,))
    process_thread.start()
    
    return f"File {file.filename} uploaded successfully!", 200

def process_detection(file_path):
    handle_rfid()
    print("Detecting Plate Number..")
    if rfid_done:
        print("Filepath: ", file_path)
        detectPlateNumber(file_path)

def monitor_sensor():
    vehicle_detected = False
    
    while True:
        sensor_status = GPIO.input(sensor_pin)
        
        if not sensor_status and not vehicle_detected:
            print("Vehicle Detected")
            vehicle_detected = True
            try:
                response = requests.post(PC_TRIGGER_URL, json={"trigger": "object_detected"})
                print(f"Trigger sent to PC. Response: {response.text}")
                time.sleep(5)
            except Exception as e:
                print(f"Failed to send trigger to PC: {e}")
                
        elif sensor_status and vehicle_detected:
            print("Waiting for vehicle")
            vehicle_detected = False
            
        time.sleep(0.1)

def main():
    try:
        # Initialize RFID
        rfidLookup = rfid.ExpiringDict(default_expiry=5)
        rfidHandler = rfid.TagHandler(rfidLookup, rfidReader)
        rfidReader.on_tag_read(rfidHandler.handle_tag)
        rfidReader.start_inventory()

        # Start sensor monitoring in a separate thread
        sensor_thread = threading.Thread(target=monitor_sensor)
        sensor_thread.daemon = True
        sensor_thread.start()

        # Start Flask app
        app.run(host='0.0.0.0', port=5000)

    except KeyboardInterrupt:
        print("Program stopped by user")
    finally:
        pwm.stop()
        GPIO.cleanup()

if __name__ == "__main__":
    main()
