"""Canli karsilastirma denemesi (T3).

Kamerada (ya da video dosyasinda) iskelet ve acilari cikarir, profilden elle
secilen anahtar pozla karsilastirir; durum, benzerlik ve hatalari ekrana yazar.
Oynatma ani (Beam Pro) henuz yok: t olarak secilen pozun ortasi kullanilir.

Kullanim:
  python canli_deneme.py cikti/video_profil.json            # kamera 0
  python canli_deneme.py cikti/video_profil.json --poz 3    # 3. pozla basla
  python canli_deneme.py cikti/video_profil.json --kaynak video.mp4

Tuslar:  n = sonraki poz   p = onceki poz   q = cikis
"""
import argparse
import glob
import os
import sys
import time

import cv2
import mediapipe as mp
from mediapipe.tasks.python import BaseOptions, vision

from acilar import AciYumusatici, hesapla_acilar
from karsilastirma import ZAMAN_PAYI_SN, karsilastir, profil_oku

MODEL = "pose_landmarker_lite.task"
ISLEME_GENISLIGI = 960

# Hatali eklemi ekranda isaretlemek icin eklem adi -> MediaPipe nokta numarasi
EKLEM_NOKTASI = {
    "sol_omuz": 11, "sag_omuz": 12, "sol_dirsek": 13, "sag_dirsek": 14,
    "sol_kalca": 23, "sag_kalca": 24, "sol_diz": 25, "sag_diz": 26,
}
# Ekranda Turkce karakter cizilemez (OpenCV), bu yuzden ASCII yazilir
YON = {"azalt": "daha cok buk/kapat", "artir": "daha cok ac"}
RENK = {
    "dogru": (0, 200, 0), "hata": (0, 0, 255), "kadraja_gir": (0, 165, 255),
    "poz_yok": (200, 0, 200), "gecis": (160, 160, 160), "oynatma_yok": (160, 160, 160),
}


def en_yeni_profil():
    adaylar = glob.glob(os.path.join("cikti", "*_profil.json"))
    return max(adaylar, key=os.path.getmtime) if adaylar else None


def satirlari_yaz(kare, satirlar, renkler):
    # Yazi boyutu kare genisligine gore olceklenir (kucuk kamera karesinde ekrani kaplamasin)
    olcek = max(0.4, min(0.6, kare.shape[1] / 1600))
    satir_yuksekligi = round(43 * olcek)
    kalinlik = 1
    genislik = max(cv2.getTextSize(s, cv2.FONT_HERSHEY_SIMPLEX, olcek, kalinlik)[0][0] for s in satirlar)
    cv2.rectangle(kare, (0, 0), (genislik + 20, 12 + satir_yuksekligi * len(satirlar)), (0, 0, 0), -1)
    for i, (s, r) in enumerate(zip(satirlar, renkler)):
        cv2.putText(kare, s, (10, satir_yuksekligi * (i + 1)), cv2.FONT_HERSHEY_SIMPLEX, olcek, r, kalinlik)


