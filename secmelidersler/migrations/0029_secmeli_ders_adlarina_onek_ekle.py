"""Seçmeli Ders Havuzu'ndaki ön eksiz ders adlarına "SEÇMELİ " ön ekini ekler.

e-Okul (ve dolayısıyla okul.DersHavuzu / haftalık ders programı) seçmeli dersleri
her zaman "SEÇMELİ ..." adıyla tutar; havuzda ise derslerin bir kısmı ön ekli, bir
kısmı ön eksizdi. Seçmeli ders gruplarındaki dersler (SecmeliDers) havuza AD
üzerinden bağlandığından (bkz. secmelidersler.views ve services/secim_sayisi.py),
yeniden adlandırılan her havuz dersinin tüm eğitim yıllarındaki grup dersleri de
aynı ön eki alır; sondaki saat eki ("(2)") ve '*' korunur.

İdempotenttir: ön eki zaten olan adlara dokunulmaz. Ön ekli adı havuzda zaten
bulunan (çakışan) bir ders atlanır. Geri alınamaz (ön eki baştan beri taşıyan
adlar ayırt edilemeyeceği için reverse no-op'tur).
"""

import re

from django.db import migrations

ONEK = "SEÇMELİ "

# secmelidersler.models.normalize_ders_adi'nin kopyası — migration'ın modeldeki
# sonraki değişikliklerden etkilenmemesi için burada sabitlenmiştir.
_SAAT_EKI_RE = re.compile(r"\s*\(\d+\)\s*$")
_YILDIZ_EKI_RE = re.compile(r"\s*\*\s*$")


def _taban_ad(ders_adi):
    metin = _SAAT_EKI_RE.sub("", ders_adi)
    metin = _YILDIZ_EKI_RE.sub("", metin)
    return " ".join(metin.split())


def onek_ekle(apps, schema_editor):
    SecmeliDersHavuzu = apps.get_model("secmelidersler", "SecmeliDersHavuzu")
    SecmeliDers = apps.get_model("secmelidersler", "SecmeliDers")

    mevcut = set(SecmeliDersHavuzu.objects.values_list("ders_adi", flat=True))
    yeniden_adlandirilan = set()
    for havuz in SecmeliDersHavuzu.objects.exclude(ders_adi__startswith=ONEK):
        yeni_ad = ONEK + havuz.ders_adi.strip()
        if yeni_ad in mevcut:
            continue
        yeniden_adlandirilan.add(havuz.ders_adi.strip())
        havuz.ders_adi = yeni_ad
        havuz.save(update_fields=["ders_adi"])

    if not yeniden_adlandirilan:
        return
    for ders in SecmeliDers.objects.exclude(ders_adi__startswith=ONEK):
        if _taban_ad(ders.ders_adi) in yeniden_adlandirilan:
            ders.ders_adi = ONEK + ders.ders_adi.strip()
            ders.save(update_fields=["ders_adi"])


class Migration(migrations.Migration):

    dependencies = [
        ("secmelidersler", "0028_secmeliderssubebolunmesi"),
    ]

    operations = [
        migrations.RunPython(onek_ekle, migrations.RunPython.noop),
    ]
