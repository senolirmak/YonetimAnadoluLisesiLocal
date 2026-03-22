from django.urls import path

from . import views

urlpatterns = [
    path("dagitim/", views.nobet_dagitim, name="nobet_dagitim"),
    path("ders-doldurma/", views.nobet_ders_doldurma, name="nobet_ders_doldurma"),
    path("ders-doldurma/pdf/", views.download_ders_doldurma_pdf, name="download_ders_doldurma_pdf"),
    path("ders-doldurma/png/", views.download_ders_doldurma_png, name="download_ders_doldurma_png"),
    path(
        "ders-doldurma/xlsx/", views.download_ders_doldurma_xlsx, name="download_ders_doldurma_xlsx"
    ),
    path("manuel-dagitim/", views.manuel_dagitim, name="manuel_dagitim"),
    path("gunun-nobetcileri/", views.gunun_nobetcileri, name="gunun_nobetcileri"),
    path(
        "gunun-nobetcileri/png/",
        views.download_gunun_nobetcileri_png,
        name="download_gunun_nobetcileri_png",
    ),
    path(
        "ders-doldurma/unassigned/png/",
        views.download_unassigned_ders_png,
        name="download_unassigned_ders_png",
    ),
    path("devamsizlik-sinif-pdf/", views.devamsizlik_sinif_pdf, name="devamsizlik_sinif_pdf"),
]