def main():
    ayrac = argparse.ArgumentParser(description="Canli karsilastirma denemesi")
    ayrac.add_argument("profil", nargs="?", help="profil JSON (verilmezse cikti/'daki en yeni)")
    ayrac.add_argument("--kaynak", default="0", help="kamera numarasi ya da video dosyasi")
    ayrac.add_argument("--poz", type=int, default=1, help="baslangic anahtar poz (1'den baslar)")
    ayrac.add_argument("--ust-vucut", action="store_true",
                       help="masa basi deneme: yalniz dirsek ve omuz hedeflerini karsilastir "
                            "(kalca/diz/govde yok sayilir, benzerlik kontrolu kapanir)")
    ayrac.add_argument("--pencere-yok", action="store_true",
                       help="pencere acmadan saniyede bir durumu yazdir (otomatik dogrulama icin)")
    s = ayrac.parse_args()

    yol = s.profil or en_yeni_profil()
    if not yol:
        print("Profil bulunamadi. Once: python referans_isleyici.py video.mp4")
        sys.exit(1)
    profil = profil_oku(yol)
    if s.ust_vucut:
        for poz in profil["anahtar_pozlar"]:
            poz["hedefler"] = [h for h in poz["hedefler"] if h["eklem"].endswith(("_dirsek", "_omuz"))]
    poz_sayisi = len(profil["anahtar_pozlar"])
    secili = min(max(s.poz, 1), poz_sayisi) - 1

    video_mu = not s.kaynak.isdigit()
    kamera = cv2.VideoCapture(s.kaynak if video_mu else int(s.kaynak))
    if not kamera.isOpened():
        print("Kaynak acilamadi:", s.kaynak)
        sys.exit(1)
    fps = (kamera.get(cv2.CAP_PROP_FPS) or 24.0) if video_mu else 30.0

    ayarlar = vision.PoseLandmarkerOptions(
        base_options=BaseOptions(model_asset_path=MODEL),
        running_mode=vision.RunningMode.VIDEO,
    )
    yumusatici = AciYumusatici()
    baglantilar = vision.PoseLandmarksConnections.POSE_LANDMARKS
    baslangic = time.perf_counter()
    kare_no = 0

    with vision.PoseLandmarker.create_from_options(ayarlar) as model:
        while True:
            okundu, kare = kamera.read()
            if not okundu:
                break
            yuk, gen = kare.shape[:2]
            if gen > ISLEME_GENISLIGI:
                kare = cv2.resize(kare, (ISLEME_GENISLIGI, round(yuk * ISLEME_GENISLIGI / gen)))
                yuk, gen = kare.shape[:2]

            zaman = kare_no / fps if video_mu else time.perf_counter() - baslangic
            goruntu = mp.Image(
                image_format=mp.ImageFormat.SRGB,
                data=cv2.cvtColor(kare, cv2.COLOR_BGR2RGB),
            )
            sonuc = model.detect_for_video(goruntu, int(zaman * 1000))
            kare_no += 1

            poz = profil["anahtar_pozlar"][secili]
            t = (poz["baslangic_sn"] + poz["bitis_sn"]) / 2  # sahte oynatma ani

            karsilastirma = None
            noktalar = None
            gorunurluk = None
            if sonuc.pose_landmarks:
                nokta = sonuc.pose_landmarks[0]
                noktalar = [(n.x * gen, n.y * yuk) for n in nokta]
                gorunurluk = [n.visibility for n in nokta]
                canli = yumusatici.ekle(hesapla_acilar(noktalar, gorunurluk))
                # Ust vucut modunda hedef sayisi 2-4'e iner; benzerlik anlamsiz olur, kapatilir
                karsilastirma = karsilastir(canli, profil, t,
                                            benzerlik_esigi=0 if s.ust_vucut else None)

            if s.pencere_yok:
                if kare_no % round(fps) == 0:
                    ozet = "kisi yok" if karsilastirma is None else (
                        f"{karsilastirma['durum']:11s} benzerlik "
                        f"{karsilastirma['benzerlik'] if karsilastirma['benzerlik'] is None else round(karsilastirma['benzerlik'], 4)}  "
                        f"hatalar {[h['eklem'] for h in karsilastirma['hatalar']]}"
                    )
                    print(f"  video {zaman:6.1f} sn  {ozet}", flush=True)
                continue

            # --- Cizim ---
            hatali = set()
            if karsilastirma:
                hatali = {h["eklem"] for h in karsilastirma["hatalar"]}
            if noktalar:
                for b in baglantilar:
                    if b.start < 11 or b.end < 11:
                        continue
                    # Gorunmeyen (kadraj disi/tahmin) noktalar cizilmez
                    if min(gorunurluk[b.start], gorunurluk[b.end]) < 0.5:
                        continue
                    cv2.line(kare, tuple(map(int, noktalar[b.start])),
                             tuple(map(int, noktalar[b.end])), (0, 255, 0), 2)
                for ad in hatali:
                    if ad in EKLEM_NOKTASI:
                        cv2.circle(kare, tuple(map(int, noktalar[EKLEM_NOKTASI[ad]])), 16, (0, 0, 255), 3)

            satirlar = [f"Poz {secili + 1}/{poz_sayisi}  ({poz['baslangic_sn']:.1f}-{poz['bitis_sn']:.1f} sn)  "
                        f"[n/p degistir, q cik]" + ("  UST VUCUT MODU" if s.ust_vucut else "")]
            renkler = [(255, 255, 255)]
            if karsilastirma is None:
                satirlar.append("Kisi gorunmuyor")
                renkler.append((160, 160, 160))
            else:
                d = karsilastirma["durum"]
                b = karsilastirma["benzerlik"]
                if not poz["hedefler"]:
                    d = "hedef_yok (bu pozda dirsek/omuz hedefi yok, n/p ile degistirin)"
                satirlar.append(f"Durum: {d}" + ("" if b is None else f"   benzerlik {b:.3f}"))
                renkler.append(RENK.get(d, (255, 255, 255)))
                if karsilastirma["eksik"]:
                    eksik = karsilastirma["eksik"]
                    ilk = ", ".join(eksik[:2]) + (f" +{len(eksik) - 2}" if len(eksik) > 2 else "")
                    satirlar.append(f"  gorunmeyen: {ilk}")
                    satirlar.append("  Geri cekilin: tum vucut gorunmeli")
                    renkler += [RENK["kadraja_gir"]] * 2
                for h in karsilastirma["hatalar"]:
                    satirlar.append(f"  {h['eklem']}: {h['olculen']:.0f} (hedef {h['hedef']:.0f}, "
                                    f"fark {h['fark']:+.0f}) {YON[h['yon']]}")
                    renkler.append((80, 80, 255))
            satirlari_yaz(kare, satirlar, renkler)

            cv2.imshow("Yoga Kocu - canli karsilastirma", kare)
            tus = cv2.waitKey(1) & 0xFF
            if tus == ord("q"):
                break
            if tus == ord("n"):
                secili = (secili + 1) % poz_sayisi
            if tus == ord("p"):
                secili = (secili - 1) % poz_sayisi

    kamera.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
