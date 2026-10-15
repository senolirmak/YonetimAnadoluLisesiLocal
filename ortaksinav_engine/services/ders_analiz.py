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

        # Yalnızca güncel (arşivlenmemiş, aktif tarihli) ders programı kullanılır;
        # eski programlardaki kapanmış şube/dersler takvime girmemeli.
        df = pd.DataFrame(
            DersProgrami.objects.aktif().values(
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

        # Ortak sınava katılacak seviyeler filtresi
        ortak_seviyeleri = self.config.get("ORTAK_SINAV_SEVIYELERI", [])
        if ortak_seviyeleri:
            df_filtreli = df_filtreli[df_filtreli["Seviye"].isin(ortak_seviyeleri)]
            self.log(f"Seviye filtresi uygulandı: {sorted(ortak_seviyeleri)} → {len(df_filtreli)} satır kaldı.")
            if df_filtreli.empty:
                raise RuntimeError(
                    f"SubeDers: Seçili seviyeler ({sorted(ortak_seviyeleri)}) için planlanacak ders bulunamadı. "
                    "Ders programı verilerini kontrol edin."
                )

        # Aktif eğitim yılında kapalı işaretli şubeler sınava girmez.
        from okul.models import SinifSubeYil
        from okul.utils import get_aktif_egitim_yili

        aktif_yil = get_aktif_egitim_yili()
        kapali_subeler = set(
            SinifSubeYil.objects.filter(egitim_yili=aktif_yil, acik=False).values_list(
                "sinif_sube_id", flat=True
            )
        ) if aktif_yil else set()

        # SubeDers, güncel ders programının birebir yansımasıdır: hedef küme
        # hesaplanır, eksikler eklenir, artık programda olmayanlar (kapanan
        # şube, kaldırılan ders, sınav yapılmayacak ders, seçilmeyen seviye) silinir.
        hedef = set()
        for row in df_filtreli.itertuples(index=False):
            ders_obj = ders_map.get(row.Ders)
            sube_obj = sube_map.get((int(row.Seviye), str(row.Sube)))
            if not ders_obj or not sube_obj or sube_obj.pk in kapali_subeler:
                continue
            hedef.add((ders_obj.pk, int(row.Seviye), sube_obj.pk))

        if not hedef:
            raise RuntimeError(
                "SubeDers: Güncel ders programında sınava girecek açık şube/ders bulunamadı."
            )

        mevcut = {
            (d, sev, s): pk
            for pk, d, sev, s in SubeDers.objects.values_list("pk", "ders_id", "seviye", "sube_id")
        }
        fazla_pk = [pk for anahtar, pk in mevcut.items() if anahtar not in hedef]
        if fazla_pk:
            SubeDers.objects.filter(pk__in=fazla_pk).delete()
            self.log(f"{len(fazla_pk)} güncel programda olmayan ders/şube kaydı SubeDers'ten silindi.")

        kayitlar = [
            SubeDers(ders_id=d, seviye=sev, sube_id=s)
            for d, sev, s in hedef - mevcut.keys()
        ]
        if kayitlar:
            SubeDers.objects.bulk_create(kayitlar, ignore_conflicts=True)
            self.log(f"{len(kayitlar)} yeni ders/şube kaydı DB'ye yazıldı.")
        if not fazla_pk and not kayitlar:
            self.log("SubeDers güncel; değişiklik yok.")
