import os
import cv2
from inference_sdk import InferenceHTTPClient
import time
import sqlite3
import re
import RPi.GPIO as GPIO
import time
import rfid
import keyboard
# import threading

sensor_pin = 4                                                                                                     
servo_pin = 18
GPIO.setmode(GPIO.BCM)
GPIO.setup(servo_pin, GPIO.OUT)
GPIO.setup(sensor_pin, GPIO.IN)		
pwm = GPIO.PWM(servo_pin, 50)
pwm.start(0)
plateDetected = False
rfid_done = False
yolo_done = False
rfidReader = rfid.RFIDReader()



CLIENT = InferenceHTTPClient(
    api_url="https://infer.roboflow.com",
    api_key="5suwHZqrjic2OqYwcopb"
)

# initialize the client
CLIENTPLATE = InferenceHTTPClient(
    api_url="https://detect.roboflow.com",
    api_key="5suwHZqrjic2OqYwcopb"
)





# Load the YOLO model
#model = YOLO('license_plate_detection(v5).pt')

# Create the "captured" folder if it doesn't exist
os.makedirs('captured', exist_ok=True)

def extract_plate_number(text):
    result_text = text.get('result', '')
    results_text = result_text.replace(" ", "")
    print(results_text)
    # Define a regex pattern to match a plate number with 1-3 letters followed by 3-4 digits
    plate_pattern = r'\b[A-Z]{1,3}[0-9]{3,4}\b|13-954'
    
    # Search for the pattern in the text
    match = re.search(plate_pattern, result_text)
    
    # Return the matched plate number if found, otherwise None
    return match.group(0) if match else None

def set_angle(angle):
	duty = 2+ (angle/18)
	GPIO.output(servo_pin, True)
	pwm.ChangeDutyCycle(duty)
	time.sleep(0.5)
	GPIO.output(servo_pin, False)
	pwm.ChangeDutyCycle(0)
    
def searchDB(plate):
    connection = sqlite3.connect('SAGS.db')
    cursor = connection.cursor()
    query = f"SELECT name FROM vehicle WHERE plate = '{plate}'"
    print("Query: ", query)
    cursor.execute(query)
    rows = cursor.fetchall()
    # Check if there is a result
    if rows:
        # Extract the RFID value from the first tuple in the result
        name = rows[0][0]
        print("Welcome ", name)
        set_angle(90)
        while not(GPIO.input(sensor_pin)):
            time.sleep(0.5)
        set_angle(0)
        connection.close()
        return name
    else:
        print("No matching plate found.")
        connection.close()
        return None
    
def millis_time():
    return round(time.time() * 1000)

# Function to process each frame
def process_frame(frame, frame_count):
    results = model.predict(frame, device='cpu')
    high_confidence = False  # Flag to track if we should save the frame

    for result in results:
        for box in result.boxes:
            x1, y1, x2, y2 = map(int, box.xyxy[0])
            confidence = box.conf[0]

            # Draw bounding box if detection is found
            cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
            cv2.putText(frame, f'{confidence*100:.2f}%', (x1, y1 - 10), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.9, (255, 0, 0), 2)

            # Check confidence level
            if confidence > 0.75:
                high_confidence = True
                break

    # Save frame if any box has high confidence
    if high_confidence:
        ts = millis_time()
        filename = f'captured/{ts}_{frame_count}.jpg'
        cv2.imwrite(f'{filename}', frame)
        ocr(filename)

    return frame

def ocr(filepath):
    result = CLIENT.ocr_image(inference_input=filepath)
    print("OCR Result: ", result)
    plate = extract_plate_number(result)
    print("Plate Number: ", plate)
    searchDB(plate)
    global plateDetected
    plateDetected = True
    #if(plateDetected == True):
        #set_angle(90)
        #time.sleep(1)
        #set_angle(0)
        #.sleep(1)
    
# Function to process video
def predict_and_plot_video(video_path):
    cap = cv2.VideoCapture(video_path)
    global plateDetected
    if not cap.isOpened():
        print("Error opening video file")
        return

    # Video writer to save the output
    out = cv2.VideoWriter('output_with_boxes.mp4', 
                          cv2.VideoWriter_fourcc(*'mp4v'), 
                          int(cap.get(cv2.CAP_PROP_FPS)), 
                          (int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), 
                           int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))))

    frame_count = 0

    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            break

        processed_frame = process_frame(frame, frame_count)
        out.write(processed_frame)  # Write frame to output video

        # Optional: display the frame
        cv2.imshow('License Plate Detection', processed_frame)
        cv2.waitKey(0)
        #if cv2.waitKey(1) & 0xFF == ord('q'):
         #   break
        frame_count += 1
        print(plateDetected)
        if plateDetected:
            break

    cap.release()
    out.release()
    cv2.destroyAllWindows()

