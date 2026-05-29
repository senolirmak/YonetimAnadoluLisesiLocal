"""
Geçici yardımcı komut: mevcut OrtakDers kayıtlarından OrtakDersHavuzu'nu doldurur.

Kural:
  - Aynı ders adına ait tüm haftalik_saat değerleri birleştirilir (tekil, sıralı)
  - Zaten var olan kayıtlar güncellenmez (get_or_create)

Kullanım:
  python manage.py ortak_havuzu_doldur
  python manage.py ortak_havuzu_doldur --guncelle   # mevcut kayıtları da günceller
"""

from collections import defaultdict

from django.core.management.base import BaseCommand

from secmelidersler.models import OrtakDers, OrtakDersHavuzu


class Command(BaseCommand):
    help = "Mevcut OrtakDers kayıtlarından OrtakDersHavuzu'nu doldurur."

    def add_arguments(self, parser):
        parser.add_argument(
            "--guncelle",
            action="store_true",
            help="Zaten var olan havuz kayıtlarını da günceller.",
        )

    def handle(self, *args, **options):
        guncelle = options["guncelle"]

        saat_map = defaultdict(set)  # ders_adi -> {haftalik_saat, ...}

        for ders in OrtakDers.objects.order_by("sira"):
            saat_map[ders.ders_adi.strip()].add(ders.haftalik_saat)

        eklenen = 0
        guncellenen = 0
        atlanan = 0

        for sira, ders_adi in enumerate(saat_map):
            derssaati = ",".join(str(v) for v in sorted(saat_map[ders_adi]))

            obj, created = OrtakDersHavuzu.objects.get_or_create(
                ders_adi=ders_adi,
                defaults={
                    "derssaati": derssaati,
                    "sira": sira,
                    "aktif": True,
                },
            )

            if created:
                eklenen += 1
                self.stdout.write(f"  + {ders_adi}  (saat: {derssaati or '—'})")
            elif guncelle:
                obj.derssaati = derssaati
                obj.save(update_fields=["derssaati"])
                guncellenen += 1
                self.stdout.write(
                    f"  ~ {ders_adi}  (saat: {derssaati or '—'}) — güncellendi"
                )
            else:
                atlanan += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"\nTamamlandı: {eklenen} eklendi"
                + (f", {guncellenen} güncellendi" if guncelle else "")
                + (f", {atlanan} zaten mevcut (atlandı)" if atlanan else "")
                + "."
            )
        )
