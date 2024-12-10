from flask import Flask, Response, render_template_string, request
import os
import cv2
import threading
import requests
import time
from datetime import datetime, timedelta

# Flask app setup
app = Flask(__name__)

# Webcam setup (use 0 for default camera)
camera = cv2.VideoCapture(0)
camera.set(cv2.CAP_PROP_FRAME_WIDTH, 1920)  # Width
camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 1080)  # Height

# Upload URL (Raspberry Pi)
UPLOAD_URL = "http://192.168.18.92:5000/upload"  # Replace with actual Raspberry Pi IP
FRAME_PATH = "frame.jpg"  # Temporary storage for the captured frame

# Trigger control variables
TRIGGER_COOLDOWN = 5  # Cooldown period in seconds
last_trigger_time = None
trigger_lock = threading.Lock()

def is_trigger_allowed():
    """Check if enough time has passed since the last trigger"""
    global last_trigger_time
    with trigger_lock:
        current_time = datetime.now()
        if last_trigger_time is None or \
           (current_time - last_trigger_time) > timedelta(seconds=TRIGGER_COOLDOWN):
            last_trigger_time = current_time
            return True
        return False

# Function to generate video frames
def generate_frames():
    global frame
    while True:
        success, frame = camera.read()  # Capture frame from the camera
        if not success:
            break
        else:
            # Encode the frame in JPEG format
            _, buffer = cv2.imencode('.jpg', frame)
            frame = buffer.tobytes()
            # Yield the frame as part of an HTTP response
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')

def safe_write_frame(frame_data):
    """Safely write frame data to file with proper cleanup"""
    temp_path = f"{FRAME_PATH}.temp"
    try:
        # Write to temporary file first
        with open(temp_path, 'wb') as f:
            f.write(frame_data)
        # Then rename it to the actual file (atomic operation)
        os.replace(temp_path, FRAME_PATH)
    except Exception as e:
        print(f"Error writing frame: {e}")
        if os.path.exists(temp_path):
            os.remove(temp_path)
        raise
    
def send_frame_to_raspberry():
    """Send the captured frame to Raspberry Pi"""
    try:
        with open(FRAME_PATH, 'rb') as f:
            files = {'file': f}
            response = requests.post(UPLOAD_URL, files=files, timeout=5)
            print(f"Frame sent successfully: {response.text}")
            return True
    except Exception as e:
        print(f"Failed to send frame: {e}")
        return False
    
# Route for the video feed
@app.route('/video_feed')
def video_feed():
    return Response(generate_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')

# Main route to display the video and handle manual control
@app.route('/', methods=['GET', 'POST'])
def index():
    message = None
    if request.method == 'POST':
        message = "Manual Open Gate triggered!"
        print(message)
    return render_template_string('''
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Live Video Stream</title>
        <style>
            body {
                font-family: Arial, sans-serif;
                margin: 0;
                padding: 20px;
                text-align: center;
            }
            header {
                background-color: #333;
                color: white;
                padding: 1em;
                margin-bottom: 20px;
            }
            img {
                max-width: 100%;
                height: auto;
                margin: 20px 0;
            }
            button {
                padding: 10px 20px;
                font-size: 16px;
                cursor: pointer;
                background-color: #4CAF50;
                color: white;
                border: none;
                border-radius: 4px;
            }
            button:hover {
                background-color: #45a049;
            }
            #message {
                margin: 20px;
                padding: 10px;
                background-color: #4CAF50;
                color: white;
                border-radius: 4px;
            }
            footer {
                margin-top: 50px;
                padding: 20px;
                background-color: #f1f1f1;
            }
        </style>
        <script>
            document.addEventListener("DOMContentLoaded", function() {
                const messageDiv = document.getElementById('message');
                if (messageDiv) {
                    setTimeout(() => {
                        messageDiv.style.display = 'none';
                    }, 7000);
                }
            });
        </script>
    </head>
    <body>
        <header>
            <h1>SAGS Gate Control</h1>
        </header>
        <main>
            <h1>Live Video Stream</h1>
            <img src="/video_feed" alt="Video Stream">
            <form method="post">
                <button type="submit">Manual Open Gate</button>
            </form>
            {% if message %}
            <div id="message">{{ message }}</div>
            {% endif %}
        </main>
        <footer>
            &copy; 2024 SAGS Gate Control System. All rights reserved.
        </footer>
    </body>
    </html>
    ''', message=message)

# Route to handle trigger from Raspberry Pi
@app.route('/trigger', methods=['POST'])
def handle_trigger():
    global frame
    data = request.json
    
    if data.get('trigger') == 'object_detected':
        
        # Check if we're allowed to process this trigger
        if not is_trigger_allowed():
            print(f"Trigger ignored - cooldown period ({TRIGGER_COOLDOWN}s) not elapsed")
            return "Trigger ignored (cooldown)", 429
        
        print("Trigger received from Raspberry Pi: Object detected!")
        
        if frame is not None:
            try:
                # Write frame to file
                safe_write_frame(frame)
                
                # Send frame in a separate thread to avoid blocking
                thread = threading.Thread(target=send_frame_to_raspberry)
                thread.daemon = True
                thread.start()
                
                return "Trigger processed", 200
            except Exception as e:
                print(f"Error processing trigger: {e}")
                return "Error processing trigger", 500
        else:
            return "No frame available", 400
            
    return "Invalid trigger", 400

# Start Flask app
if __name__ == '__main__':
    frame = None
    # Ensure the frame file doesn't exist at startup
    if os.path.exists(FRAME_PATH):
        os.remove(FRAME_PATH)
    app.run(host='0.0.0.0', port=5000, debug=True)
