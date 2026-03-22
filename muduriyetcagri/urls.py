from django.urls import path

from cagri import views as cagri_views

from . import views

app_name = "muduriyetcagri"

urlpatterns = [
    # Çağrı (cagri app'inden servis='muduriyetcagri' ile)
    path("", cagri_views.cagri_liste, {"servis": "muduriyetcagri"}, name="cagri_liste"),
    path("yeni/", cagri_views.cagri_olustur, {"servis": "muduriyetcagri"}, name="cagri_olustur"),
    path("<int:pk>/sil/", cagri_views.cagri_sil, name="cagri_sil"),
    path("<int:pk>/yazdir/", cagri_views.cagri_yazdir, name="cagri_yazdir"),
    # Görüşme
    path("gorusme/", views.gorusme_liste, name="gorusme_liste"),
    path("gorusme/yeni/", views.gorusme_olustur, name="gorusme_olustur"),
    path("gorusme/<int:pk>/", views.gorusme_detay, name="gorusme_detay"),
    path("gorusme/<int:pk>/duzenle/", views.gorusme_duzenle, name="gorusme_duzenle"),
    path("gorusme/<int:pk>/sil/", views.gorusme_sil, name="gorusme_sil"),
]
