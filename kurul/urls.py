from django.urls import path

from . import views, views_toplanti

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
    path("<int:pk>/toplantilar/", views_toplanti.toplantilar, name="toplantilar"),
    path("<int:pk>/karar-defteri.pdf", views_toplanti.karar_defteri, name="karar_defteri"),
    path("toplanti/<int:pk>/", views_toplanti.toplanti_detay, name="toplanti_detay"),
    path("toplanti/<int:pk>/duyuru.pdf", views_toplanti.toplanti_duyuru_pdf, name="toplanti_duyuru_pdf"),
    path("toplanti/<int:pk>/tutanak.pdf", views_toplanti.toplanti_tutanak_pdf, name="toplanti_tutanak_pdf"),
    path("toplanti-takvimi/", views_toplanti.toplanti_takvimi, name="toplanti_takvimi"),
]
