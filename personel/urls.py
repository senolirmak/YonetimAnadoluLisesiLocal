from django.urls import path

from . import views

urlpatterns = [
    path("", views.personel_listesi, name="personel_listesi"),
    path("<int:pk>/duzenle/", views.personel_duzenle, name="personel_duzenle"),
    path("<int:pk>/sil/", views.personel_sil, name="personel_sil"),
    path("kullanicilari/", views.ogretmen_kullanici_listesi, name="ogretmen_kullanici_listesi"),
    path(
        "kullanicilari/<int:personel_pk>/olustur/",
        views.ogretmen_kullanici_olustur,
        name="ogretmen_kullanici_olustur",
    ),
    path(
        "kullanicilari/<int:personel_pk>/kaldir/",
        views.ogretmen_kullanici_kaldir,
        name="ogretmen_kullanici_kaldir",
    ),
]
