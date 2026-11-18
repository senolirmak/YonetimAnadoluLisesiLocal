from django.urls import path

from . import views, views_paket, views_panel

app_name = "tahtalar"

urlpatterns = [
    path("", views_panel.tahta_listesi, name="liste"),
    path("komut/", views_panel.komut_ver, name="komut_ver"),
    path("paket/", views_paket.paket_sayfasi, name="paket"),
    # Tahtada wget ile çekilen süreli, imzalı paket linki (oturum gerektirmez)
    path("paket/indir/<str:token>/", views_paket.paket_link, name="paket_link"),
    # Tahtadaki ajanın uç noktaları (token ile)
    path("api/kayit/", views.kayit, name="api_kayit"),
    path("api/durum/", views.durum, name="api_durum"),
]
