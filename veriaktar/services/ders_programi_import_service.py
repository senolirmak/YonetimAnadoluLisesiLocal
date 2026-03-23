import warnings
from collections import defaultdict
from pathlib import Path

import pandas as pd

from veriaktar.services.default_path_service import DefaultPath

warnings.filterwarnings("ignore")


class DersProgramiIsleyici:
    TRGUN_CHOICES = [
        ("PAZARTESİ", "Monday"),
        ("SALI", "Tuesday"),
        ("ÇARSAMBA", "Wednesday"),
        ("PERŞEMBE", "Thursday"),
        ("CUMA", "Friday"),
        ("CUMARTESİ", "Saturday"),
        ("PAZAR", "Sunday"),
    ]

    DERSNOSU = {
        1: "08:00",
        2: "08:50",
        3: "09:40",
        4: "10:30",
        5: "11:20",
        6: "12:10",
        7: "13:35",
        8: "14:25",
    }

    def __init__(self, file_path, uygulama_tarihi="2026/02/23"):
        self.uygulama_tarihi = uygulama_tarihi
        self.sinif_bilgileri = self.sinif_bilgilerini_getir()
        self.Default_Path = DefaultPath()
        self.file_path = self.Default_Path.resolve_veri_path(file_path)
        self.df = self.program_temizle(self.file_path)
        self.gunler = [v[1] for v in self.TRGUN_CHOICES][:5]
        self.processed_df: pd.DataFrame

    def sinif_bilgilerini_getir(self):
        from nobet.models import SinifSube

        sinif_bilgileri = defaultdict(list)
        for sinif, sube in SinifSube.objects.values_list("sinif", "sube"):
            sinif_bilgileri[sinif].append(sube)
        return dict(sinif_bilgileri)

    def program_temizle(self, file_path: Path):
        out_file = self.Default_Path.VERI_DIR / "program_temiz.xlsx"
        df = pd.read_excel(file_path, header=None, skiprows=6)
        kontrol_araligi = df.iloc[:, 0:24]
        mask_dolu = kontrol_araligi.notna().any(axis=1)
        df_temiz = df.loc[mask_dolu].reset_index(drop=True)
        df_temiz.to_excel(out_file, index=False, header=False)
        return pd.read_excel(out_file)

    def split_and_replace(self, row):
        if pd.isna(row):
            return None, None
        text = str(row).strip()
        if not text:
            return None, None
        parts = [p.strip() for p in text.split("\n") if p.strip()]
        ders_adi = None
        ogretmen_adlari = []
        if parts:
            if parts[0].strip().upper() == "SEÇMELİ DERS":
                pass
            else:
                ders_adi = parts[0]
        if len(parts) >= 2:
            ikinci_satir = parts[1]
            if "-" in ikinci_satir:
                ogretmen_kisim, ders_kisim = [p.strip() for p in ikinci_satir.split("-", 1)]
                ders_adi = ders_kisim
                ogretmen_adlari = [ad.strip() for ad in ogretmen_kisim.split(",") if ad.strip()]
            else:
                ogretmen_adlari = [ad.strip() for ad in ikinci_satir.split(",") if ad.strip()]
        ogretmen_adlari_str = ", ".join(ogretmen_adlari) if ogretmen_adlari else None
        return ders_adi, ogretmen_adlari_str

    def parse_program(self):
        trgun_dict = dict(self.TRGUN_CHOICES)
        new_data = []
        cleaned_cols = []
        for c in self.df.columns:
            cs = str(c).strip().upper()
            cleaned_cols.append(None if cs.startswith("UNNAMED") or cs == "NAN" else cs)
        self.df.columns = cleaned_cols

        tum_siniflar = [
            (sinif, sube, f"{sinif} / {sube}")
            for sinif, subeler in self.sinif_bilgileri.items()
            for sube in subeler
        ]

        blok_boyutu = 8
        toplam_satir = len(self.df)
        toplam_sube = min(toplam_satir // blok_boyutu, len(tum_siniflar))

        for sube_index in range(toplam_sube):
            start = sube_index * blok_boyutu
            sube_df = self.df.iloc[start : start + blok_boyutu]
            sinif, sube, subeadi = tum_siniflar[sube_index]

            for _, row in sube_df.iterrows():
                if pd.isna(row.iloc[1]) or "-" not in str(row.iloc[1]):
                    continue
                giris_saat, cikis_saat = [s.strip() for s in str(row.iloc[1]).split("-", 1)]
                for col_index in range(2, self.df.shape[1]):
                    gun_adi = self.df.columns[col_index]
                    if not gun_adi or gun_adi not in trgun_dict:
                        continue
                    value = row.iloc[col_index]
                    if pd.isna(value):
                        continue
                    ders_adi, ders_ogretmeni = self.split_and_replace(value)
                    if not ders_adi or not ders_ogretmeni:
                        continue
                    ogretmenler = [o.strip() for o in str(ders_ogretmeni).split(",") if o.strip()]
                    for ogretmen in ogretmenler:
                        new_data.append(
                            [
                                giris_saat,
                                cikis_saat,
                                trgun_dict[gun_adi],
                                ders_adi,
                                ogretmen,
                                sinif,
                                sube,
                                subeadi,
                            ]
                        )

        self.processed_df = pd.DataFrame(
            new_data,
            columns=[
                "giris_saat",
                "cikis_saat",
                "gun",
                "ders_adi",
                "ders_ogretmeni",
                "sinif",
                "sube",
                "subeadi",
            ],
        )

    def ekle_ders_saati(self):
        saat_to_ders = {v: k for k, v in self.DERSNOSU.items()}
        self.processed_df["ders_saati"] = self.processed_df["giris_saat"].map(saat_to_ders)
        self.processed_df["ders_ogretmeni"] = self.processed_df["ders_ogretmeni"].str.split(",")
        self.processed_df = self.processed_df.explode("ders_ogretmeni").reset_index(drop=True)
        self.processed_df["ders_ogretmeni"] = self.processed_df["ders_ogretmeni"].str.strip()
        self.processed_df["ders_saati_adi"] = self.processed_df["ders_saati"].astype(str) + ". Ders"
        self.processed_df["uygulama_tarihi"] = pd.to_datetime(self.uygulama_tarihi)

    def kaydet(self, program_listesi):
        program_listesi = self.Default_Path.resolve_hazirlik_path(program_listesi)
        program_listesi.parent.mkdir(parents=True, exist_ok=True)
        self.processed_df.to_excel(program_listesi, index=False)

    def veritabanina_yaz(self):
        from utility.services.main_services import EOkulVeriAktar

        if self.processed_df.empty:
            return

        veri_aktar = EOkulVeriAktar()
        status = veri_aktar.save_yeni_veri_NobetDersProgrami(self.processed_df.copy())
        print(f"✅ {status['message']}")
        if status.get("otomatik_eklenen_isimler"):
            print(f"⚠️  Otomatik oluşturulan personel: {', '.join(status['otomatik_eklenen_isimler'])}")

    def calistir(self, program_listesi="hz_duzenlenmis_program.xlsx"):
        self.parse_program()
        self.ekle_ders_saati()
        self.kaydet(program_listesi)
        self.veritabanina_yaz()
