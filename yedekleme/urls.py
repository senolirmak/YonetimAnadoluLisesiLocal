from django.urls import path

from yedekleme import views

app_name = "yedekleme"

urlpatterns = [
    path("", views.yedek_listesi, name="yedek_listesi"),
    path("olustur/", views.yedek_olustur, name="yedek_olustur"),
    path("yukle/", views.yedek_yukle, name="yedek_yukle"),
    path("geri-yukle/", views.yedek_geri_yukle, name="yedek_geri_yukle"),
    path("<str:dosya_adi>/indir/", views.yedek_indir, name="yedek_indir"),
    path("<str:dosya_adi>/sil/", views.yedek_sil_onay, name="yedek_sil_onay"),
    path("<str:dosya_adi>/sil/onayla/", views.yedek_sil, name="yedek_sil"),
    path("<str:dosya_adi>/geri-yukle/onay/", views.yedek_geri_yukle_onay, name="yedek_geri_yukle_onay"),

    # Medya (media/) yedekleri
    path("medya/olustur/", views.medya_yedek_olustur, name="medya_yedek_olustur"),
    path("medya/yukle/", views.medya_yedek_yukle, name="medya_yedek_yukle"),
    path("medya/geri-yukle/", views.medya_yedek_geri_yukle, name="medya_yedek_geri_yukle"),
    path("medya/<str:dosya_adi>/indir/", views.medya_yedek_indir, name="medya_yedek_indir"),
    path("medya/<str:dosya_adi>/sil/", views.medya_yedek_sil_onay, name="medya_yedek_sil_onay"),
    path("medya/<str:dosya_adi>/sil/onayla/", views.medya_yedek_sil, name="medya_yedek_sil"),
    path(
        "medya/<str:dosya_adi>/geri-yukle/onay/",
        views.medya_yedek_geri_yukle_onay, name="medya_yedek_geri_yukle_onay",
    ),
]
