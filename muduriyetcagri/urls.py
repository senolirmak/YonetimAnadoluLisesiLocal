from django.urls import path

from . import views

app_name = "muduriyetcagri"

urlpatterns = [
    # Görüşme
    path("gorusme/", views.gorusme_liste, name="gorusme_liste"),
    path("gorusme/yeni/", views.gorusme_olustur, name="gorusme_olustur"),
    path("gorusme/<int:pk>/", views.gorusme_detay, name="gorusme_detay"),
    path("gorusme/<int:pk>/duzenle/", views.gorusme_duzenle, name="gorusme_duzenle"),
    path("gorusme/<int:pk>/sil/", views.gorusme_sil, name="gorusme_sil"),
]
