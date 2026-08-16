"""
Aralık ayı (1. Dönem) için "boş derslere öğretmen atama" (ders doldurma) motorunu
gerçek arayüzde denemek amacıyla örnek/deneme verisi üretir.

Neden gerekli: Veritabanında 2025-12-01 uygulama tarihli GERÇEK bir Aralık ders
programı var, ancak o döneme ait gerçek Devamsızlık (kim devamsız) ve NobetGorevi
(kim o gün nöbetçi/müsait) kaydı yok — bu yüzden /nobet/ders-doldurma/ ekranı
Aralık'taki bir tarihle açılırsa boş sonuç döner. Bu komut, gerçek Aralık ders
programına karşılık gelecek örnek devamsızlık ve nöbet görevi kayıtları üretir;
böylece mevcut arayüz üzerinden ("Hesapla" ile) atama motoru gerçekçi biçimde
denenebilir.

ÖNEMLİ — bu bir DENEME aracıdır:
  - Ürettiği kayıtlar gerçek tablolara (nobet_devamsizlik, nobet_gorevi) yazılır.
  - Test sırasında ders-doldurma ekranında yalnızca "Hesapla" kullanın; "Kaydet"e
    basarsanız sonuçlar gerçek nöbet geçmişine (NobetGecmisi/NobetAtanamayan) ve
    dolayısıyla öğretmen istatistiklerine karışır.
  - Testi bitirince --temizle ile üretilen kayıtları (kazara "Kaydet" ile oluşmuş
    NobetGecmisi/NobetAtanamayan dahil) geri alabilirsiniz.

Kullanım:
  python manage.py aralik_deneme_verisi_olustur
  python manage.py aralik_deneme_verisi_olustur --tarih 2025-12-08 --devamsiz 8
  python manage.py aralik_deneme_verisi_olustur --temizle
  python manage.py aralik_deneme_verisi_olustur --temizle --tarih 2025-12-08
"""

import random
from datetime import datetime

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from dersprogrami.models import DersProgrami
from nobet.models import NobetGorevi, NobetOgretmen, NobetYerleri
from okul.models import OkulDonem
from personeldevamsizlik.models import Devamsizlik
from utility.services.main_services import IstatistikService

DAYS_MAP = {
    0: "Monday",
    1: "Tuesday",
    2: "Wednesday",
    3: "Thursday",
    4: "Friday",
    5: "Saturday",
    6: "Sunday",
}
HAFTA_ICI_GUNLER = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]

DENEME_ACIKLAMA_ETIKETI = "[ARALIK DENEME]"
DEVAMSIZ_TUR_SECENEKLERI = [0, 1, 2, 3]


def _program_tarihi(target_date):
    """target_date'e en yakın (<=) DersProgrami uygulama_tarihi'ni döner."""
    t = (
        DersProgrami.objects.filter(uygulama_tarihi__lte=target_date)
        .order_by("-uygulama_tarihi")
        .values_list("uygulama_tarihi", flat=True)
        .first()
    )
    return t


