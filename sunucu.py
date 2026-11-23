"""Koc sunucusu (SCRUM-17 / T7, rapor AG-03).

Sabit birim (bilgisayar) ile giyilebilir birim (Beam Pro) arasindaki tek
haberlesme noktasi:
  GET /video          -> egitim videosu (ileri/geri sarma icin Range destekli)
  GET /durum?t=34.5   -> istemci oynatma anini bildirir, son kocluk durumu JSON

Canli kamera goruntusu bu sunucudan ASLA gonderilmez; agda yalnizca egitim
videosu ve sayisal veri dolasir.

Calistirma:
  python sunucu.py            # bos (hazirlik) durumla baslar
  python sunucu.py --ornek    # rapordaki ornek yanitla baslar (test icin)
"""

import argparse
import copy
import os
import socket
import threading
import time

from flask import Flask, abort, jsonify, request, send_file

VIDEO_YOLU = os.path.join(os.path.dirname(os.path.abspath(__file__)), "videolar", "egitim.mp4")
PORT = 5000

# Rapordaki (C.2-iii) yanit bicimi. Alan adlari degismemeli; istemciler buna bagli.
BOS_DURUM = {
    "poz": "",
    "durum": "hazirlik",
    "mesaj": "",
    "sira": 0,
    "toplam_hata": 0,
    "hatali_eklemler": [],
    "tutus_sn": 0,
    "hedef_sn": 0,
    "puan": 0,
    "noktalar": [],  # [[x, y, z, gorunurluk], ...] 33 nokta
}

ORNEK_DURUM = {
    "poz": "savasci_2",
    "durum": "duzeltme",
    "mesaj": "Sağ dizini biraz daha bük",
    "sira": 1,
    "toplam_hata": 3,
    "hatali_eklemler": ["sag_diz", "kalca", "sag_omuz"],
    "tutus_sn": 3,
    "hedef_sn": 5,
    "puan": 72,
    "noktalar": [[0.5, 0.5, 0.0, 0.99]] * 33,
}

# Sunucu istekleri ayri thread'lerde karsilar; koc modulu de baska bir
# thread'den yazacak. Bu yuzden ortak veriye kilitle erisilir.
_kilit = threading.Lock()
_durum = copy.deepcopy(BOS_DURUM)
_oynatma = {"t": None, "alinma_zamani": None}


def durum_guncelle(**alanlar):
    """Koc modulu yeni sonucu buradan yazar. Ornek:
    durum_guncelle(durum="duzeltme", mesaj="Sağ dizini biraz daha bük", sira=1)
    Rapor biciminde olmayan alan reddedilir."""
    bilinmeyen = set(alanlar) - set(BOS_DURUM)
    if bilinmeyen:
        raise KeyError(f"Rapor biciminde olmayan alan(lar): {sorted(bilinmeyen)}")
    with _kilit:
        _durum.update(alanlar)


def oynatma_ani():
    """Istemcinin bildirdigi son oynatma ani (sn) ve kac saniye once alindigi.
    Henuz bildirilmediyse (None, None). Karsilastirma motoru bunu kullanacak (IG-19)."""
    with _kilit:
        t, alinma = _oynatma["t"], _oynatma["alinma_zamani"]
    if t is None:
        return None, None
    return t, time.monotonic() - alinma


app = Flask(__name__)
app.json.ensure_ascii = False  # Turkce karakterler ş yerine oldugu gibi gitsin
app.json.sort_keys = False     # alanlar rapordaki sirayla gitsin


@app.get("/video")
def video():
    if not os.path.isfile(VIDEO_YOLU):
        abort(404, description=f"Egitim videosu bulunamadi: {VIDEO_YOLU}")
    # conditional=True: tarayicinin Range isteklerine (206 Partial Content) cevap verir,
    # boylece video ileri/geri sarilabilir ve tamami inmeden oynamaya baslar.
    return send_file(VIDEO_YOLU, mimetype="video/mp4", conditional=True)


@app.get("/durum")
def durum():
    t_metin = request.args.get("t")
    if t_metin is not None:
        try:
            t = float(t_metin)
        except ValueError:
            return jsonify(hata="t sayi olmali, ornek: /durum?t=34.5"), 400
        if t < 0:
            return jsonify(hata="t negatif olamaz"), 400
        with _kilit:
            _oynatma["t"] = t
            _oynatma["alinma_zamani"] = time.monotonic()

    with _kilit:
        yanit = copy.deepcopy(_durum)
    return jsonify(yanit)


def yerel_ip():
    """Telefonun baglanacagi yerel ag adresini bulur (internete paket gondermez)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


if __name__ == "__main__":
    ayrac = argparse.ArgumentParser(description="Yoga kocu sunucusu")
    ayrac.add_argument("--ornek", action="store_true", help="rapordaki ornek durumla basla")
    ayrac.add_argument("--port", type=int, default=PORT)
    secenek = ayrac.parse_args()

    if secenek.ornek:
        durum_guncelle(**ORNEK_DURUM)

    ip = yerel_ip()
    print(f"Video : http://{ip}:{secenek.port}/video")
    print(f"Durum : http://{ip}:{secenek.port}/durum?t=34.5")
    # 0.0.0.0: ayni Wi-Fi'daki telefon / Beam Pro da baglanabilsin
    app.run(host="0.0.0.0", port=secenek.port, threaded=True)
