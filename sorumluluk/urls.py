from django.urls import path

from sorumluluk import views

app_name = "sorumluluk"

urlpatterns = [
    # Sınav listesi & oluşturma
    path("",              views.sinav_liste,   name="sinav_liste"),
    path("yeni/",         views.sinav_olustur, name="sinav_olustur"),
    path("<int:pk>/",     views.sinav_detay,   name="sinav_detay"),
    path("<int:pk>/duzenle/", views.sinav_duzenle, name="sinav_duzenle"),
    path("<int:pk>/sil/", views.sinav_sil,     name="sinav_sil"),

    # Öğrenci yönetimi (sınava özgü)
    path("<int:sinav_pk>/ogrenciler/",        views.ogr_liste,  name="ogr_liste"),
    path("<int:sinav_pk>/ogrenci-ekle/",      views.ogr_ekle,   name="ogr_ekle"),
    path("<int:sinav_pk>/ogr-aktar/",         views.ogr_aktar,  name="ogr_aktar"),
    path("ogrenci/<int:pk>/duzenle/",         views.ogr_duzenle, name="ogr_duzenle"),
    path("ogrenci/<int:pk>/sil/",             views.ogr_sil,    name="ogr_sil"),

    # Ders yönetimi (öğrenciye özgü)
    path("ogrenci/<int:ogr_pk>/ders-ekle/",   views.ogr_ders_ekle,     name="ogr_ders_ekle"),
    path("ders/<int:pk>/duzenle/",            views.ogr_ders_duzenle,  name="ogr_ders_duzenle"),
    path("ders/<int:pk>/sil/",               views.ogr_ders_sil,      name="ogr_ders_sil"),

    # Takvim & Rapor
    path("<int:sinav_pk>/takvim/",            views.takvim_detay,      name="takvim_detay"),
    path("<int:sinav_pk>/takvim/olustur/",    views.takvim_olustur,    name="takvim_olustur"),
    path("<int:sinav_pk>/takvim/onayla/",     views.takvim_onayla,     name="takvim_onayla"),
    path("<int:sinav_pk>/takvim/iptal/",      views.takvim_onay_iptal, name="takvim_onay_iptal"),
    path("<int:sinav_pk>/rapor/",             views.rapor,             name="rapor"),
    path("<int:sinav_pk>/rapor/pdf/",         views.rapor_pdf,         name="rapor_pdf"),
    path("<int:sinav_pk>/rapor/imza-pdf/",    views.rapor_imza_pdf,    name="rapor_imza_pdf"),
    path("<int:sinav_pk>/rapor/genel-takvim-pdf/", views.rapor_genel_takvim_pdf, name="rapor_genel_takvim_pdf"),
    path("<int:sinav_pk>/rapor/ogrenci-takvim-pdf/", views.ogrenci_takvim_pdf, name="ogrenci_takvim_pdf"),
]
