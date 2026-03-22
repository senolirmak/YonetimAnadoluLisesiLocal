from django.urls import path

from . import views

app_name = "cagri"

urlpatterns = [
    path("api/ders-programi/", views.ders_programi_api, name="ders_programi_api"),
    path("<int:pk>/sil/", views.cagri_sil, name="cagri_sil"),
    path("<int:pk>/yazdir/", views.cagri_yazdir, name="cagri_yazdir"),
]
