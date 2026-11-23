"""Ortak aci hesabi. iskelet.py, referans isleyici ve karsilastirma motoru bunu kullanir."""
import math
from collections import deque

# Her aci icin (a, b, c) MediaPipe nokta numaralari. Aci b noktasindadir.
ACI_TANIMLARI = {
    "sol_dirsek": (11, 13, 15),  # omuz - dirsek - bilek
    "sag_dirsek": (12, 14, 16),
    "sol_omuz": (13, 11, 23),    # dirsek - omuz - kalca
    "sag_omuz": (14, 12, 24),
    "sol_kalca": (11, 23, 25),   # omuz - kalca - diz
    "sag_kalca": (12, 24, 26),
    "sol_diz": (23, 25, 27),     # kalca - diz - ayak bilegi
    "sag_diz": (24, 26, 28),
}


# Uc noktanin ortasindaki aciyi derece olarak hesaplar.
def aci(a, b, c):
    derece = math.degrees(
        math.atan2(c[1] - b[1], c[0] - b[0])
        - math.atan2(a[1] - b[1], a[0] - b[0])
    )
    derece = abs(derece)
    return 360 - derece if derece > 180 else derece


# Bu degerin altindaki gorunurluge sahip nokta "gorunmuyor" sayilir.
GORUNURLUK_ESIGI = 0.5

YUMUSATMA_KARE_SAYISI = 10  # rapor: son 10 karenin ortalamasi


# Govde dikligi: kalca ortasindan omuz ortasina giden dogru ile dikey
# arasindaki aci. 0 = tam dik, 90 = yatay, 180 = ters. Aralik 0-180.
def govde_dikligi(noktalar):
    omuz = ((noktalar[11][0] + noktalar[12][0]) / 2,
            (noktalar[11][1] + noktalar[12][1]) / 2)
    kalca = ((noktalar[23][0] + noktalar[24][0]) / 2,
             (noktalar[23][1] + noktalar[24][1]) / 2)
    dx = omuz[0] - kalca[0]
    dy = omuz[1] - kalca[1]
    uzunluk = math.hypot(dx, dy)
    if uzunluk == 0:
        return None
    # Goruntude yukari = (0, -1)
    return math.degrees(math.acos(max(-1.0, min(1.0, -dy / uzunluk))))


# noktalar: 33 noktalik (x, y) listesi.
# gorunurluk: 33 degerlik liste (verilirse), gorunmeyen eklemin acisi None olur.
# Donus: {aci_adi: derece ya da None}
def hesapla_acilar(noktalar, gorunurluk=None):
    sonuc = {}
    for ad, (a, b, c) in ACI_TANIMLARI.items():
        if gorunurluk is not None and min(
            gorunurluk[a], gorunurluk[b], gorunurluk[c]
        ) < GORUNURLUK_ESIGI:
            sonuc[ad] = None
        else:
            sonuc[ad] = aci(noktalar[a], noktalar[b], noktalar[c])

    govde_gorunur = gorunurluk is None or min(
        gorunurluk[11], gorunurluk[12], gorunurluk[23], gorunurluk[24]
    ) >= GORUNURLUK_ESIGI
    sonuc["govde_dikligi"] = govde_dikligi(noktalar) if govde_gorunur else None
    return sonuc


# Her aci icin son N karenin ortalamasini alir. None degerler atlanir;
# penceredeki tum degerler None ise sonuc None olur.
class AciYumusatici:
    def __init__(self, kare_sayisi=YUMUSATMA_KARE_SAYISI):
        self.kare_sayisi = kare_sayisi
        self.gecmis = {}

    def ekle(self, acilar):
        yumusak = {}
        for ad, deger in acilar.items():
            pencere = self.gecmis.setdefault(ad, deque(maxlen=self.kare_sayisi))
            pencere.append(deger)
            gecerli = [d for d in pencere if d is not None]
            yumusak[ad] = sum(gecerli) / len(gecerli) if gecerli else None
        return yumusak
