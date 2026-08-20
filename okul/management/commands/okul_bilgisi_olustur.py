"""
Okul Bilgisi singleton kaydını ve (yoksa) ilgili Eğitim-Öğretim Yılı kaydını
oluşturur — ilk kurulumu kolaylaştırmak için `kurulumcu` sihirbazı tarafından
çağrılır, ama tek başına da çalıştırılabilir.

CLAUDE.md'de belirtildiği gibi bu kayıt normalde admin panelinden elle
oluşturulur ("Okul → Okul Bilgisi"); bu komut yalnızca o adımın ilk kurulumdaki
karşılığıdır. Okul Bilgisi zaten yapılandırılmışsa (okul_adi doluysa) hiçbir
şey değiştirmez — var olan bir okulun bilgilerini sessizce ezmez.

Kullanım:
    python manage.py okul_bilgisi_olustur --okul-adi "Örnek Anadolu Lisesi" --egitim-yili 2025-2026
    python manage.py okul_bilgisi_olustur --okul-adi "..." --egitim-yili 2025-2026 \\
        --okul-kodu 123456 --okul-muduru "Ad Soyad" \\
        --baslangic 2025-09-01 --bitis 2026-06-19
"""

import datetime

from django.core.management.base import BaseCommand, CommandError


def _varsayilan_tarihler(egitim_yili: str) -> tuple[datetime.date, datetime.date]:
    """'2025-2026' → (1 Eylül 2025, 20 Haziran 2026) gibi mantıklı varsayılanlar üretir."""
    try:
        ilk_yil_str, ikinci_yil_str = egitim_yili.split("-")
        ilk_yil, ikinci_yil = int(ilk_yil_str), int(ikinci_yil_str)
    except ValueError:
        raise CommandError(f"Eğitim-öğretim yılı 'YYYY-YYYY' biçiminde olmalı: {egitim_yili!r}") from None
    return datetime.date(ilk_yil, 9, 1), datetime.date(ikinci_yil, 6, 20)


class Command(BaseCommand):
    help = "Okul Bilgisi ve Eğitim-Öğretim Yılı kaydını oluşturur (ilk kurulum için)."

    def add_arguments(self, parser):
        parser.add_argument("--okul-adi", type=str, required=True, metavar="AD")
        parser.add_argument("--egitim-yili", type=str, required=True, metavar="YYYY-YYYY")
        parser.add_argument("--okul-kodu", type=str, default="")
        parser.add_argument("--okul-muduru", type=str, default="")
        parser.add_argument(
            "--baslangic", type=str, default=None, metavar="YYYY-MM-DD",
            help="Belirtilmezse eğitim yılının ilk yılının 1 Eylül'ü varsayılır.",
        )
        parser.add_argument(
            "--bitis", type=str, default=None, metavar="YYYY-MM-DD",
            help="Belirtilmezse eğitim yılının ikinci yılının 20 Haziran'ı varsayılır.",
        )

    def handle(self, *args, **options):
        from okul.models import EgitimOgretimYili, OkulBilgi

        okul = OkulBilgi.get()
        if okul.okul_adi:
            self.stdout.write(
                self.style.WARNING(
                    f"Okul Bilgisi zaten yapılandırılmış ({okul.okul_adi!r}), hiçbir şey değiştirilmedi."
                )
            )
            return

        egitim_yili_str = options["egitim_yili"]
        varsayilan_baslangic, varsayilan_bitis = _varsayilan_tarihler(egitim_yili_str)
        baslangic = (
            datetime.date.fromisoformat(options["baslangic"])
            if options["baslangic"]
            else varsayilan_baslangic
        )
        bitis = datetime.date.fromisoformat(options["bitis"]) if options["bitis"] else varsayilan_bitis

        egitim_yili, olusturuldu = EgitimOgretimYili.objects.get_or_create(
            egitim_yili=egitim_yili_str,
            defaults={"egitim_baslangic": baslangic, "egitim_bitis": bitis},
        )
        if olusturuldu:
            self.stdout.write(self.style.SUCCESS(f"Eğitim-Öğretim Yılı oluşturuldu: {egitim_yili}"))
        else:
            self.stdout.write(f"Eğitim-Öğretim Yılı zaten vardı: {egitim_yili}")

        okul.okul_adi = options["okul_adi"]
        okul.okul_kodu = options["okul_kodu"]
        okul.okul_muduru = options["okul_muduru"]
        okul.okul_egtyil = egitim_yili
        okul.save()
        self.stdout.write(self.style.SUCCESS(f"Okul Bilgisi kaydedildi: {okul.okul_adi} [{egitim_yili}]"))
