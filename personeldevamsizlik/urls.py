from django.urls import path

from . import views

urlpatterns = [
    path("", views.DevamsizlikListView.as_view(), name="devamsizlik_list"),
    path("yeni/", views.DevamsizlikCreateView.as_view(), name="devamsizlik_create"),
    path("<int:pk>/duzenle/", views.DevamsizlikUpdateView.as_view(), name="devamsizlik_update"),
    path("<int:pk>/sil/", views.DevamsizlikDeleteView.as_view(), name="devamsizlik_delete"),
]
