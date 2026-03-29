from datetime import time as dtime

from django.db import migrations


def saat_str_to_time(saat_str):
    """'HH:MM' formatındaki string'i time nesnesine çevirir."""
    parts = saat_str.split(":")
    return dtime(int(parts[0]), int(parts[1]))


def takvim_ders_saati_ata(apps, schema_editor):
    """
    Her Takvim kaydının saat CharField'ını (ör. '08:50') eşleşen
    DersSaatleri kaydına (derssaati_baslangic) bağlar.

    Eşleşme bulunamazsa ders_saati None kalır; kayıt yine de geçerlidir.
    """
    Takvim = apps.get_model("sinav", "Takvim")
    DersSaatleri = apps.get_model("sinav", "DersSaatleri")

    # Tüm DersSaatleri kayıtlarını başlangıç saatine göre indexle
    ds_map = {
        ds.derssaati_baslangic: ds
        for ds in DersSaatleri.objects.all()
    }

    guncellenen = 0
    eslesmeyen = set()

    for takvim in Takvim.objects.filter(ders_saati__isnull=True).exclude(saat=""):
        try:
            saat_obj = saat_str_to_time(takvim.saat)
        except (ValueError, IndexError):
            eslesmeyen.add(takvim.saat)
            continue

        ds = ds_map.get(saat_obj)
        if ds:
            takvim.ders_saati = ds
            takvim.save(update_fields=["ders_saati"])
            guncellenen += 1
        else:
            eslesmeyen.add(takvim.saat)

    if eslesmeyen:
        print(
            f"\n  [0041] Uyarı: {len(eslesmeyen)} saat değeri için DersSaatleri eşleşmesi bulunamadı: "
            + ", ".join(sorted(eslesmeyen))
        )
    print(f"\n  [0041] {guncellenen} Takvim kaydına ders_saati atandı.")


def ders_saati_temizle(apps, schema_editor):
    """Geri alma: ders_saati FK'larını None yap."""
    Takvim = apps.get_model("sinav", "Takvim")
    Takvim.objects.update(ders_saati=None)


class Migration(migrations.Migration):

    dependencies = [
        ("sinav", "0040_add_takvim_ders_saati_fk"),
    ]

    operations = [
        migrations.RunPython(
            takvim_ders_saati_ata,
            reverse_code=ders_saati_temizle,
        ),
    ]
