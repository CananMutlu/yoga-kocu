import random
import unittest

from anahtar_poz import (
    EKLEM_TURLERI,
    bosluk_doldur,
    profil_dogrula,
    profil_olustur,
    sabit_bolumler,
)
from hatalar import ReferansHatasi

FPS = 24


def seri(*parcalar):
    """('sabit', sn, deger) ya da ('gecis', sn, bas, son) parcalarindan aci serisi."""
    sonuc = []
    for p in parcalar:
        kare = round(p[1] * FPS)
        if p[0] == "sabit":
            sonuc += [p[2]] * kare
        else:
            sonuc += [p[2] + (p[3] - p[2]) * (k + 1) / kare for k in range(kare)]
    return sonuc


def iki_tutus():
    """3 sn tutus A, 1 sn gecis, 3 sn tutus B. diz/kalca/govde degisir."""
    diz = seri(("sabit", 3, 100), ("gecis", 1, 100, 170), ("sabit", 3, 170))
    kalca = seri(("sabit", 3, 90), ("gecis", 1, 90, 175), ("sabit", 3, 175))
    govde = seri(("sabit", 3, 10), ("gecis", 1, 10, 60), ("sabit", 3, 60))
    return diz, kalca, govde


def kareler_yap(diz, kalca, govde, sol=True, maske=None):
    """Her kare icin {'t', 'acilar'} uretir. maske: {aci_adi: [bool]} False -> None."""
    kareler = []
    for k in range(len(diz)):
        a = {}
        for tur in EKLEM_TURLERI:
            deger = {"diz": diz[k], "kalca": kalca[k], "dirsek": 170.0, "omuz": 40.0}[tur]
            a[f"sag_{tur}"] = deger
            a[f"sol_{tur}"] = deger if sol else None
        a["govde_dikligi"] = govde[k]
        for ad, m in (maske or {}).items():
            if not m[k]:
                a[ad] = None
        kareler.append({"t": k / FPS, "acilar": a})
    return kareler


class BoslukTesti(unittest.TestCase):
    def test_kisa_bosluk_dogrusal_dolar(self):
        s = bosluk_doldur([10, None, None, 40], FPS)
        self.assertEqual(s, [10, 20, 30, 40])

    def test_uzun_bosluk_dolmaz(self):
        s = bosluk_doldur([10] + [None] * 20 + [40], FPS)  # 20 kare > 0.5 sn
        self.assertEqual(s.count(None), 20)

    def test_bastaki_ve_sondaki_bosluk_dolmaz(self):
        s = bosluk_doldur([None, None, 5, 5, None], FPS)
        self.assertEqual(s, [None, None, 5, 5, None])


class BolumAyirmaTesti(unittest.TestCase):
    def test_iki_tutus_iki_bolum(self):
        d, k, g = iki_tutus()
        kareler = kareler_yap(d, k, g)
        seriler = {ad: [x["acilar"][ad] for x in kareler] for ad in kareler[0]["acilar"]}
        b = sabit_bolumler(seriler, FPS)
        self.assertEqual(len(b), 2)
        self.assertLess(b[0][1], 80)       # birinci tutus ~0-72. kare
        self.assertGreater(b[1][0], 90)    # ikincisi gecisten sonra
        self.assertGreater(b[1][1] - b[1][0], 60)

    def test_cok_kisa_tutus_poz_sayilmaz(self):
        diz = seri(("gecis", 1, 100, 170), ("sabit", 1, 170), ("gecis", 1, 170, 100))
        kalca = seri(("gecis", 1, 90, 175), ("sabit", 1, 175), ("gecis", 1, 175, 90))
        govde = seri(("gecis", 1, 10, 60), ("sabit", 1, 60), ("gecis", 1, 60, 10))
        kareler = kareler_yap(diz, kalca, govde)
        seriler = {ad: [x["acilar"][ad] for x in kareler] for ad in kareler[0]["acilar"]}
        self.assertEqual(sabit_bolumler(seriler, FPS), [])

    def test_tek_kare_sicrama_bolumu_bolmez(self):
        d, k, g = iki_tutus()
        d[30] += 40  # tek karelik gurultu
        kareler = kareler_yap(d, k, g)
        seriler = {ad: [x["acilar"][ad] for x in kareler] for ad in kareler[0]["acilar"]}
        self.assertEqual(len(sabit_bolumler(seriler, FPS)), 2)


