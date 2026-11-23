"""Referans video isleyici (T2).

Adim 2: videoyu kare kare okur, her karede aciyi ve gorunurlugu cikarir.
(Anahtar poz ayirma ve JSON profil yazma sonraki adimlarda eklenecek.)

Kullanim:  python referans_isleyici.py video.mp4
"""
import csv
import json
import os
import sys

import cv2
import mediapipe as mp
from mediapipe.tasks.python import BaseOptions, vision

from acilar import AciYumusatici, hesapla_acilar
from anahtar_poz import profil_olustur
from hatalar import ReferansHatasi

MODEL = "pose_landmarker_lite.task"
ISLEME_GENISLIGI = 960   # 4K kareler modele verilmeden once bu genislige kucultulur
MIN_SURE_SN = 2.0        # bundan kisa video "cok kisa" sayilir
MIN_KISI_ORANI = 0.5     # karelerin en az bu kadarinda kisi gorunmeli
COK_KISI_ORANI = 0.1     # kontrol edilen karelerin bundan fazlasinda 2+ kisi varsa uyar
KISI_KONTROL_ARALIGI = 12  # "birden cok kisi" kontrolu her N. karede yapilir


def acilari_cikar(video_yolu, ilerleme=None):
    """(kareler, fps) dondurur. kareler: her kare icin {'t': saniye, 'acilar': {...}}.

    Kisi gorunmeyen karelerde 'acilar' None olur.
    """
    video = cv2.VideoCapture(video_yolu)
    if not video.isOpened():
        raise ReferansHatasi(f"Video acilamadi: {video_yolu}")

    fps = video.get(cv2.CAP_PROP_FPS) or 24.0
    toplam = int(video.get(cv2.CAP_PROP_FRAME_COUNT))
    if toplam / fps < MIN_SURE_SN:
        raise ReferansHatasi("Video cok kisa; poz ayrilamaz.")

    # Acilar CANLI HATLA AYNI ayarla (num_poses=1) cikarilir. num_poses degisince
    # takip degisip ayni videoda 10+ derece farkli aci cikabiliyor (olculdu).
    ayarlar = vision.PoseLandmarkerOptions(
        base_options=BaseOptions(model_asset_path=MODEL),
        running_mode=vision.RunningMode.VIDEO,
    )
    # "Birden cok kisi" kontrolu ayri ve seyrek bir gecisle yapilir (acilara karismaz).
    kontrol_ayarlari = vision.PoseLandmarkerOptions(
        base_options=BaseOptions(model_asset_path=MODEL),
        running_mode=vision.RunningMode.VIDEO,
        num_poses=2,
    )
    yumusatici = AciYumusatici()
    kareler = []
    kisi_olan = 0
    kontrol_kare = 0
    cok_kisi_olan = 0

    with vision.PoseLandmarker.create_from_options(ayarlar) as model, \
            vision.PoseLandmarker.create_from_options(kontrol_ayarlari) as kontrol:
        no = 0
        while True:
            okundu, kare = video.read()
            if not okundu:
                break

            yuk, gen = kare.shape[:2]
            if gen > ISLEME_GENISLIGI:
                kare = cv2.resize(
                    kare, (ISLEME_GENISLIGI, round(yuk * ISLEME_GENISLIGI / gen))
                )
                yuk, gen = kare.shape[:2]

            goruntu = mp.Image(
                image_format=mp.ImageFormat.SRGB,
                data=cv2.cvtColor(kare, cv2.COLOR_BGR2RGB),
            )
            t = no / fps
            sonuc = model.detect_for_video(goruntu, int(t * 1000))

            if no % KISI_KONTROL_ARALIGI == 0:
                kontrol_kare += 1
                if len(kontrol.detect_for_video(goruntu, int(t * 1000)).pose_landmarks) > 1:
                    cok_kisi_olan += 1

            if sonuc.pose_landmarks:
                kisi_olan += 1
                nokta = sonuc.pose_landmarks[0]
                noktalar = [(n.x * gen, n.y * yuk) for n in nokta]
                gorunurluk = [n.visibility for n in nokta]
                acilar = yumusatici.ekle(hesapla_acilar(noktalar, gorunurluk))
            else:
                acilar = None

            kareler.append({"t": t, "acilar": acilar})
            no += 1
            if ilerleme and no % 100 == 0:
                ilerleme(no, toplam)

    video.release()

    if not kareler or kisi_olan / len(kareler) < MIN_KISI_ORANI:
        raise ReferansHatasi("Videoda kisi gorunmuyor.")
    if kontrol_kare and cok_kisi_olan / kontrol_kare > COK_KISI_ORANI:
        raise ReferansHatasi("Videoda birden cok kisi var; tek kisilik video gerekli.")

    return kareler, fps


def profil_yaz(profil, yol):
    os.makedirs(os.path.dirname(yol) or ".", exist_ok=True)
    with open(yol, "w", encoding="utf-8") as f:
        json.dump(profil, f, ensure_ascii=False, indent=2)


def csv_yaz(kareler, yol):
    """Hata ayiklama icin: kare kare aci tablosu."""
    adlar = next(k["acilar"] for k in kareler if k["acilar"]).keys()
    os.makedirs(os.path.dirname(yol) or ".", exist_ok=True)
    with open(yol, "w", newline="", encoding="utf-8") as f:
        yazici = csv.writer(f)
        yazici.writerow(["t_sn", *adlar])
        for k in kareler:
            a = k["acilar"] or {}
            yazici.writerow(
                [f"{k['t']:.3f}"]
                + ["" if a.get(ad) is None else f"{a[ad]:.1f}" for ad in adlar]
            )


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Kullanim: python referans_isleyici.py video.mp4")
        sys.exit(1)

    yol = sys.argv[1]
    ad = os.path.splitext(os.path.basename(yol))[0]
    try:
        kareler, fps = acilari_cikar(
            yol, ilerleme=lambda n, t: print(f"  {n}/{t} kare", flush=True)
        )
        csv_yaz(kareler, os.path.join("cikti", f"{ad}_acilar.csv"))
        profil = profil_olustur(kareler, fps, os.path.basename(yol))
    except ReferansHatasi as hata:
        print("HATA:", hata)
        sys.exit(2)

    profil_yolu = os.path.join("cikti", f"{ad}_profil.json")
    profil_yaz(profil, profil_yolu)
    print(f"{len(kareler)} kare islendi, {len(profil['anahtar_pozlar'])} anahtar poz bulundu.")
    for no, poz in enumerate(profil["anahtar_pozlar"], 1):
        adlar = ", ".join(h["eklem"] for h in poz["hedefler"])
        print(f"  {no:2d}. {poz['baslangic_sn']:6.2f} - {poz['bitis_sn']:6.2f} sn  [{adlar}]")
    print("Profil:", profil_yolu)
