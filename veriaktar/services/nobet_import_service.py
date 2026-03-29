import warnings

import pandas as pd

from utility.services.main_services import EOkulVeriAktar
from veriaktar.services.default_path_service import DefaultPath

warnings.filterwarnings("ignore")


class NobetIsleyici:
    def __init__(self, nobet_path, uygulama_tarihi="2026/02/23", kullanici=None):
        self.uygulama_tarihi = uygulama_tarihi
        self.kullanici = kullanici
        self.Default_Path = DefaultPath()
        self.nobet_path = self.Default_Path.resolve_veri_path(nobet_path)

        df_nobet_raw = pd.read_excel(self.nobet_path, sheet_name="SABAH")
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

    def kaydet(self, nobet_listesi):
        nobet_listesi = self.Default_Path.resolve_hazirlik_path(nobet_listesi)
        nobet_listesi.parent.mkdir(parents=True, exist_ok=True)
        self.nobetci_veri.to_excel(nobet_listesi, index=False)

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

    def calistir(self, nobet_listesi="hz_duzenlenmis_nobet.xlsx"):
        self.nobet_nobetgorevi_data()
        self.kaydet(nobet_listesi)
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

        import pandas as pd
        uygulama_tarihi = None
        try:
            uygulama_tarihi = pd.to_datetime(self.uygulama_tarihi).date()
        except Exception:
            pass

        VeriAktarimGecmisi.objects.create(
            dosya_turu="nobet_listesi",
            dosya_adi=self.nobet_path.name,
            uygulama_tarihi=uygulama_tarihi,
            kullanici=self.kullanici,
            kayit_sayisi=status.get("inserted", 0),
            hata_sayisi=status.get("errors", 0),
            otomatik_eklenen=status.get("otomatik_eklenen", 0),
            durum=durum,
            notlar="\n".join(uyarilar),
        )
