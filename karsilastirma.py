"""Karsilastirma motoru (T3).

Canli aci degerlerini, videonun o anina denk gelen anahtar pozla eklem eklem
karsilastirir. Turkce mesaj uretmez (T5) ve puan/tutus saymaz (T4); yalnizca
yapilandirilmis sonuc dondurur.

Kullanim:
    profil = profil_oku("cikti/video_profil.json")
    sonuc = karsilastir(canli_acilar, profil, t)
    # canli_acilar: acilar.hesapla_acilar / AciYumusatici ciktisi (gorunmeyen = None)
    # t: videonun oynatma ani, saniye (sunucu.oynatma_ani()'nin ilk degeri)

Sonuc ("durum" alani):
    "oynatma_yok" : t henuz bilinmiyor
    "gecis"       : t hicbir anahtar pozun guvenli icinde degil (hata bildirilmez, IG-20)
    "kadraja_gir" : gerekli eklem(ler) gorunmuyor (hata yerine uyari, IG-08)
    "poz_yok"     : kullanici bu pozu yapmiyor gibi (benzerlik dusuk)
    "dogru"       : tum hedefler tolerans icinde
    "hata"        : en az bir hedef tolerans disinda; "hatalar" buyukten kucuge sirali
"""
import json
import math

from anahtar_poz import profil_dogrula
from hatalar import ReferansHatasi

# Oynatma ani Wi-Fi uzerinden gelir ve kullanici videoyu biraz gecikmeyle izler.
# Anahtar poz ancak [t - pay, t + pay] tamamen pozun icindeyse "guvenli" sayilir.
# Deneme olcumleriyle ayarlanacak (rapor: PT-02 gecikme olcumu).
ZAMAN_PAYI_SN = 0.5

# Canli aci vektoru ile hedef vektoru bundan az benziyorsa kullanici pozu yapmiyordur.
# Ornek videodaki 11 pozla simule edilerek secildi: +-20 derece hatali kullanici en az
# 0.989, gercekten farkli poz (ortalama fark > 25 derece) en cok 0.978 cikti; esik ortada.
# UYARI: hata benzetimi rastgeledir ve boslik dardir (+-0.005). Profil degisince
# (model/ayar) bu sayilar kayiyor. Gercek hatali kullanici kayitlariyla (T6/T18)
# yeniden dogrulanmali. 0 verilirse kontrol kapanir.
BENZERLIK_ESIGI = 0.983


def profil_oku(yol):
    """JSON profili okur ve rapor C.5.3 kisitlariyla dogrular."""
    try:
        with open(yol, encoding="utf-8") as f:
            profil = json.load(f)
    except (OSError, json.JSONDecodeError) as hata:
        raise ReferansHatasi(f"Profil okunamadi: {yol} ({hata})")
    profil_dogrula(profil)
    return profil


def anahtar_poz_bul(profil, t, pay_sn=ZAMAN_PAYI_SN):
    """t anina denk gelen anahtar pozun sirasini dondurur, yoksa None (gecis)."""
    if t is None:
        return None
    for sira, poz in enumerate(profil["anahtar_pozlar"]):
        if poz["baslangic_sn"] <= t - pay_sn and t + pay_sn <= poz["bitis_sn"]:
            return sira
    return None


def hedefleri_coz(poz, canli):
    """Profil hedeflerini canli olcumlerle eslestirir.

    "yakin_diz" gibi tarafsiz hedefler icin kullanicinin gorunen tarafi secilir:
    yalniz bir taraf gorunuyorsa o; ikisi de gorunuyorsa hedefe daha yakin olan
    (yakin tarafi bilinmedigi icin kullaniciyi haksiz yere uyarmamak adina).

    Donus: (cozulen, eksik)
      cozulen: [{"eklem": gercek_ad, "hedef", "tolerans", "olculen"}]
      eksik: olculemeyen (gorunmeyen) hedef adlari
    """
    cozulen, eksik = [], []
    for h in poz["hedefler"]:
        ad = h["eklem"]
        if ad.startswith("yakin_"):
            tur = ad[len("yakin_"):]
            adaylar = [
                (f"{yan}_{tur}", canli[f"{yan}_{tur}"])
                for yan in ("sag", "sol")
                if canli.get(f"{yan}_{tur}") is not None
            ]
            if not adaylar:
                eksik.append(ad)
                continue
            gercek_ad, olculen = min(adaylar, key=lambda a: abs(a[1] - h["aci"]))
        else:
            gercek_ad, olculen = ad, canli.get(ad)
            if olculen is None:
                eksik.append(ad)
                continue
        cozulen.append({
            "eklem": gercek_ad,
            "hedef": h["aci"],
            "tolerans": h["tolerans"],
            "olculen": olculen,
        })
    return cozulen, eksik


def benzerlik(cozulen):
    """Canli ve hedef aci vektorlerinin kosinus benzerligi (0-1 arasi)."""
    if not cozulen:
        return None
    a = [c["olculen"] for c in cozulen]
    b = [c["hedef"] for c in cozulen]
    na, nb = math.sqrt(sum(x * x for x in a)), math.sqrt(sum(x * x for x in b))
    if na == 0 or nb == 0:
        return None
    return sum(x * y for x, y in zip(a, b)) / (na * nb)


def hatalari_bul(cozulen):
    """Tolerans disindaki farklari buyukten kucuge siralar.

    fark = olculen - hedef. "yon": hedefe ulasmak icin acinin ne yapmasi gerektigi
    ("azalt" = daha fazla bukulmeli/kapanmali, "artir" = daha fazla acilmali).
    """
    hatalar = []
    for c in cozulen:
        fark = c["olculen"] - c["hedef"]
        if abs(fark) > c["tolerans"]:
            hatalar.append({
                "eklem": c["eklem"],
                "hedef": round(c["hedef"], 1),
                "olculen": round(c["olculen"], 1),
                "fark": round(fark, 1),
                "yon": "azalt" if fark > 0 else "artir",
            })
    hatalar.sort(key=lambda h: (-abs(h["fark"]), h["eklem"]))
    return hatalar


def karsilastir(canli, profil, t, pay_sn=ZAMAN_PAYI_SN, benzerlik_esigi=None):
    """Canli acilari t anina denk gelen anahtar pozla karsilastirir (bkz. modul aciklamasi)."""
    esik = BENZERLIK_ESIGI if benzerlik_esigi is None else benzerlik_esigi

    sonuc = {"durum": None, "anahtar_poz": None, "benzerlik": None, "hatalar": [], "eksik": []}
    if t is None:
        sonuc["durum"] = "oynatma_yok"
        return sonuc

    sira = anahtar_poz_bul(profil, t, pay_sn)
    if sira is None:
        sonuc["durum"] = "gecis"
        return sonuc
    sonuc["anahtar_poz"] = sira

    cozulen, eksik = hedefleri_coz(profil["anahtar_pozlar"][sira], canli)
    if eksik:
        sonuc["durum"] = "kadraja_gir"
        sonuc["eksik"] = eksik
        return sonuc

    sonuc["benzerlik"] = benzerlik(cozulen)
    if esik is not None and sonuc["benzerlik"] is not None and sonuc["benzerlik"] < esik:
        sonuc["durum"] = "poz_yok"
        return sonuc

    sonuc["hatalar"] = hatalari_bul(cozulen)
    sonuc["durum"] = "hata" if sonuc["hatalar"] else "dogru"
    return sonuc
