"""Anahtar poz ayirma ve referans profili olusturma (T2).

Girdi: kare kare aci serileri (None = eklem gorunmuyor).
Cikti: rapordaki C.5.3 formatinda profil:
  {"video": "...", "anahtar_pozlar": [
      {"baslangic_sn": 30, "bitis_sn": 60,
       "hedefler": [{"eklem": "sag_diz", "aci": 95, "tolerans": 15, "gorunurluk": 0.98}]}]}

Yandan cekimde kameraya uzak taraf gorunmez. Bu durumda yalnizca bir taraf
guvenilirse hedef "yakin_diz" gibi tarafsiz adla yazilir; canli karsilastirmada
kullanicinin gorunen tarafi onunla kiyaslanir (ters yone donuk kullaniciyi da kapsar).
"""
from statistics import median

from hatalar import ReferansHatasi

# --- Ayarlanabilir parametreler (gercek videoda denenerek secildi) ---
PENCERE_SN = 1.0           # bir bolumun "sabit" sayilmasi icin bakilan pencere
SABIT_ESIK = 10.0          # derece: pencere icinde / bolum boyunca izin verilen oynama
MIN_TUTUS_SN = 1.5         # bundan kisa sabit bolum anahtar poz sayilmaz
TOLERANS_KARE = 3          # bolum sirasinda en fazla bu kadar ust uste sapan kare affedilir
MIN_GECERLI_ORAN = 0.8     # pencerede acinin sabitlik kontrolune girmesi icin gerekli gorunurluk
MIN_KONTROL_ACISI = 3      # sabitlik karari icin en az bu kadar aci kullanilabilmeli
BOSLUK_SN = 0.5            # bundan kisa gorunmeme bosluklari doldurulur
HEDEF_MIN_GORUNURLUK = 0.7 # hedefin profile girmesi icin bolumde gorunme orani
VARSAYILAN_TOLERANS = 15   # derece; rapor: deneme olcumleriyle belirlenecek
BIRLESTIRME_BOSLUGU_SN = 0.5  # yan yana bolumler arasindaki bosluk bundan kisaysa birlestirme adayi
BIRLESTIRME_FARKI = 12.0      # ortak hedeflerin hepsi bu kadar derece icinde ise ayni poz sayilir

EKLEM_TURLERI = ("dirsek", "omuz", "kalca", "diz")


def bosluk_doldur(degerler, fps, max_sn=BOSLUK_SN):
    """Iki gecerli deger arasindaki kisa None bosluklarini dogrusal doldurur.

    Bastaki/sondaki ve max_sn'den uzun bosluklara dokunmaz.
    """
    max_kare = round(max_sn * fps)
    sonuc = list(degerler)
    n = len(degerler)
    i = 0
    while i < n:
        if degerler[i] is not None:
            i += 1
            continue
        j = i
        while j < n and degerler[j] is None:
            j += 1
        if i > 0 and j < n and (j - i) <= max_kare:
            a, b = degerler[i - 1], degerler[j]
            for k in range(i, j):
                sonuc[k] = a + (b - a) * (k - i + 1) / (j - i + 1)
        i = j
    return sonuc


def _pencere_referansi(seriler, i, w):
    """Pencere sabitse {aci_adi: medyan}, degilse None dondurur."""
    ref = {}
    for ad, seri in seriler.items():
        degerler = [v for v in seri[i:i + w] if v is not None]
        if len(degerler) < MIN_GECERLI_ORAN * w:
            continue  # bu aci pencerede yeterince gorunmuyor, kontrole katma
        if max(degerler) - min(degerler) > SABIT_ESIK:
            return None
        ref[ad] = median(degerler)
    return ref if len(ref) >= MIN_KONTROL_ACISI else None


def _uyumlu(seriler, ref, k):
    gorulen = 0
    for ad, hedef in ref.items():
        v = seriler[ad][k]
        if v is None:
            continue
        gorulen += 1
        if abs(v - hedef) > SABIT_ESIK:
            return False
    return gorulen > 0  # hic aci gorunmuyorsa (kisi yok) bolum surmez


def sabit_bolumler(seriler, fps):
    """Aci serilerinde sabit kalan bolumleri [(baslangic_kare, bitis_kare)) dondurur."""
    if not seriler:
        return []
    n = len(next(iter(seriler.values())))
    w = max(2, round(PENCERE_SN * fps))
    min_kare = round(MIN_TUTUS_SN * fps)
    bolumler = []
    i = 0
    while i + w <= n:
        ref = _pencere_referansi(seriler, i, w)
        if ref is None:
            i += 1
            continue
        son = i + w
        kotu = 0
        for k in range(i + w, n):
            if _uyumlu(seriler, ref, k):
                son = k + 1
                kotu = 0
            else:
                kotu += 1
                if kotu > TOLERANS_KARE:
                    break
        if son - i >= min_kare:
            bolumler.append((i, son))
        i = max(son, i + 1)
    return bolumler


def _oran_ve_medyan(seri, i, j):
    degerler = [v for v in seri[i:j] if v is not None]
    oran = len(degerler) / (j - i)
    return oran, (median(degerler) if degerler else None)


