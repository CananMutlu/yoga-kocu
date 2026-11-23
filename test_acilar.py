import unittest

from acilar import AciYumusatici, aci, govde_dikligi, hesapla_acilar


def bos_noktalar():
    return [(0.0, 0.0)] * 33


class AciTesti(unittest.TestCase):
    def test_dik_aci(self):
        self.assertAlmostEqual(aci((1, 0), (0, 0), (0, 1)), 90)

    def test_duz_cizgi(self):
        self.assertAlmostEqual(aci((1, 0), (0, 0), (-1, 0)), 180)

    def test_ayni_yon(self):
        self.assertAlmostEqual(aci((1, 0), (0, 0), (2, 0)), 0)

    def test_ust_uste_noktalar_coker_mi(self):
        # Rapor: ust uste gelen noktalar. Hata vermemeli, 0-180 icinde kalmali.
        self.assertTrue(0 <= aci((0, 0), (0, 0), (0, 0)) <= 180)


class GovdeTesti(unittest.TestCase):
    def _govde(self, omuz, kalca):
        n = bos_noktalar()
        n[11] = n[12] = omuz
        n[23] = n[24] = kalca
        return govde_dikligi(n)

    def test_dik(self):
        # Goruntude yukari = y azalir
        self.assertAlmostEqual(self._govde((0, 0), (0, 10)), 0)

    def test_yatay(self):
        self.assertAlmostEqual(self._govde((10, 0), (0, 0)), 90)

    def test_ters(self):
        self.assertAlmostEqual(self._govde((0, 10), (0, 0)), 180)

    def test_omuz_kalca_ayni_nokta(self):
        self.assertIsNone(self._govde((0, 0), (0, 0)))


class GorunurlukTesti(unittest.TestCase):
    def test_gorunmeyen_eklem_none(self):
        n = bos_noktalar()
        g = [1.0] * 33
        g[27] = 0.1  # sol ayak bilegi gorunmuyor
        sonuc = hesapla_acilar(n, g)
        self.assertIsNone(sonuc["sol_diz"])
        self.assertIsNotNone(sonuc["sag_diz"])

    def test_gorunurluk_verilmezse_hepsi_hesaplanir(self):
        n = [(float(i), float(i * i % 7)) for i in range(33)]
        sonuc = hesapla_acilar(n)
        self.assertNotIn(None, [v for k, v in sonuc.items() if k != "govde_dikligi"])


class YumusatmaTesti(unittest.TestCase):
    def test_son_n_kare_ortalamasi(self):
        y = AciYumusatici(kare_sayisi=3)
        y.ekle({"sol_diz": 90})
        y.ekle({"sol_diz": 100})
        self.assertAlmostEqual(y.ekle({"sol_diz": 110})["sol_diz"], 100)
        # 4. kare gelince en eski (90) pencereden cikar: (100+110+120)/3
        self.assertAlmostEqual(y.ekle({"sol_diz": 120})["sol_diz"], 110)

    def test_none_atlanir(self):
        y = AciYumusatici(kare_sayisi=3)
        y.ekle({"sol_diz": 90})
        self.assertAlmostEqual(y.ekle({"sol_diz": None})["sol_diz"], 90)

    def test_hepsi_none_ise_none(self):
        y = AciYumusatici(kare_sayisi=2)
        self.assertIsNone(y.ekle({"sol_diz": None})["sol_diz"])


if __name__ == "__main__":
    unittest.main()
