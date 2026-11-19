"""akal-eta-yonetim paketi değiştiyse SURUM'u artırır (geliştirme makinesinde).

Kullanım:
    python manage.py tahta_surum_artir            # 1.2.0 → 1.2.1 (düzeltme)
    python manage.py tahta_surum_artir --kucuk    # 1.2.0 → 1.3.0 (yeni özellik)
    python manage.py tahta_surum_artir --buyuk    # 1.2.0 → 2.0.0
    python manage.py tahta_surum_artir --denetle  # yalnızca durumu söyler

`akal_eta_yonetim.py` içindeki SURUM'u ve `paket-ozeti.txt`'yi günceller; ikisi
birlikte commit'lenir. İçerik değişmediyse hiçbir şey yapmaz. SURUM elle
artırılmışsa o sürüm kaydedilir.
"""

from django.core.management.base import BaseCommand, CommandError

from tahtalar.services import paket_surumu


class Command(BaseCommand):
    help = "akal-eta-yonetim paketi değiştiyse SURUM'u artırır ve içerik özetini kaydeder."

    def add_arguments(self, parser):
        grup = parser.add_mutually_exclusive_group()
        grup.add_argument("--kucuk", action="store_true", help="Yeni özellik: X.Y+1.0")
        grup.add_argument("--buyuk", action="store_true", help="Uyumsuz değişiklik: X+1.0.0")
        grup.add_argument("--denetle", action="store_true", help="Yalnızca denetle, yazma")
        grup.add_argument(
            "--kaydet",
            action="store_true",
            help="SURUM'a dokunmadan özeti kaydet (ilk kurulum)",
        )

    def handle(self, *args, kucuk, buyuk, denetle, kaydet, **options):
        try:
            if denetle:
                sorun = paket_surumu.denetle()
                if sorun:
                    raise CommandError(sorun)
                self.stdout.write(self.style.SUCCESS("SURUM ve paket içeriği uyumlu."))
                return
            if kaydet:
                surum = paket_surumu.kaydet()
                self.stdout.write(self.style.SUCCESS(f"Özet {surum} için kaydedildi."))
                return
            seviye = "buyuk" if buyuk else "kucuk" if kucuk else "yama"
            eski, yeni = paket_surumu.artir(seviye)
        except paket_surumu.SurumHatasi as hata:
            raise CommandError(str(hata)) from hata
        if yeni is None:
            sorun = paket_surumu.denetle()
            self.stdout.write(sorun or f"Paket içeriği değişmedi; SURUM {eski} kaldı.")
            return
        self.stdout.write(
            self.style.SUCCESS(
                f"SURUM {eski} → {yeni}. akal_eta_yonetim.py ve paket-ozeti.txt'yi "
                "birlikte commit'leyin."
            )
        )