def hedefleri_cikar(ham, i, j, tolerans=VARSAYILAN_TOLERANS):
    """[i, j) bolumu icin hedef listesi. ham: gorunmeyen karelerde None olan seriler."""

    def hedef(ad, oran, aci):
        return {
            "eklem": ad,
            "aci": round(aci, 1),
            "tolerans": tolerans,
            "gorunurluk": round(oran, 2),
        }

    hedefler = []
    for tur in EKLEM_TURLERI:
        sol = _oran_ve_medyan(ham[f"sol_{tur}"], i, j) if f"sol_{tur}" in ham else (0, None)
        sag = _oran_ve_medyan(ham[f"sag_{tur}"], i, j) if f"sag_{tur}" in ham else (0, None)
        sol_ok = sol[0] >= HEDEF_MIN_GORUNURLUK
        sag_ok = sag[0] >= HEDEF_MIN_GORUNURLUK
        if sol_ok and sag_ok:  # onden cekim: iki taraf da var
            hedefler.append(hedef(f"sol_{tur}", *sol))
            hedefler.append(hedef(f"sag_{tur}", *sag))
        elif sol_ok or sag_ok:  # yandan cekim: yalniz yakin taraf guvenilir
            oran, aci = sol if sol_ok else sag
            hedefler.append(hedef(f"yakin_{tur}", oran, aci))

    if "govde_dikligi" in ham:
        oran, aci = _oran_ve_medyan(ham["govde_dikligi"], i, j)
        if oran >= HEDEF_MIN_GORUNURLUK:
            hedefler.append(hedef("govde_dikligi", oran, aci))
    return hedefler


def _ayni_poz(hedefler_a, hedefler_b):
    """Iki bolumun ortak hedefleri (en az MIN_KONTROL_ACISI tane) birbirine yakin mi?"""
    a = {h["eklem"]: h["aci"] for h in hedefler_a}
    b = {h["eklem"]: h["aci"] for h in hedefler_b}
    ortak = a.keys() & b.keys()
    if len(ortak) < MIN_KONTROL_ACISI:
        return False
    return all(abs(a[ad] - b[ad]) <= BIRLESTIRME_FARKI for ad in ortak)


def bolumleri_birlestir(bolumler, ham, fps):
    """Aralarinda kisa bosluk olan ve ayni pozu gosteren yan yana bolumleri birlestirir.

    Hafif kayma yuzunden bolunmus tek bir tutusu (ornegin diz 156 -> 146) toparlar.
    Her birlestirmeden sonra yeni bolum bir sonrakiyle yeniden karsilastirilir.
    """
    birlesik = []
    for i, j in bolumler:
        if birlesik:
            onceki_i, onceki_j = birlesik[-1]
            yakin = (i - onceki_j) / fps <= BIRLESTIRME_BOSLUGU_SN
            if yakin and _ayni_poz(
                hedefleri_cikar(ham, onceki_i, onceki_j), hedefleri_cikar(ham, i, j)
            ):
                birlesik[-1] = (onceki_i, j)
                continue
        birlesik.append((i, j))
    return birlesik


def profil_olustur(kareler, fps, video_adi):
    """kareler: [{'t': sn, 'acilar': {...} ya da None}] -> profil sozlugu."""
    ornek = next((k["acilar"] for k in kareler if k["acilar"]), None)
    if ornek is None:
        raise ReferansHatasi("Videoda kisi gorunmuyor.")

    ham = {
        ad: [k["acilar"][ad] if k["acilar"] else None for k in kareler]
        for ad in ornek
    }
    dolu = {ad: bosluk_doldur(seri, fps) for ad, seri in ham.items()}

    anahtar_pozlar = []
    for i, j in bolumleri_birlestir(sabit_bolumler(dolu, fps), ham, fps):
        hedefler = hedefleri_cikar(ham, i, j)
        if not hedefler:
            continue
        anahtar_pozlar.append({
            "baslangic_sn": round(kareler[i]["t"], 2),
            "bitis_sn": round(kareler[j - 1]["t"], 2),
            "hedefler": hedefler,
        })

    if not anahtar_pozlar:
        raise ReferansHatasi("Videoda sabit tutus bolumu bulunamadi; poz ayrilamadi.")

    profil = {"video": video_adi, "anahtar_pozlar": anahtar_pozlar}
    profil_dogrula(profil)
    return profil


def profil_dogrula(profil):
    """Rapor C.5.3 kisitlari: aci 0-180, tolerans pozitif, her pozda >=1 hedef."""
    if not profil.get("anahtar_pozlar"):
        raise ReferansHatasi("Profilde anahtar poz yok.")
    for no, poz in enumerate(profil["anahtar_pozlar"], 1):
        if not poz["baslangic_sn"] < poz["bitis_sn"]:
            raise ReferansHatasi(f"Anahtar poz {no}: baslangic bitisten once olmali.")
        if not poz.get("hedefler"):
            raise ReferansHatasi(f"Anahtar poz {no}: en az bir eklem hedefi olmali.")
        for h in poz["hedefler"]:
            if not 0 <= h["aci"] <= 180:
                raise ReferansHatasi(f"Anahtar poz {no}, {h['eklem']}: aci 0-180 olmali.")
            if h["tolerans"] <= 0:
                raise ReferansHatasi(f"Anahtar poz {no}, {h['eklem']}: tolerans pozitif olmali.")
