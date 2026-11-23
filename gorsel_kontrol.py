"""Profildeki anahtar pozlarin ortasindaki kareyi iskelet ve acilarla cizer.

Kullanim:  python gorsel_kontrol.py video.mp4 profil.json [cikti_klasoru]
Her poz icin bir PNG ve hepsinin bir arada oldugu montaj uretir.
"""
import json
import os
import sys

import cv2
import mediapipe as mp
import numpy as np
from mediapipe.tasks.python import BaseOptions, vision

from acilar import AciYumusatici, hesapla_acilar

MODEL = "pose_landmarker_lite.task"
GENISLIK = 960
ISINMA_KARE = 15  # yumusatma ve takip oturabilsin diye hedef karenin oncesinden baslanir


def olculen(acilar, ad):
    """Profil hedef adini olculen aciya cevirir (yakin_* icin gorunen taraf)."""
    if ad.startswith("yakin_"):
        tur = ad[len("yakin_"):]
        for yan in ("sag", "sol"):
            if acilar.get(f"{yan}_{tur}") is not None:
                return acilar[f"{yan}_{tur}"], yan
        return None, None
    return acilar.get(ad), None


def kareyi_ciz(video_yolu, poz, no):
    video = cv2.VideoCapture(video_yolu)
    fps = video.get(cv2.CAP_PROP_FPS)
    orta = (poz["baslangic_sn"] + poz["bitis_sn"]) / 2
    hedef_kare = round(orta * fps)
    ilk = max(0, hedef_kare - ISINMA_KARE)
    video.set(cv2.CAP_PROP_POS_FRAMES, ilk)

    ayarlar = vision.PoseLandmarkerOptions(
        base_options=BaseOptions(model_asset_path=MODEL),
        running_mode=vision.RunningMode.VIDEO,
    )
    yumusatici = AciYumusatici()
    baglantilar = vision.PoseLandmarksConnections.POSE_LANDMARKS
    kare = acilar = None

    with vision.PoseLandmarker.create_from_options(ayarlar) as model:
        for k in range(ilk, hedef_kare + 1):
            okundu, kare = video.read()
            if not okundu:
                break
            yuk, gen = kare.shape[:2]
            kare = cv2.resize(kare, (GENISLIK, round(yuk * GENISLIK / gen)))
            yuk, gen = kare.shape[:2]
            goruntu = mp.Image(
                image_format=mp.ImageFormat.SRGB,
                data=cv2.cvtColor(kare, cv2.COLOR_BGR2RGB),
            )
            sonuc = model.detect_for_video(goruntu, int((k - ilk) / fps * 1000))
            if not sonuc.pose_landmarks:
                continue
            nokta = sonuc.pose_landmarks[0]
            xy = [(n.x * gen, n.y * yuk) for n in nokta]
            gorunurluk = [n.visibility for n in nokta]
            acilar = yumusatici.ekle(hesapla_acilar(xy, gorunurluk))
            cizim_noktalari, cizim_gorunurluk = xy, gorunurluk
    video.release()
    if kare is None or acilar is None:
        return None

    # Iskelet: gorunurlugu dusuk noktalar gri, iyi olanlar yesil/kirmizi
    for b in baglantilar:
        if b.start < 11 or b.end < 11:
            continue
        iyi = min(cizim_gorunurluk[b.start], cizim_gorunurluk[b.end]) >= 0.5
        cv2.line(kare, tuple(map(int, cizim_noktalari[b.start])),
                 tuple(map(int, cizim_noktalari[b.end])),
                 (0, 255, 0) if iyi else (160, 160, 160), 3)
    for i, p in enumerate(cizim_noktalari):
        if i >= 11:
            iyi = cizim_gorunurluk[i] >= 0.5
            cv2.circle(kare, tuple(map(int, p)), 6,
                       (0, 0, 255) if iyi else (160, 160, 160), -1)

    # Ust sol: poz bilgisi ve hedef / olculen acilar
    satirlar = [f"#{no}  {poz['baslangic_sn']:.1f}-{poz['bitis_sn']:.1f} sn  (kare {orta:.1f} sn)"]
    for h in poz["hedefler"]:
        deger, yan = olculen(acilar, h["eklem"])
        etiket = h["eklem"] + (f"[{yan}]" if yan else "")
        olc = "-" if deger is None else f"{deger:.0f}"
        satirlar.append(f"{etiket}: profil {h['aci']:.0f}  olculen {olc}")
    kutu_genislik = max(cv2.getTextSize(s, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 1)[0][0] for s in satirlar)
    cv2.rectangle(kare, (0, 0), (kutu_genislik + 24, 14 + 26 * len(satirlar)), (0, 0, 0), -1)
    y = 28
    for s in satirlar:
        cv2.putText(kare, s, (12, y), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1)
        y += 26
    return kare


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Kullanim: python gorsel_kontrol.py video.mp4 profil.json [cikti_klasoru]")
        sys.exit(1)
    video_yolu, profil_yolu = sys.argv[1], sys.argv[2]
    klasor = sys.argv[3] if len(sys.argv) > 3 else os.path.join("cikti", "gorsel")
    os.makedirs(klasor, exist_ok=True)

    profil = json.load(open(profil_yolu, encoding="utf-8"))
    kareler = []
    for no, poz in enumerate(profil["anahtar_pozlar"], 1):
        kare = kareyi_ciz(video_yolu, poz, no)
        if kare is None:
            print(f"#{no}: kare cizilemedi")
            continue
        cv2.imwrite(os.path.join(klasor, f"poz_{no:02d}.png"), kare)
        kareler.append(kare)
        print(f"#{no} tamam")

    # Montaj: 2 sutun
    kucuk = [cv2.resize(k, (800, round(k.shape[0] * 800 / k.shape[1]))) for k in kareler]
    for parca, baslangic in enumerate(range(0, len(kucuk), 6), 1):
        grup = kucuk[baslangic:baslangic + 6]
        if len(grup) % 2:
            grup.append(np.zeros_like(grup[0]))
        satirlar = [np.hstack(grup[i:i + 2]) for i in range(0, len(grup), 2)]
        cv2.imwrite(os.path.join(klasor, f"montaj_{parca}.png"), np.vstack(satirlar))
    print("Kaydedildi:", klasor)
