"""
Eski çağrı tablolarındaki verileri cagri_ogrencicagri tablosuna taşır.
- rehberlik_ogrenci_cagri  → servis='rehberlik'
- disiplin_cagri           → servis='disiplin'
Müdüriyet tablosu henüz üretim verisi içermediğinden taşıma yapılmaz.
"""

from django.db import migrations


def ileri(apps, schema_editor):
    OgrenciCagri = apps.get_model("cagri", "OgrenciCagri")
    db = schema_editor.connection

    # ── Rehberlik ──────────────────────────────────────────────────────────
    with db.cursor() as cur:
        cur.execute("""
            SELECT id, tarih, ders_saati, ders_adi, ogretmen_adi,
                   cagri_metni, olusturma_zamani,
                   ogrenci_id, rehber_id, gorusme_id
            FROM rehberlik_ogrenci_cagri
        """)
        rows = cur.fetchall()

    OgrenciCagri.objects.bulk_create(
        [
            OgrenciCagri(
                servis="rehberlik",
                tarih=r[1],
                ders_saati=r[2],
                ders_adi=r[3] or "",
                ogretmen_adi=r[4] or "",
                cagri_metni=r[5] or "",
                ogrenci_id=r[7],
                kayit_eden_id=r[8],  # rehber_id → kayit_eden (NobetPersonel)
                gorusme_rehberlik_id=r[9],
            )
            for r in rows
        ]
    )

    # ── Disiplin ───────────────────────────────────────────────────────────
    with db.cursor() as cur:
        cur.execute("""
            SELECT id, tarih, ders_saati, ders_adi, ogretmen_adi,
                   cagri_metni, olusturma_zamani,
                   ogrenci_id, kayit_eden_id, gorusme_id
            FROM disiplin_cagri
        """)
        rows = cur.fetchall()

    OgrenciCagri.objects.bulk_create(
        [
            OgrenciCagri(
                servis="disiplin",
                tarih=r[1],
                ders_saati=r[2],
                ders_adi=r[3] or "",
                ogretmen_adi=r[4] or "",
                cagri_metni=r[5] or "",
                ogrenci_id=r[7],
                kayit_eden_id=r[8],
                gorusme_disiplin_id=r[9],
            )
            for r in rows
        ]
    )


def geri(apps, schema_editor):
    OgrenciCagri = apps.get_model("cagri", "OgrenciCagri")
    OgrenciCagri.objects.filter(servis__in=["rehberlik", "disiplin"]).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("cagri", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(ileri, geri),
    ]
