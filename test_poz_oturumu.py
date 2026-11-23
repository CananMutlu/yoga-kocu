import csv
import os
import tempfile
import unittest

from poz_oturumu import (
    BITIS,
    CSV_SUTUNLARI,
    DUZELTME,
    HAZIRLIK,
    KADRAJ,
    POZ_BEKLENIYOR,
    TUTUS,
    PozOturumu,
    puan_hesapla,
)

HEDEF = [{"eklem": "sag_diz", "aci": 100, "tolerans": 15, "gorunurluk": 1.0}]
PROFIL = {"video": "egitim.mp4", "anahtar_pozlar": [
    {"baslangic_sn": 10, "bitis_sn": 40, "hedefler": HEDEF},
    {"baslangic_sn": 50, "bitis_sn": 80, "hedefler": HEDEF},
]}


def sonuc(durum, poz=0, hatalar=None):
    return {"durum": durum, "anahtar_poz": poz, "benzerlik": 0.99,
            "hatalar": hatalar or [], "eksik": []}


def hata(eklem, fark):
    return {"eklem": eklem, "hedef": 100, "olculen": 100 + fark, "fark": fark,
            "yon": "azalt" if fark > 0 else "artir"}


UC_HATA = [hata("sag_diz", 40), hata("sol_diz", 25), hata("govde_dikligi", 18)]


def yeni(profil=PROFIL, **ayar):
    varsayilan = dict(isinma_sn=0, karar_bekleme_sn=0, tutus_hedef_sn=5, mesaj_suresi_sn=3,
                      tarih_fn=lambda: "2026-01-01T10:00:00")
    varsayilan.update(ayar)
    return PozOturumu(profil, **varsayilan)


def ver(oturum, bas, sure, s, adim=0.1):
    """bas anindan sure sn boyunca ayni sonucu verir. (son cikti, son zaman) dondurur."""
    n = round(sure / adim)
    cikti = None
    for k in range(1, n + 1):
        cikti = oturum.adim(bas + k * adim, s)
    return cikti, bas + n * adim


class DurumTesti(unittest.TestCase):
    def test_oynatma_yok_hazirlik(self):
        o = yeni()
        c = o.adim(0.0, sonuc("oynatma_yok", poz=None))
        self.assertEqual(c["durum"], HAZIRLIK)
        self.assertEqual(c["puan"], 0)
        self.assertEqual(c["poz"], "")

    def test_gecis_poz_bekleniyor(self):
        o = yeni()
        c = o.adim(0.0, sonuc("gecis", poz=None))
        self.assertEqual(c["durum"], POZ_BEKLENIYOR)
        self.assertEqual(o.kayitlar, [])

    def test_kadraja_gir_hata_mesaji_yok_ve_sure_sayilmaz(self):  # FT-07
        o = yeni()
        o.adim(0.0, sonuc("kadraja_gir"))
        c, _ = ver(o, 0.0, 3.0, sonuc("kadraja_gir"))
        self.assertEqual(c["durum"], KADRAJ)
        self.assertEqual(c["mesaj"], "Kadraja gir")
        self.assertEqual(c["hatali_eklemler"], [])
        self.assertEqual(c["tutus_sn"], 0)
        self.assertEqual(c["puan"], 0)

    def test_poz_yok_poz_bekleniyor(self):
        o = yeni()
        c = o.adim(0.0, sonuc("poz_yok"))
        self.assertEqual(c["durum"], POZ_BEKLENIYOR)
        self.assertEqual(c["mesaj"], "")

    def test_dogru_tutus(self):
        o = yeni()
        o.adim(0.0, sonuc("dogru"))
        c, _ = ver(o, 0.0, 2.0, sonuc("dogru"))
        self.assertEqual(c["durum"], TUTUS)
        self.assertAlmostEqual(c["tutus_sn"], 2.0, places=1)
        self.assertEqual(c["puan"], 100)


