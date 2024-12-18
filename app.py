from flask import Flask, Response, render_template_string, request
import cv2
import paramiko
import time

app = Flask(__name__)

# Initialize the webcam (use 0 for the default camera, or a video file path)
camera = cv2.VideoCapture(0)
camera.set(cv2.CAP_PROP_FRAME_WIDTH, 1920)  # Width
camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 1080)  # Height

# SFTP details for uploading the image to Raspberry Pi
raspberry_ip = "192.168.18.92"  # Replace with your Raspberry Pi's IP address
raspberry_user = "pi"
raspberry_password = "raspberry"  # Use a secure method to handle this
raspberry_remote_path = "/home/pi/images"  # Folder on Raspberry Pi to save images

# Function to upload file to Raspberry Pi via SFTP
def upload_to_raspberry(filename):
    try:
        # Connect to the Raspberry Pi via SFTP
        transport = paramiko.Transport((raspberry_ip, 22))
        transport.connect(username=raspberry_user, password=raspberry_password)
        sftp = paramiko.SFTPClient.from_transport(transport)

        # Upload the file
        local_path = filename
        remote_path = f"{raspberry_remote_path}/{filename}"
        sftp.put(local_path, remote_path)

        sftp.close()
        transport.close()

        print(f"File {filename} uploaded successfully.")
    except Exception as e:
        print(f"Failed to upload {filename}: {e}")

# Function to generate video frames
def generate_frames():
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

# Main route to display the video, button, and message
@app.route('/', methods=['GET', 'POST'])
def index():
    message = None  # Default: no message
    if request.method == 'POST':
        # Display the message only when the button is clicked
        message = "Manual Open Gate triggered!"
        print(message)  # Log message to the console
        
        # Capture and save the frame
        ret, frame = camera.read()
        if ret:
            timestamp = int(time.time())  # Use timestamp for unique filenames
            filename = f"frame_{timestamp}.jpg"
            cv2.imwrite(filename, frame)
            print(f"Saved {filename}")
            
            # Upload the image to Raspberry Pi
            upload_to_raspberry(filename)
        else:
            print("Failed to capture frame.")

    return render_template_string('''
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Live Video Stream</title>
        <style>
            /* Global Styles */
            body {
                margin: 0;
                font-family: 'Roboto', Arial, sans-serif;
                display: flex;
                flex-direction: column;
                align-items: center;
                justify-content: center;
                min-height: 100vh;
                background: linear-gradient(to bottom, #627280, #627280);
                color: white;
            }
            header {
                width: 100%;
                display: flex;
                flex-direction: column;
                align-items: center;
                justify-content: center;
                text-align: center;
                background-color: #003d99; 
                padding: 20px;
                box-shadow: 0 4px 10px rgba(0, 0, 0, 0.3);
            }
            header h1 {
                margin: 0;
                font-size: 24px;
            }
            main {
                flex: 1;
                width: 100%;
                display: flex;
                flex-direction: column;
                align-items: center;
                justify-content: center;
                padding: 20px;
                text-align: center;
            }
            img {
                width: 80%;
                max-width: 800px;
                border-radius: 10px;
                box-shadow: 0px 4px 15px rgba(0, 0, 0, 0.5);
                margin: 20px 0;
            }
            button {
                margin-top: 20px;
                padding: 15px 30px;
                font-size: 18px;
                border: none;
                border-radius: 5px;
                background: linear-gradient(to right, #007BFF, #0056b3);
                color: white;
                cursor: pointer;
                box-shadow: 0 3px 10px rgba(0, 0, 0, 0.3);
                transition: all 0.3s ease;
            }
            button:hover {
                background: linear-gradient(to right, #0056b3, #003d99);
                transform: translateY(-2px);
            }
            footer {
                width: 100%;
                background: #004080;
                padding: 10px;
                text-align: center;
                font-size: 14px;
            }
            #message {
                margin-top: 20px;
                font-size: 18px;
                color: white;
                background: rgba(0, 0, 0, 0.6);
                padding: 10px 15px;
                border-radius: 5px;
            }
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


if __name__ == '__main__':
    if camera is None:
        print("Cannot start app - no camera found!")
    app.run(host='0.0.0.0', port=5000, debug=True)
