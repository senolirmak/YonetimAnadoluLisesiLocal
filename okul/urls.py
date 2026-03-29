# -*- coding: utf-8 -*-
from django.urls import path

from okul import views

app_name = "okul"

urlpatterns = [
    path("ders-havuzu/", views.ders_havuzu_ayarlari, name="ders_havuzu_ayarlari"),
    path("ders-havuzu/kaydet/", views.ders_havuzu_ayarlari_kaydet, name="ders_havuzu_ayarlari_kaydet"),
]
