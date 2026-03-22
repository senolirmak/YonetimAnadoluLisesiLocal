"""
Öğrenci verileri içeren tabloları temizler:
  - Öğrenci Devamsızlık
  - Faaliyet
  - Çağrı (tüm servisler)
  - Rehberlik Görüşmeleri
  - Disiplin Görüşmeleri
  - Müdüriyet Görüşmeleri

Kullanım:
  python manage.py veri_temizle
  python manage.py veri_temizle --evet     (onay sormadan çalıştır)
  python manage.py veri_temizle --sadece devamsizlik cagri
"""

from django.core.management.base import BaseCommand

TABLOLAR = {
    "devamsizlik": {
        "app": "devamsizlik",
        "model": "OgrenciDevamsizlik",
        "aciklama": "Öğrenci Devamsızlık",
    },
    "faaliyet": {
        "app": "faaliyet",
        "model": "Faaliyet",
        "aciklama": "Faaliyet",
        "m2m": ["ogrenciler"],
    },
    "cagri": {
        "app": "cagri",
        "model": "OgrenciCagri",
        "aciklama": "Öğrenci Çağrı (tüm servisler)",
    },
    "rehberlik_gorusme": {
        "app": "rehberlik",
        "model": "Gorusme",
        "aciklama": "Rehberlik Görüşmeleri",
        "m2m": ["grup_ogrencileri"],
    },
    "disiplin_gorusme": {
        "app": "disiplin",
        "model": "DisiplinGorusme",
        "aciklama": "Disiplin Görüşmeleri",
        "m2m": ["grup_ogrencileri"],
    },
    "muduriyetcagri_gorusme": {
        "app": "muduriyetcagri",
        "model": "MuduriyetGorusme",
        "aciklama": "Müdüriyet Görüşmeleri",
        "m2m": ["grup_ogrencileri"],
    },
}


class Command(BaseCommand):
    help = "Öğrenci Devamsızlık, Faaliyet, Çağrı ve Görüşme tablolarını temizler."

    def add_arguments(self, parser):
        parser.add_argument(
            "--evet",
            action="store_true",
            help="Onay sormadan çalıştır.",
        )
        parser.add_argument(
            "--sadece",
            nargs="+",
            metavar="TABLO",
            help=f"Yalnızca belirtilen tabloları temizle. Seçenekler: {', '.join(TABLOLAR)}",
        )

    def handle(self, *args, **options):
        sadece = options.get("sadece")
        if sadece:
            gecersiz = [t for t in sadece if t not in TABLOLAR]
            if gecersiz:
                self.stderr.write(
                    self.style.ERROR(
                        f"Bilinmeyen tablo(lar): {', '.join(gecersiz)}\n"
                        f"Geçerli seçenekler: {', '.join(TABLOLAR)}"
                    )
                )
                return
            hedef = {k: v for k, v in TABLOLAR.items() if k in sadece}
        else:
            hedef = TABLOLAR

        # Mevcut kayıt sayılarını göster
        self.stdout.write("\nTemizlenecek tablolar:")
        self.stdout.write("-" * 45)
        kayit_sayilari = {}
        for anahtar, cfg in hedef.items():
            from django.apps import apps

            Model = apps.get_model(cfg["app"], cfg["model"])
            sayi = Model.objects.count()
            kayit_sayilari[anahtar] = sayi
            self.stdout.write(f"  {cfg['aciklama']:<35} {sayi:>5} kayıt")
        self.stdout.write("-" * 45)
        toplam = sum(kayit_sayilari.values())
        self.stdout.write(f"  {'TOPLAM':<35} {toplam:>5} kayıt\n")

        if toplam == 0:
            self.stdout.write(self.style.SUCCESS("Tüm tablolar zaten boş."))
            return

        # Onay
        if not options["evet"]:
            cevap = input("Devam etmek istiyor musunuz? [e/H]: ").strip().lower()
            if cevap not in ("e", "evet"):
                self.stdout.write("İptal edildi.")
                return

        # Silme işlemi
        from django.apps import apps
        from django.db import transaction

        with transaction.atomic():
            for anahtar, cfg in hedef.items():
                Model = apps.get_model(cfg["app"], cfg["model"])
                # M2M ilişkileri temizle
                for m2m_adi in cfg.get("m2m", []):
                    for obj in Model.objects.all():
                        getattr(obj, m2m_adi).clear()
                sayi, _ = Model.objects.all().delete()
                self.stdout.write(
                    self.style.SUCCESS(f"  ✓ {cfg['aciklama']}: {sayi} kayıt silindi.")
                )

        self.stdout.write(self.style.SUCCESS("\nTemizleme tamamlandı."))
