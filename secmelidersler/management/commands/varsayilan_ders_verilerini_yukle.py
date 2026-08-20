"""
Projeyle birlikte gelen, her Anadolu Lisesi için genel olarak geçerli varsayılan
ders verilerini yükler: Branşlar, Ortak Ders Havuzu, Seçmeli Ders Havuzu,
Zorunlu (Ortak) Dersler, Seçmeli Ders Grupları (bkz.
`secmelidersler/fixtures/varsayilan_ders_verileri.json` ve o dizindeki README).

Ortak Ders Havuzu / Seçmeli Ders Havuzu eğitim yılından bağımsızdır, her zaman
yüklenir. Zorunlu (Ortak) Dersler / Seçmeli Ders Grupları ise bir
`EgitimOgretimYili`ye bağlıdır: --egitim-yili verilmezse OkulBilgi'deki aktif
yıl kullanılır; hiçbiri yoksa hata verilir (bu durumda --sadece-havuz ile devam
edilebilir, ya da önce `okul_bilgisi_olustur` çalıştırılabilir).

İdempotenttir (get_or_create/update_or_create) — tekrar çalıştırmak var olan
kayıtları günceller, kopya oluşturmaz.

Kullanım:
    python manage.py varsayilan_ders_verilerini_yukle
    python manage.py varsayilan_ders_verilerini_yukle --sadece-havuz
    python manage.py varsayilan_ders_verilerini_yukle --egitim-yili 2025-2026
"""

import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

FIXTURE_YOLU = Path(__file__).resolve().parent.parent.parent / "fixtures" / "varsayilan_ders_verileri.json"


