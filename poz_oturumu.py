"""Poz oturumu (T4): durum makinesi, tutus suresi, puan, mesaj sirasi ve kayit.

Her kare icin karsilastirma.karsilastir() sonucunu alir, rapordaki Sekil 10'a gore
durum degistirir ve sunucuya yazilacak durumu uretir.

Durumlar (rapor Sekil 10):
  hazirlik         oynatma ani henuz yok
  kadraj_kontrolu  gerekli eklemler gorunmuyor ("kadraja gir", hata mesaji yok, IG-08)
  poz_bekleniyor   kisi kadrajda ama anahtar pozda degil / pozu almak icin sure taniniyor
  duzeltme         hata var; mesajlar en buyuk farktan baslayarak sirayla verilir (IG-07)
  tutus            dogru durus; dogru gecen sure sayilir (IG-09)
  bitis            poz bitti (tamamlandi / sure doldu / atlandi), puan verildi

Kullanim:
    oturum = PozOturumu(profil, kayit_yolu="cikti/oturum.csv", kod="T01")
    durum = oturum.adim(time.monotonic(), karsilastir(canli, profil, t))
    sunucu.durum_guncelle(**durum)   # noktalar alani cagirana aittir

Mesaj METNI burada uretilmez (T5): hata_mesaji ve bitis_mesaji disaridan verilir;
varsayilanlar yalnizca akisi gormek icin geciciydir.
"""
import csv
import os
from datetime import datetime

HAZIRLIK = "hazirlik"
KADRAJ = "kadraj_kontrolu"
POZ_BEKLENIYOR = "poz_bekleniyor"
DUZELTME = "duzeltme"
TUTUS = "tutus"
BITIS = "bitis"

# --- Ayarlanabilir parametreler (rapor degerleri belirtmiyor; deneme ile ayarlanmali) ---
TUTUS_HEDEF_SN = 5.0       # FT-06: "dogru durus 5 sn korunur"
MESAJ_SURESI_SN = 3.0      # bir hata mesajinin ekranda kalma suresi (AG-02: 2 sn'de okunabilir)
ISINMA_SN = 2.0            # yeni pozun ilk saniyeleri: hata verilmez (FT-14: 2 sn geriden izleme)
KARAR_BEKLEME_SN = 0.5     # durum degisimi bu kadar surmeden uygulanmaz (titremeyi onler)
BITIS_GOSTERIM_SN = 4.0    # bitis mesaji ekranda bu kadar kalir
MAX_ADIM_SN = 1.0          # iki kare arasi bundan uzunsa (takilma) fazlasi sayilmaz

KADRAJ_MESAJI = "Kadraja gir"
CSV_SUTUNLARI = ["tarih", "kod", "poz", "sure_sn", "puan", "hata_sayisi", "sonuc", "iptal_edilen"]


def varsayilan_hata_mesaji(hata):
    """GECICI: gercek Turkce mesajlar T5'te uretilecek."""
    yon = "azalt" if hata["yon"] == "azalt" else "artır"
    return f"{hata['eklem']}: açıyı {yon}"


def varsayilan_bitis_mesaji(kayit):
    """GECICI: gercek mesaj T5'te."""
    if kayit["sonuc"] == "tamamlandi":
        return f"Tamam! Puan: {kayit['puan']}"
    if kayit["sonuc"] == "atlandi":
        return "Poz atlandı"
    return f"Poz bitti. Puan: {kayit['puan']}"


def puan_hesapla(dogru_sn, aktif_sn):
    """0-100. DOGRU DURUSTA gecen sure / degerlendirilen sure.

    Raporda formul tanimli degil (yalniz "puan verilmeli"); bu yuzden tek bir yerde
    durur, degistirmek kolay olsun. Degerlendirilen sure = duzeltme + tutus suresi;
    kadraja girme, isinma ve poz disi sure sayilmaz.
    """
    if aktif_sn <= 0:
        return 0
    return round(100 * min(1.0, dogru_sn / aktif_sn))


