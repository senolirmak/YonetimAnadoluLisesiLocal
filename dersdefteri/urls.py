from django.urls import path
from . import views

app_name = "dersdefteri"

urlpatterns = [
    path("", views.ders_listesi, name="ders_listesi"),
    path("kayit/<int:dp_pk>/", views.kayit_form, name="kayit_form"),
    path("gecmis/", views.gecmis_listesi, name="gecmis_listesi"),
]
