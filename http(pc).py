from flask import Flask, Response, render_template_string, request
import os
import cv2
import threading
import requests

# Flask app setup
app = Flask(__name__)

# Webcam setup (use 0 for default camera)
camera = cv2.VideoCapture(0)
camera.set(cv2.CAP_PROP_FRAME_WIDTH, 1920)  # Width
camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 1080)  # Height

# Upload URL (Raspberry Pi)
UPLOAD_URL = "http://10.15.20.11:5000/upload"  # Replace with actual Raspberry Pi IP
FRAME_PATH = "frame.jpg"  # Temporary storage for the captured frame


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
            /* Same styles as before */
        </style>
        <script>
            // JavaScript to remove the message after 7 seconds
            document.addEventListener("DOMContentLoaded", function() {
                const messageDiv = document.getElementById('message');
                if (messageDiv) {
                    setTimeout(() => {
                        messageDiv.style.display = 'none'; // Hide after 7 seconds
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
            <!-- Button to trigger manual gate open -->
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
        print("Trigger received from Raspberry Pi: Object detected!")
        if frame is not None:
            # Save the current frame to a file
            with open(FRAME_PATH, 'wb') as f:
                f.write(frame)
            # Send the frame to the Raspberry Pi
            with open(FRAME_PATH, 'rb') as f:
                files = {'file': f}
                try:
                    response = requests.post(UPLOAD_URL, files=files)
                    print(response.text)
                except Exception as e:
                    print(f"Failed to send frame: {e}")
        return "Trigger received", 200
    return "Invalid trigger", 400


# Start Flask app
if __name__ == '__main__':
    frame = None
    app.run(host='0.0.0.0', port=5000, debug=True)
