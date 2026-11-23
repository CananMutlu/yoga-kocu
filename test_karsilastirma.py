import json
import os
import tempfile
import unittest

from hatalar import ReferansHatasi
from karsilastirma import (
    anahtar_poz_bul,
    benzerlik,
    hedefleri_coz,
    karsilastir,
    profil_oku,
)


def hedef(ad, aci, tol=15):
    return {"eklem": ad, "aci": aci, "tolerans": tol, "gorunurluk": 1.0}


def profil():
    return {"video": "v.mp4", "anahtar_pozlar": [
        {"baslangic_sn": 10, "bitis_sn": 20, "hedefler": [
            hedef("sag_diz", 100), hedef("sol_diz", 170), hedef("govde_dikligi", 10)]},
        {"baslangic_sn": 30, "bitis_sn": 40, "hedefler": [
            hedef("yakin_diz", 90), hedef("yakin_kalca", 60), hedef("govde_dikligi", 100)]},
    ]}


def canli(**acilar):
    """Verilmeyen acilar None (gorunmuyor)."""
    taban = {f"{y}_{t}": None for y in ("sol", "sag") for t in ("dirsek", "omuz", "kalca", "diz")}
    taban["govde_dikligi"] = None
    taban.update(acilar)
    return taban


DOGRU_1 = dict(sag_diz=100, sol_diz=170, govde_dikligi=10)


class ProfilOkumaTesti(unittest.TestCase):
    def _yaz(self, icerik):
        f = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8")
        json.dump(icerik, f)
        f.close()
        self.addCleanup(os.unlink, f.name)
        return f.name

    def test_gecerli_profil_okunur(self):
        self.assertEqual(profil_oku(self._yaz(profil()))["video"], "v.mp4")

    def test_gecersiz_profil_reddedilir(self):
        bozuk = profil()
        bozuk["anahtar_pozlar"][0]["hedefler"][0]["aci"] = 200
        with self.assertRaises(ReferansHatasi):
            profil_oku(self._yaz(bozuk))

    def test_olmayan_dosya(self):
        with self.assertRaises(ReferansHatasi):
            profil_oku("yok_boyle_dosya.json")


class AnahtarPozBulmaTesti(unittest.TestCase):
    def test_pozun_icinde(self):
        self.assertEqual(anahtar_poz_bul(profil(), 15), 0)
        self.assertEqual(anahtar_poz_bul(profil(), 35), 1)

    def test_gecis_bolumu(self):
        self.assertIsNone(anahtar_poz_bul(profil(), 25))

    def test_kenarlarda_zaman_payi(self):
        # pay 0.5: 10.5-19.5 guvenli
        self.assertIsNone(anahtar_poz_bul(profil(), 10.4))
        self.assertEqual(anahtar_poz_bul(profil(), 10.5), 0)
        self.assertEqual(anahtar_poz_bul(profil(), 19.5), 0)
        self.assertIsNone(anahtar_poz_bul(profil(), 19.6))

    def test_pay_sifir(self):
        self.assertEqual(anahtar_poz_bul(profil(), 10.0, pay_sn=0), 0)

    def test_t_yok(self):
        self.assertIsNone(anahtar_poz_bul(profil(), None))


