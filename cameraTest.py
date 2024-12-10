import cv2

cap = cv2.VideoCapture('/dev/video0')
if not cap.isOpened():
    print("Cannot open camera")
else:
    ret, frame = cap.read()
    if ret:
        cv2.imwrite('test.jpg', frame)
        print("Camera works! Image saved.")
    else:
        print("Cannot capture frame")
cap.release()