class ProfilTesti(unittest.TestCase):
    def test_iki_anahtar_poz_ve_zaman(self):
        d, k, g = iki_tutus()
        p = profil_olustur(kareler_yap(d, k, g), FPS, "ornek.mp4")
        self.assertEqual(p["video"], "ornek.mp4")
        self.assertEqual(len(p["anahtar_pozlar"]), 2)
        a, b = p["anahtar_pozlar"]
        self.assertLess(a["baslangic_sn"], a["bitis_sn"])
        self.assertLess(a["bitis_sn"], b["baslangic_sn"])
        diz_a = next(h for h in a["hedefler"] if h["eklem"] == "sag_diz")
        diz_b = next(h for h in b["hedefler"] if h["eklem"] == "sag_diz")
        self.assertAlmostEqual(diz_a["aci"], 100, delta=2)
        self.assertAlmostEqual(diz_b["aci"], 170, delta=2)
        self.assertEqual(diz_a["tolerans"], 15)

    def test_onden_cekimde_sol_ve_sag_ayri_hedef(self):
        d, k, g = iki_tutus()
        p = profil_olustur(kareler_yap(d, k, g, sol=True), FPS, "v.mp4")
        adlar = {h["eklem"] for h in p["anahtar_pozlar"][0]["hedefler"]}
        self.assertIn("sol_diz", adlar)
        self.assertIn("sag_diz", adlar)
        self.assertNotIn("yakin_diz", adlar)

    def test_yandan_cekimde_yakin_taraf_adi(self):
        d, k, g = iki_tutus()
        p = profil_olustur(kareler_yap(d, k, g, sol=False), FPS, "v.mp4")
        adlar = {h["eklem"] for h in p["anahtar_pozlar"][0]["hedefler"]}
        self.assertIn("yakin_diz", adlar)
        self.assertIn("govde_dikligi", adlar)
        self.assertFalse(any(a.startswith(("sol_", "sag_")) for a in adlar))

    def test_az_gorunen_eklem_hedefe_girmez(self):
        d, k, g = iki_tutus()
        # sag_diz 12 kare gorunur / 12 kare gorunmez: gorunurluk ~%50 < %70
        maske = {"sag_diz": [(i // 12) % 2 == 0 for i in range(len(d))]}
        p = profil_olustur(kareler_yap(d, k, g, sol=False, maske=maske), FPS, "v.mp4")
        for poz in p["anahtar_pozlar"]:
            adlar = {h["eklem"] for h in poz["hedefler"]}
            self.assertNotIn("yakin_diz", adlar)
            self.assertIn("yakin_kalca", adlar)

    def test_gorunurluk_orani_yazilir(self):
        d, k, g = iki_tutus()
        p = profil_olustur(kareler_yap(d, k, g, sol=False), FPS, "v.mp4")
        for h in p["anahtar_pozlar"][0]["hedefler"]:
            self.assertGreaterEqual(h["gorunurluk"], 0.7)
            self.assertLessEqual(h["gorunurluk"], 1.0)

    def test_surekli_hareket_hata_verir(self):
        rnd = random.Random(1)
        n = 10 * FPS
        d = [rnd.uniform(40, 170) for _ in range(n)]
        k = [rnd.uniform(40, 170) for _ in range(n)]
        g = [rnd.uniform(0, 90) for _ in range(n)]
        with self.assertRaises(ReferansHatasi):
            profil_olustur(kareler_yap(d, k, g), FPS, "v.mp4")

    def test_kisi_yok_hata_verir(self):
        kareler = [{"t": i / FPS, "acilar": None} for i in range(100)]
        with self.assertRaises(ReferansHatasi):
            profil_olustur(kareler, FPS, "v.mp4")


class BirlestirmeTesti(unittest.TestCase):
    def _poz_sayisi(self, diz, kalca, govde):
        return len(profil_olustur(kareler_yap(diz, kalca, govde), FPS, "v.mp4")["anahtar_pozlar"])

    def test_hafif_kayan_ayni_tutus_tek_poz(self):
        # diz 100 -> 111: 10 derece esigini asip bolumu boler ama ayni pozdur
        diz = seri(("sabit", 3, 100), ("sabit", 3, 111))
        kalca = seri(("sabit", 6, 90))
        govde = seri(("sabit", 6, 10))
        self.assertEqual(self._poz_sayisi(diz, kalca, govde), 1)

    def test_belirgin_farkli_pozlar_birlesmez(self):
        diz = seri(("sabit", 3, 100), ("sabit", 3, 130))
        kalca = seri(("sabit", 3, 90), ("sabit", 3, 120))
        govde = seri(("sabit", 3, 10), ("sabit", 3, 40))
        self.assertEqual(self._poz_sayisi(diz, kalca, govde), 2)

    def test_arada_hareket_varsa_ayni_poz_ayri_kalir(self):
        # A tutus, 1 sn baska harekete gidip don, yine A tutus: bosluk > 0.5 sn
        diz = seri(("sabit", 3, 100), ("gecis", 0.5, 100, 170), ("gecis", 0.5, 170, 100), ("sabit", 3, 100))
        kalca = seri(("sabit", 3, 90), ("gecis", 0.5, 90, 170), ("gecis", 0.5, 170, 90), ("sabit", 3, 90))
        govde = seri(("sabit", 3, 10), ("gecis", 0.5, 10, 80), ("gecis", 0.5, 80, 10), ("sabit", 3, 10))
        self.assertEqual(self._poz_sayisi(diz, kalca, govde), 2)

    def test_zincirleme_kayma_tek_pozda_birikmez(self):
        # 100 -> 111 -> 122 -> 133: her adim yakin, ama 133 ilk pozdan cok uzak
        diz = seri(("sabit", 2, 100), ("sabit", 2, 111), ("sabit", 2, 122), ("sabit", 2, 133))
        kalca = seri(("sabit", 8, 90))
        govde = seri(("sabit", 8, 10))
        self.assertGreaterEqual(self._poz_sayisi(diz, kalca, govde), 2)


class DogrulamaTesti(unittest.TestCase):
    def _profil(self, **hedef):
        h = {"eklem": "sag_diz", "aci": 95, "tolerans": 15}
        h.update(hedef)
        return {"video": "v", "anahtar_pozlar": [
            {"baslangic_sn": 1, "bitis_sn": 3, "hedefler": [h]}]}

    def test_gecerli_profil(self):
        profil_dogrula(self._profil())

    def test_aci_aralik_disi(self):
        for aci in (-1, 181):
            with self.assertRaises(ReferansHatasi):
                profil_dogrula(self._profil(aci=aci))

    def test_aci_sinirlari_gecerli(self):
        profil_dogrula(self._profil(aci=0))
        profil_dogrula(self._profil(aci=180))

    def test_tolerans_pozitif_olmali(self):
        for t in (0, -5):
            with self.assertRaises(ReferansHatasi):
                profil_dogrula(self._profil(tolerans=t))

    def test_hedefsiz_poz(self):
        p = self._profil()
        p["anahtar_pozlar"][0]["hedefler"] = []
        with self.assertRaises(ReferansHatasi):
            profil_dogrula(p)

    def test_baslangic_bitisten_once_olmali(self):
        p = self._profil()
        p["anahtar_pozlar"][0]["bitis_sn"] = 1
        with self.assertRaises(ReferansHatasi):
            profil_dogrula(p)


if __name__ == "__main__":
    unittest.main()
