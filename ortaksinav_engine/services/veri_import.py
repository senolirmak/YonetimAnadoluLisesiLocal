# -*- coding: utf-8 -*-
"""
VeriImportService – DB-first veri doğrulama ve DersHavuzu senkronizasyonu.

Adim 0 (temel_verileri_olustur):
    - DersHavuzu ← dersprogrami.DersProgrami.ders_adi

Adim 1 (verileri_aktar):
    - Öğrenci ve ders programı verilerinin varlığını doğrular.
    - Kaynak: ogrenci.Ogrenci + dersprogrami.DersProgrami
"""

from ortaksinav_engine.services.base import BaseService


class VeriImportService(BaseService):
    """DB kaynaklarından DersHavuzu'nu senkronize eden servis."""

    # ------------------------------------------------------------------
    # Adim 0 – DersHavuzu: DersProgrami'nden güncelle
    # ------------------------------------------------------------------

    def temel_verileri_olustur(self):
        self.log("\nTemel veriler güncelleniyor (DersHavuzu)...")

        from dersprogrami.models import DersProgrami
        from okul.models import DersHavuzu

        tekil_dersler = {
            d.strip()
            for d in DersProgrami.objects.values_list("ders__ders_adi", flat=True).distinct()
            if d and d.strip()
        }
        mevcut_dh = set(DersHavuzu.objects.values_list("ders_adi", flat=True))
        yeni_dh = [
            DersHavuzu(ders_adi=d)
            for d in sorted(tekil_dersler)
            if d not in mevcut_dh
        ]
        if yeni_dh:
            DersHavuzu.objects.bulk_create(yeni_dh)
            self.log(f"  {len(yeni_dh)} yeni ders eklendi.")
        else:
            self.log(f"  DersHavuzu güncel, {DersHavuzu.objects.count()} kayıt korundu.")

    def fark_hesapla(self):
        """
        Mevcut SinifSube ve DersHavuzu setlerini döndürür.
        DB-first modelde fark yoktur; geriye dönük uyumluluk için korundu.
        """
        from okul.models import SinifSube
        from okul.models import DersHavuzu
        mevcut_ss = set(SinifSube.objects.values_list("sinif", "sube"))
        mevcut_dh = set(DersHavuzu.objects.values_list("ders_adi", flat=True))
        return mevcut_ss, mevcut_dh

    # ------------------------------------------------------------------
    # Adim 1 – Veri varlığını doğrula
    # ------------------------------------------------------------------

    def verileri_aktar(self, sinav):
        """DB'deki kaynak verilerin varlığını doğrular."""
        self.log("\nVeri durumu kontrol ediliyor...")

        from okul.models import SinifSube
        from dersprogrami.models import DersProgrami
        from ogrenci.models import Ogrenci as OgrenciModel

        ss_count  = SinifSube.objects.count()
        dp_count  = DersProgrami.objects.count()
        ogr_count = OgrenciModel.objects.count()

        if not ss_count:
            raise RuntimeError("Sınıf/şube verisi yok. Veri aktarımı yapın.")
        if not dp_count:
            raise RuntimeError("Haftalık ders programı yok. Veri aktarımı yapın.")
        if not ogr_count:
            raise RuntimeError("Öğrenci listesi boş. Veri aktarımı yapın.")

        self.log(
            f"  {ss_count} sınıf/şube | {dp_count} ders programı kaydı | {ogr_count} öğrenci."
        )
