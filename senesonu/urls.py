from django.urls import path

from . import views

app_name = "senesonu"

urlpatterns = [
    path("", views.gecis_listesi, name="gecis_listesi"),
    path("olustur/", views.gecis_olustur, name="gecis_olustur"),
    path("<int:pk>/", views.gecis_detay, name="gecis_detay"),
    path("<int:pk>/uygula/", views.gecis_uygula, name="gecis_uygula"),
    path("<int:pk>/sil/", views.gecis_sil, name="gecis_sil"),
    path("satir/<int:pk>/duzenle/", views.satir_duzenle, name="satir_duzenle"),
]
