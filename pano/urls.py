from django.urls import path

from .views import etkinlikler, index, kiosk

app_name = "pano"

urlpatterns = [
    path("", index, name="index"),
    path("etkinlikler/", etkinlikler, name="etkinlikler"),
    path("kiosk/", kiosk, name="kiosk"),
]
