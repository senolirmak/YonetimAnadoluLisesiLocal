import warnings

import pandas as pd

from utility.services.main_services import EOkulVeriAktar
from veriaktar.services.default_path_service import DefaultPath

warnings.filterwarnings("ignore")


class PersonelIsleyici:
    def __init__(self, personel_path, uygulama_tarihi="2026/02/23", kullanici=None):
        self.uygulama_tarihi = uygulama_tarihi
        self.kullanici = kullanici
        self.Default_Path = DefaultPath()
        self.personel_path = self.Default_Path.resolve_veri_path(personel_path)
        self.df_personel = pd.read_excel(self.personel_path, sheet_name="Sayfa1")

    def personel_data(self):
        nobet_ogretmen_sutun_name = {
            "adisoyadi": "adi_soyadi",
            "gorev": "gorev_tipi",
            "brans": "brans",
        }
        nobet_ogretmen_nobeti_yok = ["Müdür", "Müdür Yardımcısı", "Ücretli Öğretmen"]
        self.df_personel = self.df_personel.rename(columns=nobet_ogretmen_sutun_name)
        self.df_personel["nobeti_var"] = True
        self.df_personel.loc[
            self.df_personel["gorev_tipi"].isin(nobet_ogretmen_nobeti_yok), "nobeti_var"
        ] = False
        self.df_personel["adi_soyadi"] = self.df_personel["adi_soyadi"].str.strip()
        self.df_personel = self.df_personel.sort_values(by="adi_soyadi").reset_index(drop=True)
        self.df_personel["sabit_nobet"] = False
        self.df_personel["uygulama_tarihi"] = pd.to_datetime(self.uygulama_tarihi)

    def kaydet(self, personel_listesi):
        personel_listesi = self.Default_Path.resolve_hazirlik_path(personel_listesi)
        personel_listesi.parent.mkdir(parents=True, exist_ok=True)
        self.df_personel.to_excel(personel_listesi, index=False)

    def veritabanina_yaz(self):
        veri_aktar = EOkulVeriAktar()
        return veri_aktar.save_yeni_veri_NobetPersonel(self.df_personel.copy())

    def _aktar_gecmisi_kaydet(self, status):
        from okul.models import VeriAktarimGecmisi

        import pandas as pd
        uygulama_tarihi = None
        try:
            uygulama_tarihi = pd.to_datetime(self.uygulama_tarihi).date()
        except Exception:
            pass

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

        VeriAktarimGecmisi.objects.create(
            dosya_turu="personel_listesi",
            dosya_adi=self.personel_path.name,
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
            set_aktif_tarih("personel_listesi", uygulama_tarihi)

    def calistir(self, personel_listesi="hz_personel_listesi.xlsx"):
        self.personel_data()
        self.kaydet(personel_listesi)
        status = self.veritabanina_yaz()
        self._aktar_gecmisi_kaydet(status)
        return status
