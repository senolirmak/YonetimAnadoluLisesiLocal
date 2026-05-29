"""
Geçici yardımcı komut: tüm öğrenciler için mevcut yıl ders atamasını
aktif ders programından (DersProgrami.objects.aktif()) yapar.

  - Her öğrenci için sınıf/şubeye ait (ders, gün, ders_saati) üçlüsü distinct alınır
  - Aynı slotta birden fazla öğretmen varsa (örn. GÖRSEL SANATLAR/MÜZİK) tek saat sayılır
  - Mevcut OgrenciMevcutDers kayıtları silinip yeniden oluşturulur
  - Ders programında tanımlı olmayan sınıf/şubeye sahip öğrenciler atlanır

Kullanım:
  python manage.py mevcut_dersler_ata
  python manage.py mevcut_dersler_ata --sinif 9        # sadece 9. sınıf
  python manage.py mevcut_dersler_ata --sinif 9 --sube A
"""

from collections import defaultdict

from django.core.management.base import BaseCommand
from django.db import transaction

from dersprogrami.models import DersProgrami
from ogrenci.models import Ogrenci
from okul.models import SinifSube
from ogrencidersleri.models import OgrenciMevcutDers


def _ders_saatleri_hesapla(sinif_sube_obj):
    """
    (ders_id, gun, ders_saati_id) distinct → ders_id başına haftalık saat.
    Çok öğretmenli derslerde her zaman dilimi tek sayılır.
    """
    slots = (
        DersProgrami.objects.aktif()
        .filter(sinif_sube=sinif_sube_obj)
        .values("ders_id", "gun", "ders_saati_id")
        .distinct()
    )
    saat_map = defaultdict(int)
    for slot in slots:
        saat_map[slot["ders_id"]] += 1
    return saat_map  # {ders_id: haftalik_saat}


class Command(BaseCommand):
    help = "Tüm öğrenciler için mevcut yıl ders atamasını aktif ders programından yapar."

    def add_arguments(self, parser):
        parser.add_argument("--sinif", type=int, help="Sadece bu sınıf seviyesini işle.")
        parser.add_argument("--sube", type=str, help="Sadece bu şubeyi işle (--sinif ile birlikte).")

    def handle(self, *args, **options):
        sinif_filtre = options.get("sinif")
        sube_filtre = (options.get("sube") or "").strip().upper() or None

        # Sınıf/şube → ders saatleri önbelleği (aynı şubeyi birden fazla öğrenciye tekrar sorgulamayalım)
        dp_cache = {}

        ogrenciler = Ogrenci.objects.order_by("sinif", "sube", "okulno")
        if sinif_filtre:
            ogrenciler = ogrenciler.filter(sinif=sinif_filtre)
        if sube_filtre:
            ogrenciler = ogrenciler.filter(sube__iexact=sube_filtre)

        toplam = ogrenciler.count()
        self.stdout.write(f"İşlenecek öğrenci: {toplam}")

        atanan = atlanan = 0

        with transaction.atomic():
            for ogr in ogrenciler:
                key = (ogr.sinif, ogr.sube)

                if key not in dp_cache:
                    try:
                        ss = SinifSube.objects.get(sinif=ogr.sinif, sube=ogr.sube)
                        dp_cache[key] = _ders_saatleri_hesapla(ss)
                    except SinifSube.DoesNotExist:
                        dp_cache[key] = None

                saat_map = dp_cache[key]

                if not saat_map:
                    self.stdout.write(
                        self.style.WARNING(
                            f"  ! {ogr.sinif}/{ogr.sube} ders programında yok — atlandı: {ogr.adi} {ogr.soyadi}"
                        )
                    )
                    atlanan += 1
                    continue

                OgrenciMevcutDers.objects.filter(ogrenci=ogr).delete()
                OgrenciMevcutDers.objects.bulk_create([
                    OgrenciMevcutDers(
                        ogrenci=ogr,
                        ders_id=ders_id,
                        haftalik_saat=saat,
                    )
                    for ders_id, saat in saat_map.items()
                ])
                atanan += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"\nTamamlandı: {atanan} öğrenciye ders atandı"
                + (f", {atlanan} öğrenci atlandı (ders programı yok)" if atlanan else "")
                + "."
            )
        )
