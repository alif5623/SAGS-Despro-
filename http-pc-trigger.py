from flask import Flask, Response, render_template_string, request
import os
import cv2
import threading
import requests
import time
from datetime import datetime, timedelta

# Flask app setup
app = Flask(__name__)

# Camera handling class
class CameraHandler:
    def __init__(self):
        self.camera = None
        self.frame = None
        self.lock = threading.Lock()
        self.running = False
        
    def initialize(self):
        if self.camera is None:
            self.camera = cv2.VideoCapture(0)
            self.camera.set(cv2.CAP_PROP_FRAME_WIDTH, 1920)
            self.camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 1080)
            self.running = True
            # Start frame capture thread
            threading.Thread(target=self._capture_frames, daemon=True).start()
    
    def _capture_frames(self):
        while self.running:
            if self.camera is None:
                time.sleep(0.1)
                continue
                
            success, frame = self.camera.read()
            if success:
                with self.lock:
                    self.frame = frame
            time.sleep(0.01)  # Small delay to prevent excessive CPU usage
    
    def get_frame(self):
        with self.lock:
            if self.frame is None:
                return None
            return self.frame.copy()
    
    def get_jpeg_frame(self):
        frame = self.get_frame()
        if frame is not None:
            _, buffer = cv2.imencode('.jpg', frame)
            return buffer.tobytes()
        return None
    
    def release(self):
        self.running = False
        if self.camera is not None:
            self.camera.release()
            self.camera = None

# Initialize camera handler
camera_handler = CameraHandler()

# Upload URL (Raspberry Pi)
UPLOAD_URL = "http://10.15.20.11:5000/upload"  # Replace with actual Raspberry Pi IP
FRAME_PATH = "frame.jpg"  # Temporary storage for the captured frame

# Trigger control
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

def generate_frames():
    """Generate frames for video streaming"""
    while True:
        frame_data = camera_handler.get_jpeg_frame()
        if frame_data is not None:
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + frame_data + b'\r\n')
        else:
            time.sleep(0.1)

def safe_write_frame(frame_data):
    """Safely write frame data to file with proper cleanup"""
    temp_path = f"{FRAME_PATH}.temp"
    try:
        # Write to temporary file first
        with open(temp_path, 'wb') as f:
            f.write(frame_data)
        # Then rename it to the actual file (atomic operation)
        os.replace(temp_path, FRAME_PATH)
        return True
    except Exception as e:
        print(f"Error writing frame: {e}")
        if os.path.exists(temp_path):
            os.remove(temp_path)
        return False

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

@app.route('/video_feed')
def video_feed():
    return Response(generate_frames(), 
                   mimetype='multipart/x-mixed-replace; boundary=frame')

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

@app.route('/trigger', methods=['POST'])
def handle_trigger():
    data = request.json
    
    if data.get('trigger') == 'object_detected':
        # Check if we're allowed to process this trigger
        if not is_trigger_allowed():
            print(f"Trigger ignored - cooldown period ({TRIGGER_COOLDOWN}s) not elapsed")
            return "Trigger ignored (cooldown)", 429
        
        print("Trigger received from Raspberry Pi: Object detected!")
        
        # Get the current frame
        frame_data = camera_handler.get_jpeg_frame()
        if frame_data is not None:
            try:
                # Write frame to file
                if safe_write_frame(frame_data):
                    # Send frame in a separate thread
                    thread = threading.Thread(target=send_frame_to_raspberry)
                    thread.daemon = True
                    thread.start()
                    return "Trigger processed", 200
                else:
                    return "Error saving frame", 500
            except Exception as e:
                print(f"Error processing trigger: {e}")
                return "Error processing trigger", 500
        else:
            return "No frame available", 400
            
    return "Invalid trigger", 400

if __name__ == '__main__':
    try:
        # Initialize camera
        camera_handler.initialize()
        
        # Ensure the frame file doesn't exist at startup
        if os.path.exists(FRAME_PATH):
            os.remove(FRAME_PATH)
            
        app.run(host='0.0.0.0', port=5000, debug=True)
    finally:
        camera_handler.release()