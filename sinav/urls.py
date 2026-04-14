from django.urls import path
from . import views

app_name = "sinav"

urlpatterns = [
    path("", views.index, name="index"),
    path("veri/", views.veri_yukle_sayfasi, name="veri_yukle_sayfasi"),
    path("veri/yukle/", views.veri_yukle, name="veri_yukle"),
    path("veri/yukle/onayla/", views.veri_yukle_onayla, name="veri_yukle_onayla"),
    path("parametre/kaydet/", views.parametre_kaydet, name="parametre_kaydet"),

    # Gorev tetikleyiciler
    path("calistir/temel-veriler/", views.calistir_temel_veriler, name="temel_veriler"),
    path("calistir/veri-aktar/",    views.calistir_veri_aktar,    name="veri_aktar"),
    path("calistir/subeders/",      views.calistir_subeders,      name="subeders"),
    path("calistir/takvim/",        views.calistir_takvim,        name="takvim"),
    path("calistir/oturma/",         views.calistir_oturma,         name="oturma"),
    path("calistir/oturma-secili/",  views.calistir_oturma_secili,  name="oturma_secili"),
    path("pdf/oturma-plani/",   views.oturma_plani_pdf_view,   name="oturma_plani_pdf_view"),
    path("pdf/sinif-listesi/",  views.sinif_listesi_pdf_view,  name="sinif_listesi_pdf_view"),
    path("pdf/sinav-takvimi/",  views.sinav_takvimi_pdf_view,  name="sinav_takvimi_pdf_view"),

    # Gorev durumu (polling) + iptal
    path("gorev/<str:task_id>/", views.gorev_durumu, name="gorev_durumu"),
    path("gorev/<str:task_id>/iptal/", views.gorev_iptal, name="gorev_iptal"),

    # Okul Bilgileri
    path("okul-bilgileri/kaydet/", views.okul_bilgileri_kaydet, name="okul_bilgileri_kaydet"),

    # Sinav Bilgisi CRUD
    path("sinav-bilgisi/", views.sinav_bilgisi_listesi, name="sinav_bilgisi_listesi"),
    path("sinav-bilgisi/<int:pk>/duzenle/", views.sinav_bilgisi_duzenle, name="sinav_bilgisi_duzenle"),
    path("sinav-bilgisi/<int:pk>/aktif/", views.sinav_bilgisi_aktif_yap, name="sinav_bilgisi_aktif_yap"),
    path("sinav-bilgisi/<int:pk>/sil/", views.sinav_bilgisi_sil, name="sinav_bilgisi_sil"),
    path("takvim-uretim/<int:pk>/aktif/", views.takvim_uretim_aktif_yap, name="takvim_uretim_aktif_yap"),
    path("slot/serbest-birak/",     views.slot_serbest_birak,          name="slot_serbest_birak"),
    path("slot/sil/",               views.takvim_slot_sil,             name="takvim_slot_sil"),
    path("admin/force-aktif/",      views.admin_force_aktif_toggle,    name="admin_force_aktif_toggle"),
    path("gozetmen-ozet/", views.gozetmen_ozet, name="gozetmen_ozet"),

    # Ogrenci Yonetimi
    path("ogrenciler/", views.ogrenci_yonetim, name="ogrenci_yonetim"),
    path("ogrenciler/ekle/", views.ogrenci_ekle, name="ogrenci_ekle"),
    path("ogrenciler/<int:pk>/sil/", views.ogrenci_sil, name="ogrenci_sil"),

    # Ders Ayarlari
    path("ders-ayarlari/", views.ders_ayarlari, name="ders_ayarlari"),
    path("ders-ayarlari/kaydet/", views.ders_ayarlari_kaydet, name="ders_ayarlari_kaydet"),
    path("ders-ayarlari/varsayilan/", views.ders_ayarlari_varsayilan_yukle, name="ders_ayarlari_varsayilan"),
    path("ders-ayarlari/sabit-ekle/", views.sabit_sinav_ekle, name="sabit_sinav_ekle"),
    path("ders-ayarlari/sabit-sil/<int:idx>/", views.sabit_sinav_sil, name="sabit_sinav_sil"),
    path("ders-ayarlari/catisma-ekle/", views.catisma_grubu_ekle, name="catisma_grubu_ekle"),
    path("ders-ayarlari/catisma-sil/<int:idx>/", views.catisma_grubu_sil, name="catisma_grubu_sil"),
    path("ders-ayarlari/catisma-varsayilan/", views.catisma_grubu_varsayilan, name="catisma_grubu_varsayilan"),
    path("ders-ayarlari/esleme-ekle/",         views.esleme_ekle,              name="esleme_ekle"),
    path("ders-ayarlari/esleme-sil/<int:idx>/", views.esleme_sil,              name="esleme_sil"),

    # Ayri sayfalar
    path("takvim/", views.takvim_sayfasi, name="takvim_sayfasi"),
    path("takvim/gecmis/", views.takvim_gecmisi, name="takvim_gecmisi"),
    path("pdf-rapor/", views.pdf_rapor, name="pdf_rapor"),
    path("takvim/gecmis/<int:pk>/sil/", views.takvim_uretim_sil, name="takvim_uretim_sil"),
    path("takvim/gecmis/<int:pk>/kullan/", views.takvim_uretim_kullan, name="takvim_uretim_kullan"),
    path("takvim/onizleme/", views.takvim_onizleme, name="takvim_onizleme"),
    path("takvim/onayla/", views.takvim_onayla, name="takvim_onayla"),
    path("takvim/iptal/", views.takvim_onizleme_iptal, name="takvim_onizleme_iptal"),
    path("takvim/guncelle/", views.takvim_guncelle, name="takvim_guncelle"),
    path("takvim/onizleme/guncelle/", views.takvim_onizleme_guncelle, name="takvim_onizleme_guncelle"),
    path("takvim/ders-duzenle/", views.takvim_ders_duzenle, name="takvim_ders_duzenle"),
    path("yoklama-raporu/", views.sinav_yoklama_raporu, name="sinav_yoklama_raporu"),
    path("yoklama-yok-detay/", views.sinav_yoklama_yok_detay, name="sinav_yoklama_yok_detay"),

    # Öğrenci Sınav Yeri Sorgulama
    path("ogrenci-sinav-yeri/", views.ogrenci_sinav_yeri, name="ogrenci_sinav_yeri"),

    # Mazeret Sınavı
    path("mazeret/",               views.mazeret_sinav_listesi, name="mazeret_listesi"),
    path("mazeret/olustur/",       views.mazeret_sinav_olustur, name="mazeret_olustur"),
    path("mazeret/<int:pk>/",      views.mazeret_sinav_detay,   name="mazeret_detay"),
    path("mazeret/<int:pk>/dagit/", views.mazeret_sinav_dagit,  name="mazeret_dagit"),
    path("mazeret/<int:pk>/sil/",  views.mazeret_sinav_sil,     name="mazeret_sil"),
]
