from django.urls import path

from . import views

app_name = "ogrenci"

urlpatterns = [
    path("", views.ogrenci_liste, name="ogrenci_liste"),
    path("<int:pk>/detay/", views.ogrenci_detay_duzenle, name="ogrenci_detay_duzenle"),
    path("excel-yukle/", views.excel_yukle, name="excel_yukle"),
    path("sureksiz-devamsiz/", views.sureksiz_devamsiz_listesi, name="sureksiz_devamsiz_listesi"),
    path("<int:pk>/sureksiz-toggle/", views.sureksiz_devamsiz_toggle, name="sureksiz_devamsiz_toggle"),
    path("<int:pk>/muaf/", views.ogrenci_muaf_duzenle, name="ogrenci_muaf_duzenle"),
    path("yeni-kayit/<int:sinif>/", views.yeni_kayit_hub, name="yeni_kayit_hub"),
    path("yeni-kayit/<int:sinif>/<str:sube>/", views.yeni_kayit_liste, name="yeni_kayit_liste"),
    path("yeni-kayit/<int:sinif>/<str:sube>/ekle/", views.yeni_kayit_ekle, name="yeni_kayit_ekle"),
    path("yeni-kayit/duzenle/<int:pk>/", views.yeni_kayit_duzenle, name="yeni_kayit_duzenle"),
    path("yeni-kayit/sil/<int:pk>/", views.yeni_kayit_sil, name="yeni_kayit_sil"),
    path("ayrilma/", views.ayrilma_listesi, name="ayrilma_listesi"),
    path("ayrilma/ekle/", views.ayrilma_ekle, name="ayrilma_ekle"),
    path("ayrilma/<int:pk>/duzenle/", views.ayrilma_duzenle, name="ayrilma_duzenle"),
    path("ayrilma/<int:pk>/sil/", views.ayrilma_sil, name="ayrilma_sil"),
]