class MesajSirasiTesti(unittest.TestCase):
    def test_ilk_mesaj_en_buyuk_fark(self):  # FT-05
        o = yeni()
        c = o.adim(0.0, sonuc("hata", hatalar=UC_HATA))
        self.assertEqual(c["durum"], DUZELTME)
        self.assertIn("sag_diz", c["mesaj"])
        self.assertEqual((c["sira"], c["toplam_hata"]), (1, 3))
        # Tum hatali eklemler (kirmizi isaret icin)
        self.assertEqual(c["hatali_eklemler"], ["govde_dikligi", "sag_diz", "sol_diz"])

    def test_mesajlar_sirayla_ust_uste_binmeden(self):  # FT-05
        o = yeni()
        gorulen = []   # (zaman, sira, mesaj) degisimleri
        onceki = None
        for k in range(0, 112):   # 0.0 - 11.1 sn
            t = k * 0.1
            c = o.adim(t, sonuc("hata", hatalar=UC_HATA))
            if c["mesaj"] != onceki:
                gorulen.append((round(t, 1), c["sira"], c["mesaj"]))
                onceki = c["mesaj"]
        adlar = [("sag_diz" in m, "sol_diz" in m, "govde" in m) for _, _, m in gorulen]
        self.assertEqual(adlar[:3], [(True, False, False), (False, True, False), (False, False, True)])
        self.assertEqual([s for _, s, _ in gorulen[:3]], [1, 2, 3])
        # Her mesaj en az ~3 sn ekranda kalir (ust uste binme yok)
        self.assertAlmostEqual(gorulen[1][0], 3.0, delta=0.2)
        self.assertAlmostEqual(gorulen[2][0], 6.0, delta=0.3)
        # Hepsi soylenip duzelmediyse tur basa doner
        self.assertIn("sag_diz", gorulen[3][2])

    def test_goruntulenen_hata_duzelirse_hemen_gecilir(self):  # FT-17
        o = yeni()
        o.adim(0.0, sonuc("hata", hatalar=UC_HATA))
        kalan = [hata("sol_diz", 25), hata("govde_dikligi", 18)]
        c = o.adim(1.0, sonuc("hata", hatalar=kalan))   # sag_diz duzeldi
        self.assertIn("sol_diz", c["mesaj"])
        self.assertEqual((c["sira"], c["toplam_hata"]), (1, 2))
        self.assertEqual(c["hatali_eklemler"], ["govde_dikligi", "sol_diz"])
        # duzelen hata bir daha soylenmez
        mesajlar = set()
        for k in range(1, 100):
            mesajlar.add(o.adim(1.0 + k * 0.1, sonuc("hata", hatalar=kalan))["mesaj"])
        self.assertFalse(any("sag_diz" in m for m in mesajlar))

    def test_siradaki_hata_beklerken_duzelirse_soylenmez(self):  # FT-17
        o = yeni()
        mesajlar = []
        o.adim(0.0, sonuc("hata", hatalar=UC_HATA))
        # sol_diz (sirada 2.) duzeldi; sag_diz hala var
        kalan = [hata("sag_diz", 40), hata("govde_dikligi", 18)]
        for k in range(1, 80):
            mesajlar.append(o.adim(k * 0.1, sonuc("hata", hatalar=kalan))["mesaj"])
        self.assertFalse(any("sol_diz" in m for m in mesajlar))
        self.assertTrue(any("govde" in m for m in mesajlar))

    def test_hata_kalmayinca_tutusa_gecer(self):
        o = yeni()
        o.adim(0.0, sonuc("hata", hatalar=UC_HATA))
        c = o.adim(0.1, sonuc("dogru"))
        self.assertEqual(c["durum"], TUTUS)
        self.assertEqual(c["mesaj"], "")
        self.assertEqual(c["hatali_eklemler"], [])