def detectPlateNumber(filepath):
    result = CLIENTPLATE.infer(filepath, model_id="plate-detection-svkgg/1")
    # Load the original image
    image = cv2.imread(filepath)
    if image is None:
        print("Error: Unable to load the image.")
        return

    # Extract predictions and annotate the image
    if "predictions" in result:
        for prediction in result["predictions"]:
            # Extract bounding box details
            x = int(prediction["x"])
            y = int(prediction["y"])
            width = int(prediction["width"])
            height = int(prediction["height"])
            confidence = prediction["confidence"]

            # Calculate top-left and bottom-right corners
            x1 = x - width // 2
            y1 = y - height // 2
            x2 = x + width // 2
            y2 = y + height // 2

            # Draw bounding box
            cv2.rectangle(image, (x1, y1), (x2, y2), (0, 255, 0), 2)
            cropped_image = image[y1:y2, x1:x2]
            # Save the cropped region
            cropped_path = f"cropped_img.jpg"
            cv2.imwrite(cropped_path, cropped_image)
            print(f"Cropped image saved to: {cropped_path}")
            # Add label and confidence
            label = f"{prediction.get('class', 'Unknown')} {confidence:.2f}"
            cv2.putText(image, label, (x1, y1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)

    # Save the annotated image
    output_path = "Labeled_Result.jpg"
    if(confidence > 0.85):
        ocr(image)
    cv2.imwrite(output_path, image)
    print(f"Labeled image saved to: {output_path}")
    return True

def handle_rfid():
    global rfid_done
    max_attempts = 5
    attempt = 0
    rfid_result = None

    while attempt < max_attempts:
        rfid_result = rfidReader.read_response()
        if rfid_result:
            print(f"RFID found: {rfid_result}")
            rfid_done = True
            return
        else:
            print(f"RFID read failed, retrying... ({attempt + 1}/{max_attempts})")
        attempt += 1
        time.sleep(1)  # Add a small delay between retries

    print("RFID not found.")
    rfid_done = False


def handle_yolo():
    global yolo_done
    yolo_done = detectPlateNumber("Tes_RFID2.png")

def main():
    rfidLookup = rfid.ExpiringDict(default_expiry=5)
    rfidHandler = rfid.TagHandler(rfidLookup, rfidReader)
    print("Waiting for vehicle")

    GPIO.setwarnings(False)  # Suppress GPIO warnings
    vehicle_detected = False  # Flag to track vehicle detection status

    try:
        rfidReader.on_tag_read(rfidHandler.handle_tag)
        rfidReader.start_inventory()

        while True:
            # Read the sensor status
            sensor_status = GPIO.input(sensor_pin)

            if not sensor_status and not vehicle_detected:
                # Condition met: start detection tasks
                # Condition met: start detection tasks
                print("Vehicle Detected")
                vehicle_detected = True  # Update the flag

                # Handle RFID and set a flag
                handle_rfid()

                if not rfid_done:
                    print("Skipping YOLO detection due to RFID failure.")
                    continue  # Skip further processing if RFID is not found

                # Perform plate detection if RFID is found
                detectPlateNumber("Tes_RFID2.png")
                # handle_yolo()
                
                # while not yolo_done:
                #     time.sleep(0.1)
                # t1 = threading.Thread(target=detectPlateNumber, args=("Tes_RFID2.png",))
                # t2 = threading.Thread(target=rfidReader.read_response)

                # t1.start()
                # t2.start()

                # Do not wait for threads to finish immediately, so both can run concurrently
                # Removing the t1.join() and t2.join() will allow the RFID reader and detection to run in parallel
                # t1.join() 
                # t2.join()
                time.sleep(5)

            elif sensor_status and vehicle_detected:
                # Reset the flag if the sensor returns to its initial state
                print("Waiting for vehicle")
                vehicle_detected = False

            # Small delay to avoid excessive CPU usage
            time.sleep(0.1)

    except KeyboardInterrupt:
        print("Program stopped by user")
    finally:
        GPIO.cleanup()


    # infer on a local image
    # Perform inference
    """
    try:
        while True:
            if not(GPIO.input(sensor_pin)):
                predict_and_plot_video('images1.jpg')
                print("Object Detected")
            else:
                #set_angle(0)
                print("No object")
            time.sleep(0.1)
    except KeyboardInterrupt:
        connection.close()
    finally:
        pwm.stop()
        GPIO.cleanup()
    """
if __name__ == "__main__":
    main()
