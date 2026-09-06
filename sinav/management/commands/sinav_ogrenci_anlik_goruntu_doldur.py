"""
Zaten Oturma Planı üretilmiş ama henüz `SinavOgrenci` anlık görüntüsü olmayan
(eski) sınavlar için, mevcut `OturmaPlani` kayıtlarındaki donmuş metin
alanlarından (okulno / adı-soyadı / sinifsube) geriye dönük bir anlık görüntü
oluşturur — bkz. `sinav.models.SinavOgrenci` docstring'i.

Bu komut yalnızca ORTAKSINAV_ENGINE'in `SinavOgrenci` desteği eklendiği ANDA
zaten üretilmiş bulunan sınavlar için bir kereye mahsus geçiş amaçlıdır:
bundan sonra üretilecek her sınav, ilk "Oturma Üret" çalıştığında kendi anlık
görüntüsünü otomatik alır (bkz. `ortaksinav_engine.services.oturma.
anlik_goruntu_garanti_et`) — bu komuda ihtiyaç duymaz.

`adı-soyadı` → adı/soyadı ve `sinifsube` ("9/A") → sınıf/şube ayrımı metin
bazlı ve en iyi çaba (best-effort) ile yapılır (bkz. `build_salon_grids`'teki
aynı yaklaşım); `cinsiyet` ve `sureksiz_devamsız` OturmaPlani'de tutulmadığından
geriye dönük olarak bilinemez, varsayılan (boş / False) bırakılır — bu yalnızca
o sınav ileride kısmen yeniden üretilirse (ör. tek bir oturumu düzeltmek için)
kullanılacağından etkisi sınırlıdır. Muafiyetler de aynı sebeple geri
doldurulmaz.

Kullanım:
    python manage.py sinav_ogrenci_anlik_goruntu_doldur           # tüm eksik sınavlar
    python manage.py sinav_ogrenci_anlik_goruntu_doldur --sinav 4  # tek bir sınav
"""
import re

from django.core.management.base import BaseCommand

_SINIFSUBE_RE = re.compile(r"^(\d+)\s*/\s*([A-Za-zÇĞİÖŞÜçğıöşü]+)$")


class Command(BaseCommand):
    help = (
        "Oturma Planı üretilmiş ama SinavOgrenci anlık görüntüsü olmayan eski "
        "sınavlar için, OturmaPlani'deki donmuş verilerden geriye dönük bir "
        "anlık görüntü oluşturur."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--sinav", type=int, default=None, metavar="PK",
            help="Yalnızca bu SinavBilgisi.pk için doldur (belirtilmezse eksik olan tüm sınavlar).",
        )

    def handle(self, *args, **options):
        from sinav.models import OturmaPlani, SinavBilgisi, SinavOgrenci

        sinavlar = SinavBilgisi.objects.filter(pk=options["sinav"]) if options["sinav"] else SinavBilgisi.objects.all()

        for sinav in sinavlar:
            if SinavOgrenci.objects.filter(sinav=sinav).exists():
                self.stdout.write(f"'{sinav}' için anlık görüntü zaten var, atlanıyor.")
                continue

            satirlar = list(
                OturmaPlani.objects.filter(sinav=sinav)
                .values("okulno", "adi_soyadi", "sinifsube")
                .distinct()
            )
            if not satirlar:
                continue  # bu sınav için hiç oturma planı yok, doldurulacak bir şey yok

            yeni = []
            atlanan = 0
            for row in satirlar:
                eslesme = _SINIFSUBE_RE.match((row["sinifsube"] or "").strip())
                if not eslesme:
                    atlanan += 1
                    continue
                try:
                    okulno = int(row["okulno"])
                except (TypeError, ValueError):
                    atlanan += 1
                    continue
                parcalar = (row["adi_soyadi"] or "").split(" ", 1)
                yeni.append(SinavOgrenci(
                    sinav=sinav,
                    okulno=okulno,
                    adi=parcalar[0] if parcalar else "",
                    soyadi=parcalar[1] if len(parcalar) > 1 else "",
                    sinif=int(eslesme.group(1)),
                    sube=eslesme.group(2).upper(),
                ))

            SinavOgrenci.objects.bulk_create(yeni, ignore_conflicts=True)
            mesaj = f"'{sinav}': {len(yeni)} öğrenci anlık görüntüsü oluşturuldu."
            if atlanan:
                mesaj += f" ({atlanan} satır ayrıştırılamadı, atlandı.)"
            self.stdout.write(self.style.SUCCESS(mesaj))