class TutusVePuanTesti(unittest.TestCase):
    def test_5sn_dogru_durus_olumlu_mesaj_puan_kayit(self):  # FT-06
        o = yeni()
        o.adim(0.0, sonuc("dogru"))
        c, _ = ver(o, 0.0, 5.3, sonuc("dogru"))
        self.assertEqual(c["durum"], BITIS)
        self.assertEqual(len(o.kayitlar), 1)
        k = o.kayitlar[0]
        self.assertEqual(k["sonuc"], "tamamlandi")
        self.assertEqual(k["puan"], 100)
        self.assertEqual(k["poz"], "egitim.mp4#1")
        self.assertIn("Puan: 100", c["mesaj"])

    def test_tutus_birikimli_hata_puani_dusurur(self):
        o = yeni()
        o.adim(0.0, sonuc("dogru"))
        _, t = ver(o, 0.0, 2.0, sonuc("dogru"))
        c, t = ver(o, t, 2.0, sonuc("hata", hatalar=[hata("sag_diz", 30)]))
        self.assertEqual(c["durum"], DUZELTME)
        self.assertAlmostEqual(c["tutus_sn"], 2.0, places=1)   # hata surede sayilmaz ama sifirlanmaz
        c, t = ver(o, t, 3.5, sonuc("dogru"))
        self.assertEqual(c["durum"], BITIS)
        self.assertEqual(o.kayitlar[0]["sonuc"], "tamamlandi")
        self.assertTrue(65 <= o.kayitlar[0]["puan"] <= 80, o.kayitlar[0]["puan"])
        self.assertEqual(o.kayitlar[0]["hata_sayisi"], 1)

    def test_kadraja_gir_sureyi_durdurur(self):  # FT-07
        o = yeni()
        o.adim(0.0, sonuc("dogru"))
        _, t = ver(o, 0.0, 1.0, sonuc("dogru"))
        c, t = ver(o, t, 3.0, sonuc("kadraja_gir"))
        self.assertEqual(c["durum"], KADRAJ)
        self.assertAlmostEqual(c["tutus_sn"], 1.0, places=1)
        c, t = ver(o, t, 1.0, sonuc("dogru"))
        self.assertEqual(c["durum"], TUTUS)
        self.assertAlmostEqual(c["tutus_sn"], 2.0, places=1)

    def test_tamamlanan_poz_ayni_pozda_yeniden_baslamaz(self):
        o = yeni()
        o.adim(0.0, sonuc("dogru"))
        _, t = ver(o, 0.0, 5.3, sonuc("dogru"))
        c, t = ver(o, t, 10.0, sonuc("dogru"))   # video hala ayni pozda
        self.assertEqual(len(o.kayitlar), 1)
        self.assertEqual(c["durum"], POZ_BEKLENIYOR)   # bitis mesaji suresi doldu

    def test_gecisten_sonra_ayni_poz_yeni_oturum(self):
        o = yeni()
        o.adim(0.0, sonuc("dogru"))
        _, t = ver(o, 0.0, 5.3, sonuc("dogru"))
        o.adim(t + 0.1, sonuc("gecis", poz=None))
        o.adim(t + 0.2, sonuc("dogru"))
        ver(o, t + 0.2, 5.3, sonuc("dogru"))
        self.assertEqual(len(o.kayitlar), 2)

    def test_baska_poza_gecince_oncekini_kapatir(self):
        o = yeni()
        o.adim(0.0, sonuc("hata", hatalar=UC_HATA))
        ver(o, 0.0, 1.0, sonuc("hata", hatalar=UC_HATA))
        c = o.adim(1.2, sonuc("hata", poz=1, hatalar=UC_HATA))
        self.assertEqual(len(o.kayitlar), 1)
        self.assertEqual(o.kayitlar[0]["poz"], "egitim.mp4#1")
        self.assertEqual(o.kayitlar[0]["sonuc"], "sure_doldu")
        self.assertEqual(c["poz"], "egitim.mp4#2")

    def test_hic_pozda_olunmadiysa_atlandi(self):
        o = yeni()
        ver(o, 0.0, 2.0, sonuc("poz_yok"))
        c = o.adim(2.2, sonuc("gecis", poz=None))
        self.assertEqual(o.kayitlar[0]["sonuc"], "atlandi")
        self.assertEqual(o.kayitlar[0]["puan"], 0)
        self.assertIn("atlandı", c["mesaj"])

    def test_kisa_pozda_hedef_ulasilabilir(self):
        kisa = {"video": "v.mp4", "anahtar_pozlar": [
            {"baslangic_sn": 0, "bitis_sn": 3, "hedefler": HEDEF}]}
        o = PozOturumu(kisa)   # varsayilan isinma 2 sn
        c = o.adim(0.0, sonuc("dogru"))
        self.assertEqual(c["hedef_sn"], 1.0)

    def test_puan_hesapla(self):
        self.assertEqual(puan_hesapla(0, 0), 0)
        self.assertEqual(puan_hesapla(5, 10), 50)
        self.assertEqual(puan_hesapla(10, 5), 100)


class IptalVeOzetTesti(unittest.TestCase):
    def test_poz_biterken_soylenmemis_mesajlar_iptal_ve_ozette(self):  # FT-18
        o = yeni()
        o.adim(0.0, sonuc("hata", hatalar=UC_HATA))
        ver(o, 0.0, 0.5, sonuc("hata", hatalar=UC_HATA))   # yalniz sag_diz soylendi
        o.adim(0.7, sonuc("gecis", poz=None))
        k = o.kayitlar[0]
        self.assertEqual(k["sonuc"], "sure_doldu")
        self.assertEqual(k["iptal_edilen"], "govde_dikligi;sol_diz")
        ozet = o.ozet()
        self.assertEqual(ozet["iptal_edilen"], [("egitim.mp4#1", ["govde_dikligi", "sol_diz"])])
        self.assertEqual(ozet["poz_sayisi"], 1)

    def test_tamamlanan_pozda_iptal_yok(self):
        o = yeni()
        o.adim(0.0, sonuc("dogru"))
        ver(o, 0.0, 5.3, sonuc("dogru"))
        self.assertEqual(o.kayitlar[0]["iptal_edilen"], "")
        self.assertEqual(o.ozet()["ortalama_puan"], 100)


