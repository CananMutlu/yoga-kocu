import math
import cv2
import mediapipe as mp
from mediapipe.tasks.python import BaseOptions, vision

KAYNAK = 0  # 0: bilgisayarın kamerası. Video denemek için: "video.mp4"
MODEL = "pose_landmarker_lite.task"

# Üç noktanın ortasındaki (b) açıyı derece olarak hesaplar.
def aci(a, b, c):
    derece = math.degrees(
        math.atan2(c[1] - b[1], c[0] - b[0]) - math.atan2(a[1] - b[1], a[0] - b[0])
    )
    derece = abs(derece)
    return 360 - derece if derece > 180 else derece

ayarlar = vision.PoseLandmarkerOptions(
    base_options=BaseOptions(model_asset_path=MODEL),
    running_mode=vision.RunningMode.VIDEO,
)
baglantilar = vision.PoseLandmarksConnections.POSE_LANDMARKS

kamera = cv2.VideoCapture(KAYNAK)
kare_no = 0

with vision.PoseLandmarker.create_from_options(ayarlar) as model:
    while True:
        okundu, kare = kamera.read()
        if not okundu:
            break

        kare_no += 1
        rgb = cv2.cvtColor(kare, cv2.COLOR_BGR2RGB)
        goruntu = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
        sonuc = model.detect_for_video(goruntu, kare_no * 33)

        if sonuc.pose_landmarks:
            yukseklik, genislik = kare.shape[:2]
            # Noktaları piksele çeviriyoruz; açı ancak böyle doğru çıkar.
            noktalar = [(n.x * genislik, n.y * yukseklik) for n in sonuc.pose_landmarks[0]]

            # Çizgiler: 11 numaradan küçük noktalar yüzdür, onları çizmiyoruz.
            for b in baglantilar:
                if b.start < 11 or b.end < 11:
                    continue
                bas = tuple(map(int, noktalar[b.start]))
                son = tuple(map(int, noktalar[b.end]))
                cv2.line(kare, bas, son, (0, 255, 0), 2)

            # Noktalar: burun (0) ve omuzdan ayağa kadar olan eklemler (11 ve sonrası)
            for i, nokta in enumerate(noktalar):
                if i == 0 or i >= 11:
                    cv2.circle(kare, tuple(map(int, nokta)), 6, (0, 0, 255), -1)

            # Diz açıları: kalça - diz - ayak bileği
            sol_diz = aci(noktalar[23], noktalar[25], noktalar[27])
            sag_diz = aci(noktalar[24], noktalar[26], noktalar[28])
            # Dirsek açıları: omuz - dirsek - bilek
            sol_dirsek = aci(noktalar[11], noktalar[13], noktalar[15])
            sag_dirsek = aci(noktalar[12], noktalar[14], noktalar[16])

            cv2.putText(kare, f"Sol diz: {sol_diz:.0f}  Sag diz: {sag_diz:.0f}",
                        (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 0, 255), 2)
            cv2.putText(kare, f"Sol dirsek: {sol_dirsek:.0f}  Sag dirsek: {sag_dirsek:.0f}",
                        (20, 80), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (255, 0, 0), 2)

        cv2.imshow("Yoga Kocu - cikmak icin q", kare)
        if cv2.waitKey(1) & 0xFF == ord("q"):
            break

kamera.release()
cv2.destroyAllWindows()