class Command(BaseCommand):
    help = (
        "Aralık ayı gerçek ders programına karşılık gelecek örnek Devamsızlık ve "
        "NobetGorevi (deneme) verisi üretir; /nobet/ders-doldurma/ ekranını Aralık "
        "tarihiyle denemeyi mümkün kılar."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--tarih",
            default="2025-12-08",
            help="Test edilecek tarih (YYYY-MM-DD). Varsayılan: 2025-12-08 (Pazartesi).",
        )
        parser.add_argument(
            "--devamsiz",
            type=int,
            default=6,
            metavar="SAYI",
            help="Üretilecek devamsız öğretmen sayısı (varsayılan: 6).",
        )
        parser.add_argument(
            "--temizle",
            action="store_true",
            help="Üretilmiş deneme verisini (ve varsa test tarihine kaydedilmiş "
            "gerçek atama sonuçlarını) siler; yeni veri üretmez.",
        )
        parser.add_argument(
            "--evet",
            action="store_true",
            help="Onay sormadan çalıştır.",
        )

    def handle(self, *args, **options):
        try:
            target_date = datetime.strptime(options["tarih"], "%Y-%m-%d").date()
        except ValueError:
            raise CommandError("--tarih YYYY-MM-DD formatında olmalı.")

        program_date = _program_tarihi(target_date)
        if not program_date:
            raise CommandError(
                f"{target_date} tarihi için (veya öncesi için) hiç DersProgrami kaydı yok."
            )

        if options["temizle"]:
            self._temizle(target_date, program_date, options["evet"])
            return

        if target_date.weekday() >= 5:
            raise CommandError("--tarih hafta içi bir gün olmalı (Cumartesi/Pazar değil).")

        self._olustur(target_date, program_date, options["devamsiz"], options["evet"])

    # ------------------------------------------------------------------

    def _olustur(self, target_date, program_date, devamsiz_sayisi, evet):
        donem = (
            OkulDonem.objects.select_related("egitim_yili")
            .filter(baslangic__lte=program_date, bitis__gte=program_date)
            .first()
        )
        if not donem:
            raise CommandError(
                f"{program_date} tarihini kapsayan bir OkulDonem bulunamadı."
            )
        egitim_yili = donem.egitim_yili

        # Bu programa (program_date) ders programı olan, nöbet tutabilen öğretmenler
        havuz = list(
            NobetOgretmen.objects.filter(
                personel__nobeti_var=True,
                personel__dersprogrami__uygulama_tarihi=program_date,
            )
            .select_related("personel")
            .distinct()
        )
        if len(havuz) < devamsiz_sayisi + 5:
            raise CommandError(
                f"{program_date} programında yeterli öğretmen yok "
                f"({len(havuz)} bulundu)."
            )

        yerler = list(NobetYerleri.objects.filter(aktif=True))
        if not yerler:
            raise CommandError("Tanımlı (aktif) nöbet yeri bulunamadı.")

        self.stdout.write(
            f"Hedef tarih : {target_date} ({DAYS_MAP[target_date.weekday()]})\n"
            f"Program tarihi (Aralık ders programı) : {program_date}\n"
            f"Dönem : {egitim_yili} / {donem.donem}. Dönem\n"
            f"Uygun öğretmen havuzu : {len(havuz)}\n"
        )

        if not evet:
            cevap = input(
                f"{program_date} tarihli örnek NobetGorevi ve "
                f"{devamsiz_sayisi} adet Devamsızlık kaydı oluşturulacak. "
                "Devam edilsin mi? [e/H]: "
            ).strip().lower()
            if cevap not in ("e", "evet"):
                self.stdout.write("İptal edildi.")
                return

        with transaction.atomic():
            # Önce aynı program_date'e ait önceki deneme verisini temizle (idempotent).
            self._sil_gorev_ve_devamsizlik(program_date)

            rastgele_havuz = havuz[:]
            random.shuffle(rastgele_havuz)

            # ── Haftalık nöbet görevi (kim müsait/nöbetçi) ──────────────────
            gorev_sayisi = 0
            for i, ogretmen in enumerate(rastgele_havuz):
                gun = HAFTA_ICI_GUNLER[i % len(HAFTA_ICI_GUNLER)]
                yer = yerler[i % len(yerler)]
                NobetGorevi.objects.create(
                    nobet_gun=gun,
                    nobet_yeri=yer,
                    uygulama_tarihi=program_date,
                    ogretmen=ogretmen,
                    egitim_yili=egitim_yili,
                    donem=donem,
                )
                gorev_sayisi += 1

            # ── Devamsızlık (kim boş ders bırakıyor) ────────────────────────
            devamsiz_havuz = random.sample(
                havuz, k=min(devamsiz_sayisi, len(havuz))
            )
            devamsiz_sayisi_olusan = 0
            for ogretmen in devamsiz_havuz:
                tam_gun = random.random() < 0.7
                saatler = "1,2,3,4,5,6,7,8" if tam_gun else random.choice(
                    ["1,2,3,4", "5,6,7,8", "1,2,3,4,5"]
                )
                Devamsizlik.objects.create(
                    baslangic_tarihi=target_date,
                    sure=1,
                    devamsiz_tur=random.choice(DEVAMSIZ_TUR_SECENEKLERI),
                    aciklama=f"{DENEME_ACIKLAMA_ETIKETI} otomatik oluşturuldu",
                    ders_saatleri=saatler,
                    gorevlendirme_yapilsin=True,
                    ogretmen=ogretmen,
                )
                devamsiz_sayisi_olusan += 1

        self.stdout.write(self.style.SUCCESS(
            f"\n✓ {gorev_sayisi} NobetGorevi ve {devamsiz_sayisi_olusan} Devamsızlık "
            "kaydı oluşturuldu.\n"
            f"Şimdi arayüzde deneyin: /nobet/ders-doldurma/?tarih={target_date}\n"
            "Yalnızca 'Hesapla' kullanın — 'Kaydet' gerçek nöbet geçmişine yazar.\n"
            "Test bitince: python manage.py aralik_deneme_verisi_olustur --temizle "
            f"--tarih {target_date}"
        ))

    # ------------------------------------------------------------------

    def _sil_gorev_ve_devamsizlik(self, program_date):
        NobetGorevi.objects.filter(uygulama_tarihi=program_date).delete()
        Devamsizlik.objects.filter(
            aciklama__startswith=DENEME_ACIKLAMA_ETIKETI
        ).delete()

    def _temizle(self, target_date, program_date, evet):
        from datetime import time

        from django.utils import timezone

        from nobet.models import NobetAtanamayan, NobetGecmisi

        gorev_sayisi = NobetGorevi.objects.filter(uygulama_tarihi=program_date).count()
        devamsiz_sayisi = Devamsizlik.objects.filter(
            aciklama__startswith=DENEME_ACIKLAMA_ETIKETI
        ).count()

        start_dt = timezone.make_aware(datetime.combine(target_date, time.min))
        end_dt = timezone.make_aware(datetime.combine(target_date, time.max))
        gecmis_sayisi = NobetGecmisi.objects.filter(tarih__range=[start_dt, end_dt]).count()
        atanamayan_sayisi = NobetAtanamayan.objects.filter(
            tarih__range=[start_dt, end_dt]
        ).count()

        toplam = gorev_sayisi + devamsiz_sayisi + gecmis_sayisi + atanamayan_sayisi
        if toplam == 0:
            self.stdout.write(self.style.SUCCESS("Silinecek deneme verisi bulunamadı."))
            return

        self.stdout.write(
            f"Silinecek:\n"
            f"  NobetGorevi ({program_date} tarihli)        : {gorev_sayisi}\n"
            f"  Devamsızlık ({DENEME_ACIKLAMA_ETIKETI})      : {devamsiz_sayisi}\n"
            f"  NobetGecmisi ({target_date} tarihli)         : {gecmis_sayisi}\n"
            f"  NobetAtanamayan ({target_date} tarihli)      : {atanamayan_sayisi}\n"
        )
        if not evet:
            cevap = input("Devam edilsin mi? [e/H]: ").strip().lower()
            if cevap not in ("e", "evet"):
                self.stdout.write("İptal edildi.")
                return

        with transaction.atomic():
            self._sil_gorev_ve_devamsizlik(program_date)
            NobetGecmisi.objects.filter(tarih__range=[start_dt, end_dt]).delete()
            NobetAtanamayan.objects.filter(tarih__range=[start_dt, end_dt]).delete()

        try:
            IstatistikService().hesapla_ve_kaydet()
        except Exception as e:
            self.stdout.write(self.style.WARNING(f"İstatistik güncelleme hatası: {e}"))

        self.stdout.write(self.style.SUCCESS("✓ Deneme verisi temizlendi."))
