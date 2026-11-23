
import math
import time
import cv2
import mediapipe as mp
from mediapipe.tasks.python import BaseOptions, vision

KAYNAK = 0  # 0: bilgisayarin kamerasi
MODEL = "pose_landmarker_lite.task"
YUZU_BULANIKLASTIR = True

# Uc noktanin ortasindaki aciyi derece olarak hesaplar.
def aci(a, b, c):
    derece = math.degrees(
        math.atan2(c[1] - b[1], c[0] - b[0])
        - math.atan2(a[1] - b[1], a[0] - b[0])
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

# FPS olcum degiskenleri
baslangic_zamani = time.perf_counter()
son_fps_zamani = baslangic_zamani

fps_sayaci = 0
toplam_kare = 0
fps = 0.0
ortalama_fps = 0.0

# MediaPipe video zaman damgasi
video_baslangic = time.perf_counter()

with vision.PoseLandmarker.create_from_options(ayarlar) as model:

    while True:
        okundu, kare = kamera.read()

        if not okundu:
            print("Kamera okunamadi.")
            break

        kare_no += 1

        # Gercek zamanli FPS sayimi
        fps_sayaci += 1
        toplam_kare += 1

        simdiki_zaman = time.perf_counter()
        gecen_sure = simdiki_zaman - son_fps_zamani

        if gecen_sure >= 1.0:
            fps = fps_sayaci / gecen_sure
            fps_sayaci = 0
            son_fps_zamani = simdiki_zaman

        # Test baslangicindan itibaren ortalama FPS
        toplam_sure = simdiki_zaman - baslangic_zamani

        if toplam_sure > 0:
            ortalama_fps = toplam_kare / toplam_sure

        # Goruntuyu RGB formatina donustur
        rgb = cv2.cvtColor(kare, cv2.COLOR_BGR2RGB)

        goruntu = mp.Image(
            image_format=mp.ImageFormat.SRGB,
            data=rgb
        )

        # Gercek zamanli video zaman damgasi
        zaman_damgasi = int(
            (simdiki_zaman - video_baslangic) * 1000
        )

        sonuc = model.detect_for_video(goruntu, zaman_damgasi)

        if sonuc.pose_landmarks:
            yukseklik, genislik = kare.shape[:2]

            # Noktalari piksele cevir
            noktalar = [
                (n.x * genislik, n.y * yukseklik)
                for n in sonuc.pose_landmarks[0]
            ]

            # Yuz bulaniklastirma
            if YUZU_BULANIKLASTIR:
                xs = [p[0] for p in noktalar[:11]]
                ys = [p[1] for p in noktalar[:11]]

                pay = 0.6 * (max(xs) - min(xs))

                x1 = max(int(min(xs) - pay), 0)
                x2 = min(int(max(xs) + pay), genislik)
                y1 = max(int(min(ys) - pay), 0)
                y2 = min(int(max(ys) + pay), yukseklik)

                if x2 > x1 and y2 > y1:
                    kare[y1:y2, x1:x2] = cv2.GaussianBlur(
                        kare[y1:y2, x1:x2],
                        (99, 99),
                        30
                    )

            # Iskelet cizgileri
            for b in baglantilar:
                if b.start < 11 or b.end < 11:
                    continue

                bas = tuple(map(int, noktalar[b.start]))
                son = tuple(map(int, noktalar[b.end]))

                cv2.line(kare, bas, son, (0, 255, 0), 2)

            # Eklem noktalari
            for i, nokta in enumerate(noktalar):
                if i == 0 or i >= 11:
                    cv2.circle(
                        kare,
                        tuple(map(int, nokta)),
                        6,
                        (0, 0, 255),
                        -1
                    )

            # Diz acilari: kalca - diz - ayak bilegi
            sol_diz = aci(noktalar[23], noktalar[25], noktalar[27])
            sag_diz = aci(noktalar[24], noktalar[26], noktalar[28])

            # Dirsek acilari: omuz - dirsek - bilek
            sol_dirsek = aci(noktalar[11], noktalar[13], noktalar[15])
            sag_dirsek = aci(noktalar[12], noktalar[14], noktalar[16])

            cv2.putText(
                kare,
                f"Sol diz: {sol_diz:.0f}  Sag diz: {sag_diz:.0f}",
                (20, 40),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.9,
                (0, 0, 255),
                2
            )

            cv2.putText(
                kare,
                f"Sol dirsek: {sol_dirsek:.0f}  Sag dirsek: {sag_dirsek:.0f}",
                (20, 80),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.9,
                (255, 0, 0),
                2
            )

        # Anlik FPS
        cv2.putText(
            kare,
            f"Anlik FPS: {fps:.1f}",
            (20, 120),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.8,
            (0, 255, 0),
            2
        )

        # Ortalama FPS
        cv2.putText(
            kare,
            f"Ortalama FPS: {ortalama_fps:.1f}",
            (20, 155),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.8,
            (0, 255, 255),
            2
        )

        cv2.imshow("Yoga Kocu - cikmak icin q", kare)

        if cv2.waitKey(1) & 0xFF == ord("q"):
            break

# Test sonu
toplam_sure = time.perf_counter() - baslangic_zamani

if toplam_sure > 0:
    ortalama_fps = toplam_kare / toplam_sure

print("\n--- FPS TEST SONUCU ---")
print(f"Toplam kare: {toplam_kare}")
print(f"Test suresi: {toplam_sure:.2f} saniye")
print(f"Ortalama FPS: {ortalama_fps:.2f}")

kamera.release()
cv2.destroyAllWindows()