class IsinmaVeTitremeTesti(unittest.TestCase):
    def test_isinma_suresinde_hata_verilmez(self):  # FT-14
        o = yeni(isinma_sn=2.0)
        c = o.adim(0.0, sonuc("hata", hatalar=UC_HATA))
        self.assertEqual(c["durum"], POZ_BEKLENIYOR)
        self.assertEqual(c["mesaj"], "")
        c = o.adim(1.5, sonuc("hata", hatalar=UC_HATA))
        self.assertEqual(c["durum"], POZ_BEKLENIYOR)
        c = o.adim(2.1, sonuc("hata", hatalar=UC_HATA))
        self.assertEqual(c["durum"], DUZELTME)
        self.assertIn("sag_diz", c["mesaj"])

    def test_isinmada_dogru_durus_sayilir(self):
        o = yeni(isinma_sn=2.0)
        o.adim(0.0, sonuc("dogru"))
        c = o.adim(1.0, sonuc("dogru"))
        self.assertEqual(c["durum"], TUTUS)
        self.assertAlmostEqual(c["tutus_sn"], 1.0, places=1)

    def test_tek_karelik_hata_tutusu_bozmaz(self):
        o = yeni(karar_bekleme_sn=0.5)
        o.adim(0.0, sonuc("dogru"))
        o.adim(0.1, sonuc("hata", hatalar=[hata("sag_diz", 30)]))
        c = o.adim(0.2, sonuc("dogru"))
        self.assertEqual(c["durum"], TUTUS)

    def test_surekli_hata_duzeltmeye_gecirir(self):
        o = yeni(karar_bekleme_sn=0.5)
        o.adim(0.0, sonuc("dogru"))
        c = None
        for k in range(1, 12):
            c = o.adim(k * 0.1, sonuc("hata", hatalar=[hata("sag_diz", 30)]))
        self.assertEqual(c["durum"], DUZELTME)

    def test_bekleme_sirasinda_bos_hata_listesi_cokmez(self):
        o = yeni(karar_bekleme_sn=0.5)
        o.adim(0.0, sonuc("hata", hatalar=UC_HATA))
        c = o.adim(0.1, sonuc("dogru"))   # duzeltme kosulu henuz bozulmadi
        self.assertEqual(c["durum"], DUZELTME)
        self.assertIn("sag_diz", c["mesaj"])

    def test_takilmada_fazla_sure_sayilmaz(self):
        o = yeni()
        o.adim(0.0, sonuc("dogru"))
        c = o.adim(100.0, sonuc("dogru"))
        self.assertAlmostEqual(c["tutus_sn"], 1.0, places=1)


class KayitTesti(unittest.TestCase):
    def test_csv_yazilir_ve_eklenir(self):
        klasor = tempfile.mkdtemp()
        yol = os.path.join(klasor, "oturum.csv")
        self.addCleanup(lambda: [os.unlink(os.path.join(klasor, f)) for f in os.listdir(klasor)] and os.rmdir(klasor))
        o = yeni(kayit_yolu=yol, kod="T01")
        for poz in (0, 1):
            o.adim(0.0, sonuc("dogru", poz=poz))
            _, t = ver(o, 0.0, 5.3, sonuc("dogru", poz=poz))
            o.adim(t + 0.1, sonuc("gecis", poz=None))
            o._son_zaman = None
        with open(yol, encoding="utf-8") as f:
            satirlar = list(csv.DictReader(f))
        self.assertEqual(list(satirlar[0].keys()), CSV_SUTUNLARI)
        self.assertEqual(len(satirlar), 2)
        self.assertEqual(satirlar[0]["kod"], "T01")
        self.assertEqual(satirlar[0]["sonuc"], "tamamlandi")
        self.assertEqual(satirlar[1]["poz"], "egitim.mp4#2")
        with open(yol, encoding="utf-8") as f:
            self.assertEqual(f.read().count("tarih,kod"), 1)   # baslik bir kez

    def test_sunucu_alanlariyla_uyumlu(self):
        try:
            import sunucu
        except ImportError:
            self.skipTest("flask kurulu degil")
        o = yeni()
        for s in (sonuc("oynatma_yok", poz=None), sonuc("dogru"),
                  sonuc("hata", hatalar=UC_HATA), sonuc("kadraja_gir")):
            self.assertLessEqual(set(o.adim(1.0, s)), set(sunucu.BOS_DURUM))
        sunucu.durum_guncelle(**o.adim(2.0, sonuc("dogru")))   # reddedilmemeli


if __name__ == "__main__":
    unittest.main()
