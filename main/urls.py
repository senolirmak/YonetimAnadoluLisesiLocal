from django.urls import path

from main import views as main_views
from nobet import views as nobet_views
from sinav.views_ogretmen import (
    ogretmen_gozetim_sinif_listesi,
    ogretmen_ogrenci_sinav_takvimi,
    ogretmen_sinav_gozetim,
    ogretmen_sinav_medya,
    ogretmen_yoklama_raporum,
    sinav_oturum_istatistik,
    sinav_salon_yoklama,
    sinif_oturma_plani,
)
from sorumluluk.views import ogretmen_sorumluluk_gorevleri
from okul.views import okul_ayarlari

urlpatterns = [
    path("", main_views.index, name="index"),
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
    path("sinav/sorumluluk-gorevlerim/", ogretmen_sorumluluk_gorevleri, name="ogretmen_sorumluluk_gorevleri"),
    path("sinav/ogrenci-sinav-takvimi/", ogretmen_ogrenci_sinav_takvimi, name="ogretmen_ogrenci_sinav_takvimi"),
    path("okul-ayarlari/", okul_ayarlari, name="okul_ayarlari"),
    path("sinif/oturma-plani/", sinif_oturma_plani, name="sinif_oturma_plani"),
]