class PozOturumu:
    def __init__(self, profil, kayit_yolu=None, kod="", hata_mesaji=varsayilan_hata_mesaji,
                 kadraj_mesaji=KADRAJ_MESAJI, bitis_mesaji=varsayilan_bitis_mesaji,
                 tutus_hedef_sn=TUTUS_HEDEF_SN, mesaj_suresi_sn=MESAJ_SURESI_SN,
                 isinma_sn=ISINMA_SN, karar_bekleme_sn=KARAR_BEKLEME_SN, tarih_fn=None):
        self.profil = profil
        self.kayit_yolu = kayit_yolu
        self.kod = kod  # takma kod; kisisel ad tutulmaz (VG-04)
        self._hata_mesaji = hata_mesaji
        self._kadraj_mesaji = kadraj_mesaji
        self._bitis_mesaji = bitis_mesaji
        self._tutus_hedef_sn = tutus_hedef_sn
        self._mesaj_suresi_sn = mesaj_suresi_sn
        self._isinma_sn = isinma_sn
        self._karar_bekleme_sn = karar_bekleme_sn
        self._tarih_fn = tarih_fn or (lambda: datetime.now().isoformat(timespec="seconds"))

        self.durum = HAZIRLIK
        self.kayitlar = []

        self._son_zaman = None
        self._poz = None              # etkin anahtar poz sirasi (None = yok)
        self._bitirilen_poz = None    # tamamlanip kilitlenen poz (ayni pozda yeniden baslamasin)
        self._etkin = None            # titremesiz (kararli) kosul
        self._bekleyen = None
        self._bekleyen_bas = 0.0
        self._bitis_zamani = None
        self._poz_sifirla()
        self._puan = 0
        self._poz_adi = ""
        self._hedef_sn = 0.0
        self._mesaj_metni = ""

    # ------------------------------------------------------------------ yardimcilar
    def _poz_sifirla(self):
        self._giris = 0.0
        self._dogru_sn = 0.0
        self._aktif_sn = 0.0
        self._gorulen = set()         # pozda hatali bulunan tum eklemler
        self._soylenen = set()        # pozda mesaji verilen eklemler
        self._tur_soylenen = set()    # mevcut turda mesaji verilenler
        self._mesaj = None            # {"eklem", "baslangic"} o an gosterilen hata mesaji
        self._sira = 0
        self._toplam = 0
        self._hatali = []
        self._son_hata_adlari = set()

    def _poz_adi_yap(self, sira):
        video = os.path.basename(self.profil.get("video", "video"))
        return f"{video}#{sira + 1}"

    def _kararli(self, ham, zaman):
        """Kosul ancak karar_bekleme_sn boyunca surerse etkin olur (ilk kosul hemen)."""
        if self._etkin is None or self._karar_bekleme_sn <= 0:
            self._etkin, self._bekleyen = ham, None
        elif ham == self._etkin:
            self._bekleyen = None
        else:
            if ham != self._bekleyen:
                self._bekleyen, self._bekleyen_bas = ham, zaman
            if zaman - self._bekleyen_bas >= self._karar_bekleme_sn:
                self._etkin, self._bekleyen = ham, None
        return self._etkin

    def _basla(self, sira, zaman):
        self._poz_sifirla()
        self._poz = sira
        self._giris = zaman
        poz = self.profil["anahtar_pozlar"][sira]
        uzunluk = poz["bitis_sn"] - poz["baslangic_sn"]
        # Isinma suresi dusulur ki hedefe ulasilabilsin
        self._hedef_sn = round(min(self._tutus_hedef_sn, max(1.0, uzunluk - self._isinma_sn)), 1)
        self._poz_adi = self._poz_adi_yap(sira)
        self._puan = 0
        self._mesaj_metni = ""
        self._bitis_zamani = None

    def _bitir(self, sonuc, zaman, kilitle=False):
        """Pozu kapatir, puani hesaplar, kaydi yazar."""
        if self._poz is None:
            return
        if sonuc == "sure_doldu" and self._aktif_sn <= 0:
            sonuc = "atlandi"
        puan = puan_hesapla(self._dogru_sn, self._aktif_sn)
        # IG-21: poz bitince soylenmemis hatalar iptal edilir, ozette gosterilir
        iptal = sorted(self._son_hata_adlari - self._soylenen) if sonuc != "tamamlandi" else []
        kayit = {
            "tarih": self._tarih_fn(),
            "kod": self.kod,
            "poz": self._poz_adi,
            "sure_sn": round(zaman - self._giris, 1),
            "puan": puan,
            "hata_sayisi": len(self._gorulen),
            "sonuc": sonuc,
            "iptal_edilen": ";".join(iptal),
        }
        self.kayitlar.append(kayit)
        self._kaydet(kayit)

        self._puan = puan
        self.durum = BITIS
        self._mesaj_metni = self._bitis_mesaji(kayit)
        self._mesaj = None
        self._hatali = []
        self._sira = self._toplam = 0
        self._bitis_zamani = zaman
        if kilitle:
            self._bitirilen_poz = self._poz
        self._poz = None

    def _kaydet(self, kayit):
        if not self.kayit_yolu:
            return
        yeni = not os.path.isfile(self.kayit_yolu)
        os.makedirs(os.path.dirname(self.kayit_yolu) or ".", exist_ok=True)
        with open(self.kayit_yolu, "a", newline="", encoding="utf-8") as f:
            yazici = csv.DictWriter(f, fieldnames=CSV_SUTUNLARI)
            if yeni:
                yazici.writeheader()
            yazici.writerow(kayit)

    def _bitis_suresi_doldu_mu(self, zaman):
        if self.durum == BITIS and self._bitis_zamani is not None \
                and zaman - self._bitis_zamani >= BITIS_GOSTERIM_SN:
            self.durum = POZ_BEKLENIYOR
            self._mesaj_metni = ""

    def _hata_mesaj_adimi(self, zaman, hatalar):
        """IG-07: en buyuk farktan sirayla, ust uste binmeden; her mesajdan sonra
        siralama yenilenir, duzelen hata soylenmez."""
        if not hatalar:
            return  # titreme bekleme suresinde bu karede hata yok: mevcut mesaj korunur
        adlar = {h["eklem"] for h in hatalar}
        self._gorulen |= adlar

        m = self._mesaj
        if m and (m["eklem"] not in adlar or zaman - m["baslangic"] >= self._mesaj_suresi_sn):
            m = None  # sure doldu ya da o hata duzeldi

        if m is None:
            kalan = [h for h in hatalar if h["eklem"] not in self._tur_soylenen]
            if not kalan:             # tur bitti: duzelmeyenler en bastan tekrar
                self._tur_soylenen = set()
                kalan = hatalar
            sonraki = kalan[0]
            self._tur_soylenen.add(sonraki["eklem"])
            self._soylenen.add(sonraki["eklem"])
            m = {"eklem": sonraki["eklem"], "baslangic": zaman}
            self._mesaj_metni = self._hata_mesaji(sonraki)
        self._mesaj = m
        self._sira = len(adlar & self._tur_soylenen)
        self._toplam = len(hatalar)
        self._hatali = sorted(adlar)

    def _mesaji_birak(self):
        self._mesaj = None
        self._tur_soylenen = set()
        self._sira = self._toplam = 0
        self._hatali = []

    # ------------------------------------------------------------------ ana akis
    def adim(self, zaman, sonuc):
        """Bir karelik karsilastirma sonucunu isler; sunucuya yazilacak durumu dondurur.

        zaman: monoton saat (sn). sonuc: karsilastirma.karsilastir() ciktisi.
        """
        dt = 0.0 if self._son_zaman is None else min(max(zaman - self._son_zaman, 0.0), MAX_ADIM_SN)
        self._son_zaman = zaman
        ham = sonuc["durum"]

        if ham == "oynatma_yok":
            if self._poz is None and self.durum != BITIS:
                self.durum = HAZIRLIK
            self._bitis_suresi_doldu_mu(zaman)
            return self._cikti()

        if ham == "gecis":                      # hicbir anahtar pozun icinde degil (IG-20)
            self._bitir("sure_doldu", zaman)
            self._bitirilen_poz = None
            self._etkin = self._bekleyen = None
            if self.durum != BITIS:             # bitis mesaji suresi dolana kadar ekranda kalir
                self.durum = POZ_BEKLENIYOR
            self._bitis_suresi_doldu_mu(zaman)
            return self._cikti()

        sira = sonuc["anahtar_poz"]
        if sira == self._bitirilen_poz:         # tamamlanan poz: video ayni pozdayken yeniden baslama
            self._bitis_suresi_doldu_mu(zaman)
            return self._cikti()
        if self._poz is not None and sira != self._poz:   # video baska pozlara gecti / sarildi
            self._bitir("sure_doldu", zaman)
            self._etkin = self._bekleyen = None
            dt = 0.0
        self._bitirilen_poz = None
        if self._poz is None:
            self._basla(sira, zaman)
            dt = 0.0

        self._son_hata_adlari = {h["eklem"] for h in sonuc.get("hatalar", [])}
        kosul = self._kararli(ham, zaman)
        isinmada = (zaman - self._giris) < self._isinma_sn

        if kosul == "kadraja_gir":              # IG-08: hata yerine uyari, sure sayilmaz
            self.durum = KADRAJ
            self._mesaj_metni = self._kadraj_mesaji
            self._mesaji_birak()
        elif kosul == "poz_yok":
            self.durum = POZ_BEKLENIYOR
            self._mesaj_metni = ""
            self._mesaji_birak()
        elif kosul == "dogru":
            self.durum = TUTUS
            self._mesaj_metni = ""
            self._mesaji_birak()
            self._dogru_sn += dt
            self._aktif_sn += dt
        else:                                   # "hata"
            if isinmada:                        # FT-14: kullanici geriden izliyor olabilir
                self.durum = POZ_BEKLENIYOR
                self._mesaj_metni = ""
                self._mesaji_birak()
            else:
                self.durum = DUZELTME
                self._aktif_sn += dt
                self._hata_mesaj_adimi(zaman, sonuc["hatalar"])

        if self._dogru_sn >= self._hedef_sn:    # sure doldu: puan hesaplanir, kayit yapilir
            self._bitir("tamamlandi", zaman, kilitle=True)
            return self._cikti()

        if self.durum in (TUTUS, DUZELTME, KADRAJ, POZ_BEKLENIYOR):
            self._puan = puan_hesapla(self._dogru_sn, self._aktif_sn)
        return self._cikti()

    def _cikti(self):
        """Sunucudaki BOS_DURUM alanlari (noktalar haric; onu cagiran ekler)."""
        return {
            "poz": self._poz_adi,
            "durum": self.durum,
            "mesaj": self._mesaj_metni,
            "sira": self._sira,
            "toplam_hata": self._toplam,
            "hatali_eklemler": list(self._hatali),
            "tutus_sn": round(self._dogru_sn, 1),
            "hedef_sn": self._hedef_sn,
            "puan": self._puan,
        }

    def ozet(self):
        """Oturum sonu ozeti: poz kayitlari ve iptal edilen mesajlar (IG-21)."""
        puanlar = [k["puan"] for k in self.kayitlar]
        return {
            "kayitlar": list(self.kayitlar),
            "poz_sayisi": len(self.kayitlar),
            "ortalama_puan": round(sum(puanlar) / len(puanlar)) if puanlar else 0,
            "iptal_edilen": [(k["poz"], k["iptal_edilen"].split(";")) for k in self.kayitlar
                             if k["iptal_edilen"]],
        }
