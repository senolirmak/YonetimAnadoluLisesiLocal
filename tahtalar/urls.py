from django.urls import path

from . import views, views_panel

app_name = "tahtalar"

urlpatterns = [
    path("", views_panel.tahta_listesi, name="liste"),
    path("komut/", views_panel.komut_ver, name="komut_ver"),
    # Tahtadaki ajanın uç noktaları (token ile)
    path("api/kayit/", views.kayit, name="api_kayit"),
    path("api/durum/", views.durum, name="api_durum"),
]
