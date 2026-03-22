from django.urls import path

from . import views

urlpatterns = [
    path("", views.duyuru_listesi, name="duyuru_listesi"),
    path("ekle/", views.duyuru_ekle, name="duyuru_ekle"),
    path("duzenle/<int:pk>/", views.DuyuruUpdateView.as_view(), name="duyuru_duzenle"),
    path("sil/<int:pk>/", views.DuyuruDeleteView.as_view(), name="duyuru_sil"),
    path(
        "api/<int:sinif_id>/<str:tarih_str>/<int:ders_saati>/",
        views.aktif_duyuru_getir_api,
        name="aktif_duyuru_getir_api",
    ),
]