class Command(BaseCommand):
    help = "Projeyle gelen, her Anadolu Lisesi için geçerli varsayılan ders verilerini yükler."

    def add_arguments(self, parser):
        parser.add_argument(
            "--sadece-havuz",
            action="store_true",
            help=(
                "Yalnızca eğitim yılından bağımsız havuz tablolarını (Ortak Ders Havuzu, "
                "Seçmeli Ders Havuzu) yükler; Zorunlu (Ortak) Dersler ve Seçmeli Ders "
                "Grupları'nı atlar (aktif eğitim yılı henüz tanımlı değilse kullanışlıdır)."
            ),
        )
        parser.add_argument(
            "--egitim-yili",
            type=str,
            default=None,
            metavar="YIL",
            help=(
                "Zorunlu (Ortak) Dersler / Seçmeli Ders Grupları için hedef eğitim-öğretim "
                "yılı (örn: 2025-2026). Belirtilmezse OkulBilgi'deki aktif yıl kullanılır."
            ),
        )

    def handle(self, *args, **options):
        from okul.models import Brans, EgitimOgretimYili, OkulBilgi
        from secmelidersler.models import (
            OrtakDers,
            OrtakDersHavuzu,
            SecmeliDers,
            SecmeliDersGrubu,
            SecmeliDersHavuzu,
        )

        if not FIXTURE_YOLU.exists():
            raise CommandError(f"Varsayılan veri dosyası bulunamadı: {FIXTURE_YOLU}")
        veri = json.loads(FIXTURE_YOLU.read_text(encoding="utf-8"))

        self.stdout.write("Branşlar yükleniyor...")
        eklenen = sum(Brans.objects.get_or_create(ad=ad)[1] for ad in veri["branslar"])
        self.stdout.write(f"  {eklenen} yeni branş eklendi ({len(veri['branslar'])} toplam).")

        self.stdout.write("Ortak Ders Havuzu yükleniyor...")
        self._havuz_yukle(OrtakDersHavuzu, veri["ortak_ders_havuzu"], Brans)

        self.stdout.write("Seçmeli Ders Havuzu yükleniyor...")
        self._havuz_yukle(SecmeliDersHavuzu, veri["secmeli_ders_havuzu"], Brans, ("secimsayisi",))

        if options["sadece_havuz"]:
            self.stdout.write(self.style.SUCCESS("\nHavuz tabloları yüklendi (--sadece-havuz)."))
            return

        egitim_yili = self._egitim_yilini_bul(options.get("egitim_yili"), EgitimOgretimYili, OkulBilgi)

        self.stdout.write(f"Zorunlu (Ortak) Dersler yükleniyor [{egitim_yili}]...")
        self._ortak_dersler_yukle(OrtakDers, veri["ortak_dersler"], egitim_yili, Brans)

        self.stdout.write(f"Seçmeli Ders Grupları yükleniyor [{egitim_yili}]...")
        self._secmeli_gruplari_yukle(
            SecmeliDersGrubu, SecmeliDers, veri["secmeli_ders_gruplari"], egitim_yili, Brans
        )

        self.stdout.write(self.style.SUCCESS("\nVarsayılan ders verileri yüklendi."))

    def _egitim_yilini_bul(self, yil_str, EgitimOgretimYili, OkulBilgi):
        if yil_str:
            try:
                return EgitimOgretimYili.objects.get(egitim_yili=yil_str)
            except EgitimOgretimYili.DoesNotExist:
                raise CommandError(f"Eğitim-öğretim yılı bulunamadı: {yil_str!r}") from None

        egitim_yili = OkulBilgi.get().okul_egtyil
        if not egitim_yili:
            raise CommandError(
                "Aktif eğitim-öğretim yılı tanımlı değil. Önce Okul Bilgisi/Eğitim-Öğretim "
                "Yılı kaydını oluşturun (`python manage.py okul_bilgisi_olustur` ya da admin "
                "panelden Okul → Okul Bilgisi), ya da --egitim-yili ile açıkça belirtin. "
                "Yalnızca havuz tablolarını yüklemek için --sadece-havuz kullanabilirsiniz."
            )
        return egitim_yili

    def _brans_nesneleri(self, Brans, adlar):
        return [Brans.objects.get_or_create(ad=ad)[0] for ad in adlar]

    def _havuz_yukle(self, model, kayitlar, Brans, ekstra_alanlar=()):
        eklenen = guncellenen = 0
        for kayit in kayitlar:
            defaults = {"derssaati": kayit["derssaati"], "sira": kayit["sira"], "aktif": kayit["aktif"]}
            defaults.update({alan: kayit[alan] for alan in ekstra_alanlar})
            obj, created = model.objects.update_or_create(ders_adi=kayit["ders_adi"], defaults=defaults)
            obj.branslar.set(self._brans_nesneleri(Brans, kayit["branslar"]))
            eklenen += created
            guncellenen += not created
        self.stdout.write(f"  {eklenen} eklendi, {guncellenen} güncellendi ({len(kayitlar)} toplam).")

    def _ortak_dersler_yukle(self, OrtakDers, kayitlar, egitim_yili, Brans):
        eklenen = guncellenen = 0
        for kayit in kayitlar:
            obj, created = OrtakDers.objects.update_or_create(
                egitim_yili=egitim_yili,
                sinif_seviyesi=kayit["sinif_seviyesi"],
                ders_adi=kayit["ders_adi"],
                defaults={"haftalik_saat": kayit["haftalik_saat"], "sira": kayit["sira"]},
            )
            obj.branslar.set(self._brans_nesneleri(Brans, kayit["branslar"]))
            eklenen += created
            guncellenen += not created
        self.stdout.write(f"  {eklenen} eklendi, {guncellenen} güncellendi ({len(kayitlar)} toplam).")

    def _secmeli_gruplari_yukle(self, SecmeliDersGrubu, SecmeliDers, gruplar, egitim_yili, Brans):
        eklenen_grup = guncellenen_grup = eklenen_ders = guncellenen_ders = 0
        for grup_kayit in gruplar:
            grup, created = SecmeliDersGrubu.objects.update_or_create(
                egitim_yili=egitim_yili,
                sinif_seviyesi=grup_kayit["sinif_seviyesi"],
                adi=grup_kayit["adi"],
                defaults={"zorunlu_grup": grup_kayit["zorunlu_grup"], "sira": grup_kayit["sira"]},
            )
            eklenen_grup += created
            guncellenen_grup += not created
            for ders_kayit in grup_kayit["dersler"]:
                ders, d_created = SecmeliDers.objects.update_or_create(
                    grup=grup,
                    ders_adi=ders_kayit["ders_adi"],
                    defaults={
                        "saat_secenekleri": ders_kayit["saat_secenekleri"],
                        "sira": ders_kayit["sira"],
                        "aktif": ders_kayit["aktif"],
                    },
                )
                ders.branslar.set(self._brans_nesneleri(Brans, ders_kayit["branslar"]))
                eklenen_ders += d_created
                guncellenen_ders += not d_created
        self.stdout.write(
            f"  {eklenen_grup} grup eklendi, {guncellenen_grup} güncellendi; "
            f"{eklenen_ders} ders eklendi, {guncellenen_ders} güncellendi."
        )
