from django.urls import path

from . import views

app_name = "kurul"

urlpatterns = [
    path("", views.index, name="index"),
    path("yil-kurulumu/", views.yil_kurulumu_view, name="yil_kurulumu"),
    path("katalog/", views.katalog, name="katalog"),
    path("gorev-dagilimi/", views.gorev_yuku_view, name="gorev_yuku"),
    path("gorevlendirme-listesi.pdf", views.gorevlendirme_pdf, name="gorevlendirme_pdf"),
    path("gorevlerim/", views.gorevlerim, name="gorevlerim"),
    path("tur/<slug:kod>/", views.tur_detay, name="tur_detay"),
    path("tur/<slug:kod>/ac/", views.kurul_ac, name="kurul_ac"),
    path("tur/<slug:kod>/tamamla/", views.tur_tamamla, name="tur_tamamla"),
    path("<int:pk>/", views.kurul_detay, name="kurul_detay"),
]
