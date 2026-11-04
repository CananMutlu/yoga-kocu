import cv2

kamera = cv2.VideoCapture(0)
while True:
    okundu, kare = kamera.read()
    if not okundu:
        print("Kamera okunamadı. Başka bir uygulama kamerayı kullanıyor olabilir.")
        break
    cv2.imshow("Kamera testi - cikmak icin q", kare)
    if cv2.waitKey(1) & 0xFF == ord("q"):
        break
kamera.release()
cv2.destroyAllWindows()