class KarsilastirmaTesti(unittest.TestCase):
    def test_tam_dogru(self):
        s = karsilastir(canli(**DOGRU_1), profil(), 15)
        self.assertEqual(s["durum"], "dogru")
        self.assertEqual(s["hatalar"], [])
        self.assertEqual(s["anahtar_poz"], 0)

    def test_tolerans_siniri(self):
        # tolerans 15: 14.9 ve 15.0 icerde, 15.1 disarda
        for fark, beklenen in ((14.9, "dogru"), (15.0, "dogru"), (15.1, "hata")):
            c = canli(**dict(DOGRU_1, sag_diz=100 + fark))
            self.assertEqual(karsilastir(c, profil(), 15)["durum"], beklenen, fark)

    def test_alt_sinir(self):
        c = canli(**dict(DOGRU_1, sag_diz=100 - 15.1))
        self.assertEqual(karsilastir(c, profil(), 15)["durum"], "hata")

    def test_yon_ve_fark(self):
        s = karsilastir(canli(**dict(DOGRU_1, sag_diz=130)), profil(), 15)
        h = s["hatalar"][0]
        self.assertEqual(h["eklem"], "sag_diz")
        self.assertEqual(h["fark"], 30)
        self.assertEqual(h["yon"], "azalt")   # cok acik -> daha fazla bukmeli
        s = karsilastir(canli(**dict(DOGRU_1, sag_diz=70)), profil(), 15)
        self.assertEqual(s["hatalar"][0]["yon"], "artir")

    def test_hatalar_buyukten_kucuge(self):
        c = canli(sag_diz=125, sol_diz=100, govde_dikligi=40)  # farklar 25, -70, 30
        # benzerlik kontrolu kapali: burada yalniz siralama sinaniyor
        s = karsilastir(c, profil(), 15, benzerlik_esigi=0)
        self.assertEqual([h["eklem"] for h in s["hatalar"]], ["sol_diz", "govde_dikligi", "sag_diz"])

    def test_esit_farkta_sira_ada_gore_kararli(self):
        c = canli(sag_diz=125, sol_diz=145, govde_dikligi=10)  # 25 ve -25
        s = karsilastir(c, profil(), 15)
        self.assertEqual([h["eklem"] for h in s["hatalar"]], ["sag_diz", "sol_diz"])

    def test_gecis_bolumunde_hata_yok(self):
        s = karsilastir(canli(sag_diz=0, sol_diz=0, govde_dikligi=0), profil(), 25)
        self.assertEqual(s["durum"], "gecis")
        self.assertEqual(s["hatalar"], [])

    def test_oynatma_yok(self):
        self.assertEqual(karsilastir(canli(**DOGRU_1), profil(), None)["durum"], "oynatma_yok")

    def test_gorunmeyen_eklem_kadraja_gir(self):
        c = canli(sag_diz=100, sol_diz=None, govde_dikligi=10)
        s = karsilastir(c, profil(), 15)
        self.assertEqual(s["durum"], "kadraja_gir")
        self.assertEqual(s["eksik"], ["sol_diz"])
        self.assertEqual(s["hatalar"], [])   # hata yerine uyari

    def test_farkli_poz_yapiliyorsa_poz_yok(self):
        # 1. poz bekleniyor ama kullanici cok farkli bir duruste
        c = canli(sag_diz=40, sol_diz=40, govde_dikligi=120)
        s = karsilastir(c, profil(), 15)
        self.assertEqual(s["durum"], "poz_yok")
        self.assertEqual(s["hatalar"], [])

    def test_hatali_ama_poz_yapiliyor_hata_listesi(self):
        # +-20 derece hatali ama ayni poz: poz_yok degil, hata olmali
        c = canli(sag_diz=120, sol_diz=150, govde_dikligi=30)
        s = karsilastir(c, profil(), 15)
        self.assertEqual(s["durum"], "hata")
        self.assertEqual(len(s["hatalar"]), 3)

    def test_benzerlik_kontrolu_kapatilabilir(self):
        c = canli(sag_diz=40, sol_diz=40, govde_dikligi=120)
        s = karsilastir(c, profil(), 15, benzerlik_esigi=0)
        self.assertEqual(s["durum"], "hata")


class YakinTarafTesti(unittest.TestCase):
    T = 35  # 2. poz: yakin_diz 90, yakin_kalca 60, govde 100

    def test_yalniz_sag_gorunuyor(self):
        s = karsilastir(canli(sag_diz=90, sag_kalca=60, govde_dikligi=100), profil(), self.T)
        self.assertEqual(s["durum"], "dogru")

    def test_yalniz_sol_gorunuyor_ters_donuk_kullanici(self):
        s = karsilastir(canli(sol_diz=90, sol_kalca=60, govde_dikligi=100), profil(), self.T)
        self.assertEqual(s["durum"], "dogru")

    def test_hata_cozulmus_gercek_adla_bildirilir(self):
        # sol taraf gorunuyor ve 40 derece hatali: cikti "sol_diz" olmali, "yakin_diz" degil
        s = karsilastir(canli(sol_diz=130, sol_kalca=60, govde_dikligi=100), profil(), self.T)
        self.assertEqual(s["hatalar"][0]["eklem"], "sol_diz")

    def test_iki_taraf_gorunurse_hedefe_yakin_olan(self):
        coz, eksik = hedefleri_coz(
            profil()["anahtar_pozlar"][1],
            canli(sag_diz=150, sol_diz=92, sag_kalca=60, govde_dikligi=100),
        )
        diz = next(c for c in coz if c["eklem"].endswith("_diz"))
        self.assertEqual(diz["eklem"], "sol_diz")
        self.assertEqual(eksik, [])

    def test_iki_taraf_da_gorunmuyorsa_eksik(self):
        s = karsilastir(canli(sag_kalca=60, govde_dikligi=100), profil(), self.T)
        self.assertEqual(s["durum"], "kadraja_gir")
        self.assertEqual(s["eksik"], ["yakin_diz"])


class BenzerlikTesti(unittest.TestCase):
    def test_ayni_vektor_bir(self):
        coz = [{"olculen": 100, "hedef": 100}, {"olculen": 50, "hedef": 50}]
        self.assertAlmostEqual(benzerlik(coz), 1.0)

    def test_bos_liste(self):
        self.assertIsNone(benzerlik([]))


if __name__ == "__main__":
    unittest.main()
