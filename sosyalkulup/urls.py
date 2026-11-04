from django.urls import path

from . import views

app_name = "sosyalkulup"

urlpatterns = [
    path("", views.kulup_listesi, name="kulup_listesi"),
    path("danisman-ogretmenler/", views.danisman_ogretmenler, name="danisman_ogretmenler"),
    path("excel-yukle/", views.kulup_excel_yukle, name="kulup_excel_yukle"),
    path("kulup/<int:pk>/ogrenciler/", views.kulup_ogrencileri, name="kulup_ogrencileri"),
    path("kulup/<int:pk>/ogrenciler/pdf/", views.kulup_ogrencileri_pdf, name="kulup_ogrencileri_pdf"),
    path("ogrenci-kulup/", views.ogrenci_kulup_belirle, name="ogrenci_kulup_belirle"),
    path("ogrenci-kulup/pdf/", views.ogrenci_kulup_pdf, name="ogrenci_kulup_pdf"),
]
