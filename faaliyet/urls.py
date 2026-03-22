from django.urls import path

from . import views

app_name = "faaliyet"

urlpatterns = [
    # Öğretmen
    path("", views.faaliyet_liste, name="faaliyet_liste"),
    path("yeni/", views.faaliyet_olustur, name="faaliyet_olustur"),
    path("<int:pk>/", views.faaliyet_detay, name="faaliyet_detay"),
    path("<int:pk>/duzenle/", views.faaliyet_duzenle, name="faaliyet_duzenle"),
    path("<int:pk>/sil/", views.faaliyet_sil, name="faaliyet_sil"),
    path("<int:pk>/devamsizlik/", views.faaliyet_devamsizlik, name="faaliyet_devamsizlik"),
    path("<int:pk>/rapor/", views.faaliyet_rapor, name="faaliyet_rapor"),
    path("<int:pk>/rapor/pdf/", views.faaliyet_rapor_pdf, name="faaliyet_rapor_pdf"),
    # AJAX
    path("ders-programi/", views.ders_programi_getir, name="ders_programi_getir"),
    # Müdür Yardımcısı
    path("onay/", views.faaliyet_onay_listesi, name="faaliyet_onay_listesi"),
    path("<int:pk>/onayla/", views.faaliyet_onayla, name="faaliyet_onayla"),
    path("<int:pk>/reddet/", views.faaliyet_reddet, name="faaliyet_reddet"),
]
