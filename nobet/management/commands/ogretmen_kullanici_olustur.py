"""
Kullanıcısı olmayan veya 'ogretmen' grubuna atanmamış NobetPersonel
kayıtları için Django kullanıcısı oluşturur.

Kullanım:
    python manage.py ogretmen_kullanici_olustur            # önizleme (dry-run)
    python manage.py ogretmen_kullanici_olustur --kaydet   # gerçek kayıt
"""

from django.contrib.auth.models import Group, User
from django.core.management.base import BaseCommand

from nobet.models import NobetPersonel

_TR_TABLE = {
    ord("ç"): "c", ord("Ç"): "c",
    ord("ğ"): "g", ord("Ğ"): "g",
    ord("ı"): "i", ord("İ"): "i",
    ord("ö"): "o", ord("Ö"): "o",
    ord("ş"): "s", ord("Ş"): "s",
    ord("ü"): "u", ord("Ü"): "u",
}

DEFAULT_SIFRE = "452869Zx"


def tr_normalize(metin: str) -> str:
    """Türkçe karakterleri ASCII karşılıklarına çevirir, küçük harf yapar."""
    return metin.translate(_TR_TABLE).lower()


def kullanici_adi_uret(adi_soyadi: str) -> str:
    """'Ahmet Çelik' → 'ahmetcelik'"""
    parcalar = adi_soyadi.strip().split()
    return "".join(tr_normalize(p) for p in parcalar)


class Command(BaseCommand):
    help = "Kullanıcısı olmayan öğretmenler için hesap oluşturur."

    def add_arguments(self, parser):
        parser.add_argument(
            "--kaydet",
            action="store_true",
            default=False,
            help="Bu bayrak verilmezse yalnızca önizleme yapılır (dry-run).",
        )

    def handle(self, *args, **options):
        kaydet = options["kaydet"]
        ogretmen_grubu, _ = Group.objects.get_or_create(name="ogretmen")

        # Kullanıcısı olmayan VEYA ogretmen grubunda olmayan personeller
        eksikler = NobetPersonel.objects.filter(
            user__isnull=True
        ) | NobetPersonel.objects.exclude(
            user__groups__name="ogretmen"
        ).filter(user__isnull=False)

        eksikler = eksikler.distinct().order_by("adi_soyadi")

        if not eksikler.exists():
            self.stdout.write(self.style.SUCCESS("Tüm personellerin kullanıcısı zaten mevcut."))
            return

        self.stdout.write(f"{'ÖNİZLEME — ' if not kaydet else ''}İşlenecek kayıt sayısı: {eksikler.count()}\n")
        self.stdout.write(f"{'Durum':<10} {'Kullanıcı Adı':<25} {'Ad Soyad'}")
        self.stdout.write("-" * 65)

        olusturulan = 0
        guncellenen = 0
        atlanan = 0

        for personel in eksikler:
            adi_soyadi = personel.adi_soyadi.strip()
            parcalar = adi_soyadi.split()
            soyad = parcalar[-1] if len(parcalar) > 1 else ""
            ad = " ".join(parcalar[:-1]) if len(parcalar) > 1 else adi_soyadi

            kullanici_adi = kullanici_adi_uret(adi_soyadi)

            # Çakışma varsa sonuna sayı ekle
            taban = kullanici_adi
            sayac = 1
            while User.objects.filter(username=kullanici_adi).exclude(
                pk=personel.user_id
            ).exists():
                kullanici_adi = f"{taban}{sayac}"
                sayac += 1

            if personel.user is None:
                # Yeni kullanıcı oluştur
                if kaydet:
                    user = User.objects.create_user(
                        username=kullanici_adi,
                        password=DEFAULT_SIFRE,
                        first_name=ad,
                        last_name=soyad,
                        is_active=True,
                    )
                    user.groups.add(ogretmen_grubu)
                    personel.user = user
                    personel.save(update_fields=["user"])
                durum = "OLUŞTUR"
                olusturulan += 1
            else:
                # Kullanıcı var ama ogretmen grubunda değil
                if kaydet:
                    user = personel.user
                    user.groups.add(ogretmen_grubu)
                    if not user.first_name:
                        user.first_name = ad
                        user.last_name = soyad
                        user.save(update_fields=["first_name", "last_name"])
                    kullanici_adi = personel.user.username  # mevcut adı göster
                durum = "GÜNCELLE"
                guncellenen += 1

            self.stdout.write(f"{durum:<10} {kullanici_adi:<25} {adi_soyadi}")

        self.stdout.write("-" * 65)
        if kaydet:
            self.stdout.write(self.style.SUCCESS(
                f"Tamamlandı — Oluşturulan: {olusturulan}, Güncellenen: {guncellenen}, Atlanan: {atlanan}"
            ))
        else:
            self.stdout.write(self.style.WARNING(
                f"Önizleme tamamlandı. Uygulamak için --kaydet bayrağını ekleyin."
            ))
