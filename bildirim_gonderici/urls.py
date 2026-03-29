from django.urls import path

from . import views

app_name = "bildirim"

urlpatterns = [
    path("tahtalar/",                views.tahta_listesi,    name="tahta_listesi"),
    path("tahtalar/ekle/",           views.tahta_ekle,       name="tahta_ekle"),
    path("tahtalar/<int:pk>/duzenle/", views.tahta_duzenle,  name="tahta_duzenle"),
    path("tahtalar/<int:pk>/sil/",   views.tahta_sil,        name="tahta_sil"),
    path("tahtalar/<int:pk>/test/",  views.tahta_test,       name="tahta_test"),
    path("tahtalar/<int:pk>/durum/", views.tahta_durum,      name="tahta_durum"),
    path("gecmis/",                  views.bildirim_gecmisi, name="bildirim_gecmisi"),
]
