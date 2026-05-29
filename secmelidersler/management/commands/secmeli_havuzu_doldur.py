"""
Geçici yardımcı komut: mevcut SecmeliDers kayıtlarından SecmeliDersHavuzu'nu doldurur.

Kural:
  - Ders adı sonundaki "(N)" → secimsayisi = N, temiz ad = N öncesi kısım
  - Aynı temiz ada ait tüm saat_secenekleri değerleri birleştirilir (tekil, sıralı)
  - Zaten var olan kayıtlar güncellenmez (get_or_create)

Kullanım:
  python manage.py secmeli_havuzu_doldur
  python manage.py secmeli_havuzu_doldur --guncelle   # mevcut kayıtları da günceller
"""

import re
from collections import defaultdict

from django.core.management.base import BaseCommand

from secmelidersler.models import SecmeliDers, SecmeliDersHavuzu

_PARANTEZ = re.compile(r"^(.*?)\s*\((\d+)\)\s*$")


def _saat_birlestir(saat_str_listesi):
    """Birden fazla 'saat_secenekleri' dizesindeki tüm değerleri birleştirir."""
    degerler = set()
    for s in saat_str_listesi:
        for parca in s.split(","):
            parca = parca.strip()
            if parca.isdigit() and int(parca) >= 1:
                degerler.add(int(parca))
    return ",".join(str(v) for v in sorted(degerler)) if degerler else ""


class Command(BaseCommand):
    help = "Mevcut SecmeliDers kayıtlarından SecmeliDersHavuzu'nu doldurur."

    def add_arguments(self, parser):
        parser.add_argument(
            "--guncelle",
            action="store_true",
            help="Zaten var olan havuz kayıtlarını da günceller.",
        )

    def handle(self, *args, **options):
        guncelle = options["guncelle"]

        # Ders adına göre tüm saat seçeneklerini topla
        saat_map = defaultdict(list)       # temiz_adi -> [saat_secenekleri, ...]
        secimsayisi_map = {}               # temiz_adi -> secimsayisi

        for ders in SecmeliDers.objects.order_by("sira"):
            adi = ders.ders_adi.strip()
            m = _PARANTEZ.match(adi)
            if m:
                temiz_adi = m.group(1).strip()
                secimsayisi = int(m.group(2))
            else:
                temiz_adi = adi
                secimsayisi = 1

            saat_map[temiz_adi].append(ders.saat_secenekleri)
            # İlk karşılaşılan secimsayisi'ni koru
            secimsayisi_map.setdefault(temiz_adi, secimsayisi)

        eklenen = 0
        guncellenen = 0
        atlanan = 0

        for sira, temiz_adi in enumerate(saat_map):
            derssaati = _saat_birlestir(saat_map[temiz_adi])
            secimsayisi = secimsayisi_map[temiz_adi]

            obj, created = SecmeliDersHavuzu.objects.get_or_create(
                ders_adi=temiz_adi,
                defaults={
                    "derssaati": derssaati,
                    "secimsayisi": secimsayisi,
                    "sira": sira,
                    "aktif": True,
                },
            )

            if created:
                eklenen += 1
                self.stdout.write(
                    f"  + {temiz_adi}  "
                    f"(seçim: {secimsayisi}, saat: {derssaati or '—'})"
                )
            elif guncelle:
                obj.derssaati = derssaati
                obj.secimsayisi = secimsayisi
                obj.save(update_fields=["derssaati", "secimsayisi"])
                guncellenen += 1
                self.stdout.write(
                    f"  ~ {temiz_adi}  "
                    f"(seçim: {secimsayisi}, saat: {derssaati or '—'}) — güncellendi"
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
