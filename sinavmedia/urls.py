from django.urls import path
from . import views

app_name = "sinavmedia"

urlpatterns = [
    path("", views.yonetim, name="yonetim"),
    path("yukle/<int:takvim_pk>/<int:seviye>/", views.yukle, name="yukle"),
    path("serbest/<int:pk>/", views.serbest_toggle, name="serbest_toggle"),
    path("sil/<int:pk>/", views.sil, name="sil"),
    path("oynat/<int:pk>/", views.oynat, name="oynat"),
]
