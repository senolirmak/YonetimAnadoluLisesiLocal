from django.urls import path

from . import views

urlpatterns = [
    path("", views.veriaktar_ana, name="veriaktar_ana"),
]
