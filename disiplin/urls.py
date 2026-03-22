from django.urls import path

from cagri import views as cagri_views

from . import views

app_name = "disiplin"

urlpatterns = [
    # Görüşme
    path("", views.gorusme_liste, name="gorusme_liste"),
    path("yeni/", views.gorusme_olustur, name="gorusme_olustur"),
    path("<int:pk>/", views.gorusme_detay, name="gorusme_detay"),
    path("<int:pk>/duzenle/", views.gorusme_duzenle, name="gorusme_duzenle"),
    path("<int:pk>/sil/", views.gorusme_sil, name="gorusme_sil"),
    # Çağrı (cagri app'inden servis='disiplin' ile)
    path("cagri/", cagri_views.cagri_liste, {"servis": "disiplin"}, name="cagri_liste"),
    path("cagri/olustur/", cagri_views.cagri_olustur, {"servis": "disiplin"}, name="cagri_olustur"),
    path("cagri/<int:pk>/sil/", cagri_views.cagri_sil, name="cagri_sil"),
    path("cagri/<int:pk>/yazdir/", cagri_views.cagri_yazdir, name="cagri_yazdir"),
    # API
    path("api/ders-programi/", views.ders_programi_api, name="ders_programi_api"),
]
