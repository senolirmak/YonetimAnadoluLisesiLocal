from django.urls import path

from . import views

app_name = "ogrencinobet"

urlpatterns = [
    path("nobetci/", views.nobetci_form, name="nobetci_form"),
]
