# -*- coding: utf-8 -*-
"""
VeriImportService – Adim 0 + Adim 1

Adim 0 (Temel modeller):
    - SinifSube  ← e-Okul öğrenci listesi (sınıf/şube çiftleri)
    - DersHavuzu ← e-Okul haftalık ders programı (tekil ders adı havuzu)
    CASCADE: SinifSube.delete() → Ogrenci + DersProgram temizlenir
    CASCADE: DersHavuzu.delete() → DersProgram temizlenir

Adim 1 (Bağımlı modeller):
    - DersProgram ← haftalık program + SinifSube FK + DersHavuzu FK
    - Ogrenci     ← öğrenci listesi + SinifSube FK
"""

import re
import pandas as pd

from ortaksinav_engine.services.base import BaseService
from ortaksinav_engine.utils import iter_rows

_TRGUN_DICT = {
    "PAZARTESİ": "Monday",
    "SALI": "Tuesday",
    "ÇARSAMBA": "Wednesday",
    "PERŞEMBE": "Thursday",
    "CUMA": "Friday",
}

_DERSNOSU = {
    1: "08:00", 2: "08:50", 3: "09:40", 4: "10:30",
    5: "11:20", 6: "12:10", 7: "13:35", 8: "14:25",
}


class VeriImportService(BaseService):
    """e-Okul dosyalarindan veri okuyup DB'ye kaydeden servis."""

    # ------------------------------------------------------------------
    # Adim 0 – Temel Modeller: SinifSube + DersHavuzu
    # ------------------------------------------------------------------

    def temel_verileri_olustur(self):
        self.log("\nTemel veriler guncelleniyor (SinifSube + DersHavuzu)...")

        from sinav.models import SinifSube, DersHavuzu

        # 1) SinifSube – öğrenci listesinden sınıf/şube çiftlerini al
        df_ogrenci = self._extract_student_data(self.config["eokul_ogrenci_dosya"])
        df_temiz = df_ogrenci.dropna(subset=["sinif", "sube"])

        sinif_sube_df = (
            df_temiz[["sinif", "sube"]]
            .drop_duplicates()
            .sort_values(["sinif", "sube"])
        )

        # Sadece DB'de olmayan sinifsube ciftlerini ekle
        mevcut_ss = set(SinifSube.objects.values_list("sinif", "sube"))
        yeni_ss = [
            SinifSube(
                sinif=int(row.sinif),
                sube=str(row.sube),
                sinifsube=f"{int(row.sinif)}/{str(row.sube)}",
                salon=f"Salon {int(row.sinif)}/{str(row.sube)}",
            )
            for row in sinif_sube_df.itertuples(index=False)
            if (int(row.sinif), str(row.sube)) not in mevcut_ss
        ]
        if yeni_ss:
            SinifSube.objects.bulk_create(yeni_ss)
            self.log(f"  {len(yeni_ss)} yeni sinif/sube eklendi.")
        else:
            self.log(f"  SinifSube degismedi, {len(mevcut_ss)} kayit korundu.")

        # 2) DersHavuzu – haftalık programdan tekil ders adlarını al
        sinif_bilgileri = self._sinif_bilgileri_from_df(df_temiz)
        program_df = self._parse_haftalik_program(sinif_bilgileri)
        tekil_dersler = program_df["ders_adi"].dropna().unique()

        # Sadece DB'de olmayan ders adlarini ekle
        mevcut_dh = set(DersHavuzu.objects.values_list("ders_adi", flat=True))
        yeni_dh = [
            DersHavuzu(ders_adi=str(d).strip())
            for d in sorted(tekil_dersler)
            if str(d).strip() and str(d).strip() not in mevcut_dh
        ]
        if yeni_dh:
            DersHavuzu.objects.bulk_create(yeni_dh)
            self.log(f"  {len(yeni_dh)} yeni ders eklendi.")
        else:
            self.log(f"  DersHavuzu degismedi, {DersHavuzu.objects.count()} kayit korundu.")

    def fark_hesapla(self):
        """
        DB'ye yazmadan yeni SinifSube ve DersHavuzu setlerini hesaplar.
        Donus: (sinifsube_set, dershavuzu_set)
          sinifsube_set : {(sinif_int, sube_str), ...}
          dershavuzu_set: {ders_adi_str, ...}
        """
        df_ogrenci = self._extract_student_data(self.config["eokul_ogrenci_dosya"])
        df_temiz = df_ogrenci.dropna(subset=["sinif", "sube"])

        sinif_sube_df = (
            df_temiz[["sinif", "sube"]]
            .drop_duplicates()
            .sort_values(["sinif", "sube"])
        )
        yeni_ss = {(int(r.sinif), str(r.sube)) for r in sinif_sube_df.itertuples(index=False)}

        sinif_bilgileri = self._sinif_bilgileri_from_df(df_temiz)
        program_df = self._parse_haftalik_program(sinif_bilgileri)
        tekil_dersler = program_df["ders_adi"].dropna().unique()
        yeni_dh = {str(d).strip() for d in tekil_dersler if str(d).strip()}

        return yeni_ss, yeni_dh

    # ------------------------------------------------------------------
    # Adim 1 – Bağımlı Modeller: DersProgram + Ogrenci (sınav bazlı)
    # ------------------------------------------------------------------

    def verileri_aktar(self, sinav):
        """
        DersProgram ve Ogrenci kayitlarini sinav bazli olusturur.
        sinav: SinavBilgisi ornegi (zorunlu).
        """
        if sinav is None:
            raise RuntimeError("verileri_aktar: sinav parametresi zorunludur.")

        self.log("\nVeriler aktariliyor (DersProgram + Ogrenci)...")

        from sinav.models import DersProgram, DersHavuzu, SinifSube, Ogrenci

        # Bu sinava ait onceki kayitlari temizle
        DersProgram.objects.filter(sinav=sinav).delete()
        Ogrenci.objects.filter(sinav=sinav).delete()

        # FK haritalari – temel_verileri_olustur tamamlanmis olmali
        ders_map = {dh.ders_adi: dh for dh in DersHavuzu.objects.all()}
        ss_map   = {(ss.sinif, ss.sube): ss for ss in SinifSube.objects.all()}

        if not ders_map:
            raise RuntimeError("verileri_aktar: DersHavuzu bos. Once temel verileri olusturun.")
        if not ss_map:
            raise RuntimeError("verileri_aktar: SinifSube bos. Once temel verileri olusturun.")

        # 1) DersProgram – haftalık program + SinifSube FK + DersHavuzu FK
        uygulama_tarihi = self.config.get("uygulama_tarihi", "2026-02-23")
        uygulama_date   = pd.to_datetime(uygulama_tarihi).date()
        saat_to_ders    = {v: k for k, v in _DERSNOSU.items()}

        sinif_bilgileri = self._sinif_bilgileri_from_ss_map(ss_map)
        program_df = self._parse_haftalik_program(sinif_bilgileri)
        program_df["ders_saati"]     = program_df["giris_saat"].map(saat_to_ders)
        program_df["ders_saati_adi"] = program_df["ders_saati"].astype(str) + ". Ders"

        DersProgram.objects.bulk_create([
            DersProgram(
                sinav         = sinav,
                giris_saat    = row.giris_saat,
                cikis_saat    = row.cikis_saat,
                gun           = row.gun,
                ders          = ders_map.get(str(row.ders_adi).strip()),
                ders_ogretmeni= row.ders_ogretmeni,
                sinif_sube    = ss_map.get((int(row.sinif), str(row.sube))),
                ders_saati    = int(row.ders_saati) if pd.notna(row.ders_saati) else None,
                ders_saati_adi= str(row.ders_saati_adi),
                uygulama_tarihi= uygulama_date,
            )
            for row in program_df.itertuples(index=False)
        ])
        self.log(f"  {len(program_df)} DersProgram kaydi olusturuldu.")

        # 2) Ogrenci – öğrenci listesi + SinifSube FK
        df_ogrenci = self._extract_student_data(self.config["eokul_ogrenci_dosya"])
        df_temiz   = df_ogrenci.dropna(subset=["sinif", "sube"])

        Ogrenci.objects.bulk_create([
            Ogrenci(
                sinav     = sinav,
                okulno    = str(int(row.okulno)) if pd.notna(row.okulno) else "",
                adi       = str(row.adi),
                soyadi    = str(row.soyadi),
                cinsiyet  = str(row.cinsiyet) if pd.notna(row.cinsiyet) else "",
                sinif_sube= ss_map.get((int(row.sinif), str(row.sube))),
            )
            for row in df_temiz.itertuples(index=False)
        ])
        self.log(f"  {len(df_temiz)} ogrenci Ogrenci'ye kaydedildi.")

    # ------------------------------------------------------------------
    # Yardımcı: sinif_bilgileri sözlüğü oluşturma
    # ------------------------------------------------------------------

    @staticmethod
    def _sinif_bilgileri_from_df(df_temiz) -> dict:
        """Öğrenci DataFrame'inden {sinif: [sube, ...]} sözlüğü üretir."""
        sinif_bilgileri: dict = {}
        for row in (
            df_temiz.dropna(subset=["sinif", "sube"])
            .drop_duplicates(subset=["sinif", "sube"])
            .sort_values(["sinif", "sube"])
            .itertuples(index=False)
        ):
            s = int(row.sinif)
            sinif_bilgileri.setdefault(s, [])
            if str(row.sube) not in sinif_bilgileri[s]:
                sinif_bilgileri[s].append(str(row.sube))
        return sinif_bilgileri

    @staticmethod
    def _sinif_bilgileri_from_ss_map(ss_map: dict) -> dict:
        """SinifSube FK haritasından {sinif: [sube, ...]} sözlüğü üretir."""
        sinif_bilgileri: dict = {}
        for (sinif, sube) in sorted(ss_map.keys()):
            sinif_bilgileri.setdefault(sinif, [])
            sinif_bilgileri[sinif].append(str(sube))
        return sinif_bilgileri

    # ------------------------------------------------------------------
    # Yardımcı: haftalık program Excel parse
    # ------------------------------------------------------------------

    def _parse_haftalik_program(self, sinif_bilgileri: dict) -> pd.DataFrame:
        """
        Haftalık ders programı XLS/XLSX dosyasını parse eder.
        sinif_bilgileri: {sinif: [sube, ...]} – blok sıralaması için gerekli.
        Döndürür: DataFrame(giris_saat, cikis_saat, gun, ders_adi, ders_ogretmeni, sinif, sube, subeadi)
        """
        file_path = self.config["eokul_haftalik_program_dosya"]

        tum_siniflar = [
            (sinif, sube, f"{sinif} / {sube}")
            for sinif, subeler in sorted(sinif_bilgileri.items())
            for sube in subeler
        ]

        engine  = "xlrd" if str(file_path).lower().endswith(".xls") else None
        df_raw  = pd.read_excel(file_path, header=None, skiprows=6, engine=engine)
        mask    = df_raw.iloc[:, 0:24].notna().any(axis=1)
        df      = df_raw.loc[mask].reset_index(drop=True)

        header = []
        for c in df.iloc[0]:
            cs = str(c).strip().upper() if c is not None and str(c).strip() not in ("", "NAN") else None
            header.append(cs)
        df.columns = header
        df = df.iloc[1:].reset_index(drop=True)

        blok_boyutu  = 8
        toplam_sube  = min(len(df) // blok_boyutu, len(tum_siniflar))
        new_data: list = []

        for sube_index in range(toplam_sube):
            start   = sube_index * blok_boyutu
            sube_df = df.iloc[start: start + blok_boyutu]
            sinif, sube, subeadi = tum_siniflar[sube_index]

            for _, row in sube_df.iterrows():
                if pd.isna(row.iloc[1]) or "-" not in str(row.iloc[1]):
                    continue
                giris_saat, cikis_saat = [s.strip() for s in str(row.iloc[1]).split("-", 1)]

                for col_index in range(2, len(df.columns)):
                    gun_adi = df.columns[col_index]
                    if not gun_adi or gun_adi not in _TRGUN_DICT:
                        continue
                    val = row.iloc[col_index]
                    if pd.isna(val):
                        continue
                    ders_adi, ogretmen_str = self._split_ders_cell(val)
                    if not ders_adi or not ogretmen_str:
                        continue
                    for ogretmen in [o.strip() for o in ogretmen_str.split(",") if o.strip()]:
                        new_data.append([
                            giris_saat, cikis_saat,
                            _TRGUN_DICT[gun_adi],
                            ders_adi, ogretmen,
                            sinif, sube, subeadi,
                        ])

        return pd.DataFrame(new_data, columns=[
            "giris_saat", "cikis_saat", "gun", "ders_adi",
            "ders_ogretmeni", "sinif", "sube", "subeadi",
        ])

    # ------------------------------------------------------------------
    # Yardımcı: öğrenci listesi XLS parse
    # ------------------------------------------------------------------

    def _extract_student_data(self, file_path) -> pd.DataFrame:
        all_students = []
        current_class = ""

        for row in iter_rows(file_path):
            row_str = " ".join(str(cell) if cell is not None else "" for cell in row)

            match = re.search(r"(\d+\.\s*Sınıf\s*/\s*[A-ZÇĞİÖŞÜ]\s*Şubesi)", row_str)
            if match:
                current_class = match.group(1).strip()
                continue

            if isinstance(row[0], (int, float)) and row[0] > 0:
                sinif, sube, sinifsube = self._format_sinif(current_class)
                all_students.append({
                    "okulno":    row[1],
                    "adi":       row[4],
                    "soyadi":    row[8],
                    "cinsiyet":  row[12],
                    "sinifsube": sinifsube,
                    "sube":      sube,
                    "sinif":     int(sinif) if sinif else None,
                })

        df = pd.DataFrame(all_students)
        return df.dropna(subset=["adi"])

    @staticmethod
    def _format_sinif(sinif_metni):
        match = re.search(r"(\d+)\.\s*Sınıf\s*/\s*(\w+)\s*Şubesi", sinif_metni)
        if match:
            return match.group(1), match.group(2), f"{match.group(1)}/{match.group(2)}"
        return "", "", sinif_metni

    @staticmethod
    def _split_ders_cell(cell_value):
        text = str(cell_value).strip()
        if not text or text.upper() == "NAN":
            return None, None
        parts = [p.strip() for p in text.split("\n") if p.strip()]
        ders_adi = None
        ogretmen = None
        if parts:
            if parts[0].strip().upper() != "SEÇMELİ DERS":
                ders_adi = parts[0]
        if len(parts) >= 2:
            ikinci = parts[1]
            if "-" in ikinci:
                ogretmen_kisim, ders_kisim = [p.strip() for p in ikinci.split("-", 1)]
                ders_adi = ders_kisim
                ogretmen = ogretmen_kisim
            else:
                ogretmen = ikinci
        return ders_adi, ogretmen
