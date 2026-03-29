# -*- coding: utf-8 -*-
"""
DersAnalizService – SubeDers Guncelleme

DersProgram tablosundan sinif/sube/ders bazinda haftalik ders saatlerini
bellekte hesaplar; sinav yapilmayacak dersler filtrelenerek
SubeDers tablosuna yalnizca eksik kayitlar eklenir.
"""

import pandas as pd
from django.db import models

from ortaksinav_engine.config import SINAV_YAPILMAYACAK_DERSLER as _DEFAULT_SINAV_YAPILMAYACAK
from ortaksinav_engine.services.base import BaseService


class DersAnalizService(BaseService):
    """DersProgram'dan SubeDers'i guncelleyen servis."""

    def subeders_guncelle(self, sinav=None):
        self.log("\nSubeDers guncelleniyor...")
        from okul.models import SinifSube
        from dersprogrami.models import DersProgrami
        from okul.models import DersHavuzu
        from sinav.models import SubeDers

        # DersProgrami'nden sinif / sube / ders_adi verisi
        df = pd.DataFrame(
            DersProgrami.objects.values(
                ders_adi=models.F("ders__ders_adi"),
                sinif=models.F("sinif_sube__sinif"),
                sube=models.F("sinif_sube__sube"),
            )
        )
        if df.empty:
            raise RuntimeError("SubeDers: Haftalık ders programı boş. Veri aktarımı yapın.")

        df = df.dropna(subset=["ders_adi", "sinif", "sube"])
        if df.empty:
            raise RuntimeError(
                "SubeDers: Ders programında sınıf/şube bilgisi eksik. "
                "Veri aktarımını yeniden yapın."
            )

        df["ders_adi"] = df["ders_adi"].astype(str).str.strip()

        # Her (sinif, ders_adi) icin haftalik saat ve sube listesini bellekte hesapla
        sonuc_listesi = []
        for sinif in df["sinif"].unique():
            for ders in df["ders_adi"].unique():
                filtrelenmis = df[(df["sinif"] == sinif) & (df["ders_adi"] == ders)]
                if filtrelenmis.empty:
                    continue
                subeler = filtrelenmis["sube"].unique()
                sonuc_listesi.append({
                    "sinif":   sinif,
                    "ders_adi": ders,
                    "subeler": subeler,
                })

        if not sonuc_listesi:
            raise RuntimeError("SubeDers: Hicbir ders bulunamadi. Veri aktarimini yeniden yapin.")

        # (sinif, ders_adi, sube) uclusune donustur
        satirlar = [
            {"Ders": r["ders_adi"], "Seviye": int(r["sinif"]), "Sube": str(sube)}
            for r in sonuc_listesi
            for sube in r["subeler"]
        ]
        df_filtreli_oncesi = pd.DataFrame(satirlar)

        # Sinav yapilmayacak dersleri filtrele
        from okul.models import DersHavuzu as _DH
        _db_yapilmayacak = list(_DH.objects.filter(sinav_yapilmayacak=True).values_list("ders_adi", flat=True))
        sinav_yapilmayacak = _db_yapilmayacak or self.config.get("SINAV_YAPILMAYACAK_DERSLER") or _DEFAULT_SINAV_YAPILMAYACAK
        sinav_yapilmayacak_upper = {d.upper().strip() for d in sinav_yapilmayacak}
        df_filtreli_oncesi["Ders_upper"] = df_filtreli_oncesi["Ders"].str.upper().str.strip()
        df_filtreli = df_filtreli_oncesi[
            ~df_filtreli_oncesi["Ders_upper"].isin(sinav_yapilmayacak_upper)
        ].drop(columns=["Ders_upper"])

        # FK lookup haritalari
        ders_map = {d.ders_adi: d for d in DersHavuzu.objects.all()}
        sube_map = {(ss.sinif, ss.sube): ss for ss in SinifSube.objects.all()}

        # Sinav yapilmayacak derslerin mevcut SubeDers kayitlarini kaldir
        # NOT: df_filtreli hesabından SONRA silme yapılır ki döngüde geri eklenmesın
        if sinav_yapilmayacak:
            silinen, _ = SubeDers.objects.filter(ders__ders_adi__in=sinav_yapilmayacak).delete()
            if silinen:
                self.log(f"{silinen} sinav-yapilmayacak ders/sube kaydi SubeDers'ten silindi.")

        # Mevcut kayitlari topla; yalnizca eksik olanlari ekle
        mevcut = set(SubeDers.objects.values_list("ders_id", "seviye", "sube_id"))

        kayitlar = []
        for row in df_filtreli.itertuples(index=False):
            ders_obj = ders_map.get(row.Ders)
            sube_obj = sube_map.get((int(row.Seviye), str(row.Sube)))
            if not ders_obj or not sube_obj:
                continue
            anahtar = (ders_obj.pk, int(row.Seviye), sube_obj.pk)
            if anahtar not in mevcut:
                kayitlar.append(SubeDers(ders=ders_obj, seviye=int(row.Seviye), sube=sube_obj))

        if kayitlar:
            SubeDers.objects.bulk_create(kayitlar, ignore_conflicts=True)
            self.log(f"{len(kayitlar)} yeni ders/sube kaydi DB'ye yazildi.")
        else:
            self.log("Yeni ders/sube kaydi yok; mevcut veriler korundu.")
