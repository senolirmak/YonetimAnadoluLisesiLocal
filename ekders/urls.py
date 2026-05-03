from django.urls import path

from ekders import views

app_name = "ekders"

urlpatterns = [
    path("",                                   views.donem_listesi,       name="donem_listesi"),
    path("yeni/",                              views.donem_olustur,       name="donem_olustur"),
    path("<int:pk>/",                          views.donem_detay,         name="donem_detay"),
    path("<int:pk>/duzenle/",                  views.donem_duzenle,       name="donem_duzenle"),
    path("<int:pk>/hesapla/",                  views.donem_hesapla_view,  name="donem_hesapla"),
    path("<int:pk>/onayla/",                   views.donem_onayla,        name="donem_onayla"),
    path("<int:pk>/kayit/<int:kayit_pk>/",     views.hafta_duzenle,       name="hafta_duzenle"),
    path("tatil/",                             views.tatil_listesi,       name="tatil_listesi"),
    path("tatil/<int:pk>/sil/",               views.tatil_sil,           name="tatil_sil"),
]
