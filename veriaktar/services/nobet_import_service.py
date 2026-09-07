import warnings

import pandas as pd

from utility.services.main_services import EOkulVeriAktar

warnings.filterwarnings("ignore")


class NobetIsleyici:
    """Haftalık nöbetçi listesi Excel dosyasını (..ÖğretmenNöbet.xlsx) içe aktarır.

    Yüklenen dosya diske yazılmadan, doğrudan bellekte (Django'nun UploadedFile
    nesnesinden) işlenir — ayrı bir "veri"/"hazırlık" dizinine ihtiyaç duymaz.
    """

    def __init__(self, dosya, uygulama_tarihi="2026/02/23", kullanici=None):
        self.uygulama_tarihi = uygulama_tarihi
        self.kullanici = kullanici
        self.dosya_adi = getattr(dosya, "name", "nobet.xlsx")

        df_nobet_raw = pd.read_excel(dosya, sheet_name="SABAH")
        df_nobet_raw = df_nobet_raw.iloc[3:, :4]
        df_nobet_raw.columns = ["nobetgun", "_", "adisoyadi", "nobetyeri"]
        self.df_nobet = df_nobet_raw

    def nobet_dosyasi_olustur_sabah(self):
        self.df_nobet = self.df_nobet.dropna(subset=["adisoyadi", "nobetyeri"], how="all")
        self.df_nobet["nobetgun"] = self.df_nobet["nobetgun"].ffill()

        gun_map = {
            "Pazartesi": "Monday",
            "Salı": "Tuesday",
            "Çarşamba": "Wednesday",
            "Perşembe": "Thursday",
            "Cuma": "Friday",
        }
        self.df_nobet["nobetgun"] = self.df_nobet["nobetgun"].replace(gun_map)
        self.df_nobet["uygulama_tarihi"] = pd.to_datetime(self.uygulama_tarihi)
        self.df_nobet = self.df_nobet[["adisoyadi", "nobetgun", "nobetyeri", "uygulama_tarihi"]]

        self.nobetci_veri = self.df_nobet.rename(
            columns={"adisoyadi": "nobetci", "nobetgun": "nobet_gun", "nobetyeri": "nobet_yeri"}
        )
        return self.nobetci_veri

    def nobetci_data(self):
        nobet_veri = self.nobet_dosyasi_olustur_sabah()
        return nobet_veri[["nobetci", "nobet_gun", "nobet_yeri", "uygulama_tarihi"]]

    def nobet_nobetgorevi_data(self):
        self.nobetci_veri = self.nobetci_data()
        self.nobetci_veri["nobetci"] = self.nobetci_veri["nobetci"].str.strip()

    def _nobet_yerlerini_sync_et(self):
        from nobet.models import NobetYerleri

        yerler = self.nobetci_veri["nobet_yeri"].dropna().str.strip().unique()
        for yer in yerler:
            if yer:
                NobetYerleri.objects.get_or_create(ad=yer)

    def veritabanina_yaz(self):
        self._nobet_yerlerini_sync_et()
        veri_aktar = EOkulVeriAktar()
        return veri_aktar.save_yeni_veri_NobetGorevi(self.nobetci_veri.copy())

    def calistir(self):
        self.nobet_nobetgorevi_data()
        status = self.veritabanina_yaz()
        self._aktar_gecmisi_kaydet(status)
        return status

    def _aktar_gecmisi_kaydet(self, status):
        from okul.models import VeriAktarimGecmisi

        uyarilar = []
        if status.get("otomatik_eklenen_isimler"):
            uyarilar.append(
                f"Otomatik oluşturulan personel: {', '.join(status['otomatik_eklenen_isimler'])}"
            )

        durum = "basarili"
        if status.get("errors"):
            durum = "kismi" if status.get("inserted") else "hatali"
        if uyarilar:
            durum = "kismi"

        uygulama_tarihi = None
        try:
            uygulama_tarihi = pd.to_datetime(self.uygulama_tarihi).date()
        except Exception:
            pass

        VeriAktarimGecmisi.objects.create(
            dosya_turu="nobet_listesi",
            dosya_adi=self.dosya_adi,
            uygulama_tarihi=uygulama_tarihi,
            kullanici=self.kullanici,
            kayit_sayisi=status.get("inserted", 0),
            hata_sayisi=status.get("errors", 0),
            otomatik_eklenen=status.get("otomatik_eklenen", 0),
            durum=durum,
            notlar="\n".join(uyarilar),
        )

        if durum != "hatali" and uygulama_tarihi:
            from okul.utils import set_aktif_tarih
            set_aktif_tarih("nobet_listesi", uygulama_tarihi)
