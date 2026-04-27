from django.urls import path

from .views import config_api, etkinlikler, index, kiosk

app_name = "pano"

urlpatterns = [
    path("", index, name="index"),
    path("etkinlikler/", etkinlikler, name="etkinlikler"),
    path("kiosk/", kiosk, name="kiosk"),
    path("api/config/", config_api, name="config_api"),
]
