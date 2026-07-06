from django.urls import path

from . import views

app_name = "rehberlik"

urlpatterns = [
    # Görüşme
    path("", views.gorusme_liste, name="gorusme_liste"),
    path("yeni/", views.gorusme_olustur, name="gorusme_olustur"),
    path("<int:pk>/", views.gorusme_detay, name="gorusme_detay"),
    path("<int:pk>/duzenle/", views.gorusme_duzenle, name="gorusme_duzenle"),
    path("<int:pk>/sil/", views.gorusme_sil, name="gorusme_sil"),
]
