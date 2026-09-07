from django.urls import path

from . import views

app_name = "ebagiris"

urlpatterns = [
    path("giris/baslat/", views.eba_giris_baslat, name="eba_giris_baslat"),
    path("giris/durum/<str:token>/", views.eba_giris_durum, name="eba_giris_durum"),
    path("baglama/baslat/", views.eba_baglama_baslat, name="eba_baglama_baslat"),
    path("baglama/durum/<str:token>/", views.eba_baglama_durum, name="eba_baglama_durum"),
    path("baglama/kaldir/", views.eba_baglama_kaldir, name="eba_baglama_kaldir"),
]
