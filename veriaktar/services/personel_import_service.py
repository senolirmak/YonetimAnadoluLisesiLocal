import warnings

import pandas as pd

from utility.services.main_services import EOkulVeriAktar
from veriaktar.services.default_path_service import DefaultPath

warnings.filterwarnings("ignore")


class PersonelIsleyici:
    def __init__(self, personel_path, uygulama_tarihi="2026/02/23"):
        self.uygulama_tarihi = uygulama_tarihi
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
        p_status = veri_aktar.save_yeni_veri_NobetPersonel(self.df_personel.copy())
        print(f"✅ {p_status['message']}")

    def calistir(self, personel_listesi="hz_personel_listesi.xlsx"):
        self.personel_data()
        self.kaydet(personel_listesi)
        self.veritabanina_yaz()
