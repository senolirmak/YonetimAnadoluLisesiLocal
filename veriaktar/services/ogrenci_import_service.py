# -*- coding: utf-8 -*-
"""
OgrenciIsleyici – e-Okul OOG01001R020 formatındaki XLS dosyasından
öğrenci listesini okuyarak ogrenci.Ogrenci tablosuna yazar.

Format:
- Her sınıf grubunun başında (col0) çok satırlı başlık hücresi:
  "9. Sınıf / A Şubesi" veya "10. Sınıf / B Şubesi" vb.
- Öğrenci satırları: col0 = S.No (float > 0), col1 = okulno,
  col4 = adi, col8 = soyadi, col12 = cinsiyet
"""

import re
from datetime import date

import xlrd


class OgrenciIsleyici:
    SINIF_SUBE_RE = re.compile(
        r"(\d+)\.\s*S[iı]n[iı]f\s*/\s*([A-ZÇĞİÖŞÜa-züçğışö]+)\s*Şubesi",
        re.IGNORECASE,
    )

    def __init__(self, file_path):
        self.file_path = str(file_path)
        self._kayitlar = []

    # ------------------------------------------------------------------
    def parse(self) -> list:
        """XLS dosyasını okuyup {sinif, sube, okulno, adi, soyadi, cinsiyet}
        sözlüklerinden oluşan listeyi döner."""
        wb = xlrd.open_workbook(self.file_path)
        ws = wb.sheet_by_index(0)

        aktif_sinif = None
        aktif_sube = None
        sonuc = []

        for row_idx in range(ws.nrows):
            val0 = ws.cell_value(row_idx, 0)

            # Sınıf/şube başlık hücresi
            if isinstance(val0, str):
                eslesme = self.SINIF_SUBE_RE.search(val0)
                if eslesme:
                    aktif_sinif = int(eslesme.group(1))
                    aktif_sube = eslesme.group(2).upper().strip()
                continue

            # Öğrenci satırı: col0 float > 0 (S.No)
            if isinstance(val0, float) and val0 > 0 and aktif_sinif is not None:
                try:
                    okulno = str(ws.cell_value(row_idx, 1)).strip()
                    if okulno.endswith(".0"):
                        okulno = okulno[:-2]
                    adi = str(ws.cell_value(row_idx, 4)).strip().upper()
                    soyadi = str(ws.cell_value(row_idx, 8)).strip().upper()
                    cinsiyet_raw = str(ws.cell_value(row_idx, 12)).strip().lower()
                    cinsiyet = "E" if "erkek" in cinsiyet_raw else "K"

                    if not okulno or not adi or not soyadi:
                        continue

                    sonuc.append(
                        {
                            "sinif": aktif_sinif,
                            "sube": aktif_sube,
                            "okulno": okulno,
                            "adi": adi,
                            "soyadi": soyadi,
                            "cinsiyet": cinsiyet,
                        }
                    )
                except (IndexError, ValueError):
                    continue

        self._kayitlar = sonuc
        return sonuc

    # ------------------------------------------------------------------
    def veritabanina_yaz(self) -> dict:
        """parse() sonucunu ogrenci.Ogrenci tablosuna yazar.
        tckimlikno ve dogumtarihi eksik olduğu için yer tutucu değer kullanılır."""
        from ogrenci.models import Ogrenci

        yeni = 0
        guncellenen = 0
        hatali = 0

        for kayit in self._kayitlar:
            okulno = kayit["okulno"]
            tckimlikno_placeholder = okulno.zfill(11)
            try:
                obj, created = Ogrenci.objects.update_or_create(
                    okulno=okulno,
                    defaults={
                        "sinif": kayit["sinif"],
                        "sube": kayit["sube"],
                        "adi": kayit["adi"],
                        "soyadi": kayit["soyadi"],
                        "cinsiyet": kayit["cinsiyet"],
                        "tckimlikno": tckimlikno_placeholder,
                        "dogumtarihi": date(2000, 1, 1),
                    },
                )
                if created:
                    yeni += 1
                else:
                    guncellenen += 1
            except Exception:
                hatali += 1

        return {"yeni": yeni, "guncellenen": guncellenen, "hatali": hatali}

    # ------------------------------------------------------------------
    def calistir(self) -> dict:
        self.parse()
        return self.veritabanina_yaz()
