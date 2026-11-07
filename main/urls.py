from django.urls import path

from main import views as main_views
from nobet import views as nobet_views
from okul.views import okul_ayarlari
from sinav.views_ogretmen import (
    ogretmen_gozetim_sinif_listesi,
    ogretmen_ogrenci_sinav_takvimi,
    ogretmen_sinav_gozetim,
    ogretmen_sinav_medya,
    ogretmen_yoklama_raporum,
    sinav_oturum_istatistik,
    sinav_salon_yoklama,
    sinif_oturma_plani,
    sinif_oturma_plani_pdf,
)
from sorumluluk.views import ogretmen_sorumluluk_gorevleri

urlpatterns = [
    path("", main_views.index, name="index"),
    path("gorevlerim/", main_views.gorevlerim, name="gorevlerim"),
    path(
        "devamsizlik-nobet/",
        main_views.devamsizlik_nobet_islemleri,
        name="devamsizlik_nobet_islemleri",
    ),
    path(
        "ders-programi-islemleri/",
        main_views.ders_programi_islemleri,
        name="ders_programi_islemleri",
    ),
    path("ogrenci-islemleri/", main_views.ogrenci_islemleri, name="ogrenci_islemleri"),
    path("sinav-islemleri/", main_views.sinav_islemleri, name="sinav_islemleri"),
    path("yonetim-paneli/", main_views.yonetim_paneli, name="yonetim_paneli"),
    path("bilgi-panosu/", main_views.bilgi_panosu, name="bilgi_panosu"),
    path(
        "yerel-ca-sertifikasi/",
        main_views.yerel_ca_sertifikasi_indir,
        name="yerel_ca_sertifikasi_indir",
    ),
    path("nobet/haftalik/", nobet_views.ogretmen_haftalik_nobet, name="ogretmen_haftalik_nobet"),
    path("nobet/gunun-nobetcileri/", nobet_views.ogretmen_gunun_nobetcileri, name="ogretmen_gunun_nobetcileri"),
    path("nobet/ders-doldurma/", nobet_views.ogretmen_ders_doldurma, name="ogretmen_ders_doldurma"),
    path("nobet/ders-doldurma/istatistik/", nobet_views.nobetci_ders_doldurma_istatistik, name="nobetci_ders_doldurma_istatistik"),
    path("sinav/gozetim/", ogretmen_sinav_gozetim, name="ogretmen_sinav_gozetim"),
    path("sinav/medya/", ogretmen_sinav_medya, name="ogretmen_sinav_medya"),
    path("sinav/gozetim/sinif-listesi/", ogretmen_gozetim_sinif_listesi, name="ogretmen_gozetim_sinif_listesi"),
    path("sinav/gozetim/salon-yoklama/", sinav_salon_yoklama, name="sinav_salon_yoklama"),
    path("sinav/istatistik/", sinav_oturum_istatistik, name="sinav_oturum_istatistik"),
    path("sinav/yoklama-raporum/", ogretmen_yoklama_raporum, name="ogretmen_yoklama_raporum"),
    # "sinav/sorumluluk-gorevlerim/" sinav.urls tarafından gölgeleniyordu (config/urls.py
    # sırası) ve öğretmen Ortak Sınav yönetim çerçevesine düşüyordu; bu yüzden ayrı adres.
    path("gorevlerim/sorumluluk-sinavi/", ogretmen_sorumluluk_gorevleri, name="ogretmen_sorumluluk_gorevleri"),
    path("sinav/ogrenci-sinav-takvimi/", ogretmen_ogrenci_sinav_takvimi, name="ogretmen_ogrenci_sinav_takvimi"),
    path("okul-ayarlari/", okul_ayarlari, name="okul_ayarlari"),
    path("sinif/oturma-plani/", sinif_oturma_plani, name="sinif_oturma_plani"),
    path("sinif/oturma-plani/pdf/", sinif_oturma_plani_pdf, name="sinif_oturma_plani_pdf"),
]
