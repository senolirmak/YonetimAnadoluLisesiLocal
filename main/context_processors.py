from pathlib import Path

from django.conf import settings

from okul.auth import is_ust_yonetici as _is_ust_yonetici
from okul.auth import rol_bayraklari


def kullanici_rol(request):
    """Tüm template'lerde kullanıcı rol bilgilerini erişilebilir kılar (kurallar: okul.auth)."""
    b = rol_bayraklari(request.user)
    bekleyen_faaliyet = 0
    if b["mudur_yardimcisi"]:
        from faaliyet.models import Faaliyet

        bekleyen_faaliyet = Faaliyet.objects.filter(durum=Faaliyet.DURUM_BEKLEMEDE).count()
    return {
        "is_mudur_yardimcisi": b["mudur_yardimcisi"],
        "is_yonetici": b["yonetici"],
        "is_tarih_degistirebilir": b["ust_yonetici"],
        "bekleyen_faaliyet_sayisi": bekleyen_faaliyet,
        "is_rehber_ogretmen": b["rehber_ogretmen"],
        "is_disiplin_kurulu": b["disiplin_kurulu"],
        "is_ogretmen": b["salt_ogretmen"],
        # ogretmen + rehber_ogretmen + disiplin_kurulu → öğretmen görev sayfaları
        "is_ogretmen_menu": b["ogretmen_menu"],
    }


def yerel_ca_bilgisi(request):
    """Sunucu, kendi yerel CA'sıyla imzalı bir sertifikayla HTTPS'e geçirildiyse
    (bkz. kurulumcu/sertifika.py, HTTPS_ETKIN) giriş/ana sayfalarda CA'nın
    genel sertifikasını indirme bağlantısını göstermek için kullanılır — bkz.
    main.views.yerel_ca_sertifikasi_indir. Anonim ziyaretçiler dahil TÜM
    template'lere enjekte edilir (giriş sayfası, güvene henüz kavuşmamış bir
    tarayıcının ilk indireceği yer olduğundan kimlik doğrulaması gerektirmez).
    """
    dosya_var = (Path(settings.BASE_DIR) / "yerel-ca-sertifikasi.crt").is_file()
    return {"yerel_ca_indirilebilir": getattr(settings, "HTTPS_ETKIN", False) and dosya_var}


# ── Kalıcı sol menüler ────────────────────────────────────────────────────
# Bir sayfa bir menüye aitse layouts/base.html içeriği menüyle birlikte çizer
# (bkz. includes/yan_menu.html). `yan_menu` şablon yolunu, `*_menu` ise o
# menünün verisini taşır.

# Öğretmen "Görevlerim" menüsünün gösterildiği sayfalar (URL adları)
GOREV_MENUSU_SAYFALARI = {
    "gorevlerim",
    "haftalik_ders_programi",
    "ogretmen_haftalik_nobet",
    "ogretmen_ders_doldurma",
    "ogretmen_sinav_gozetim",
    "ogretmen_sorumluluk_gorevleri",
    "ogretmen_ogrenci_sinav_takvimi",
    "sosyalkulup:kulup_ogrencileri",
    # Sınav gözetim sayfasından açılan alt sayfalar
    "ogretmen_gozetim_sinif_listesi",
    "sinav_salon_yoklama",
    "ogretmen_yoklama_raporum",
    "ogretmen_sinav_medya",
    # Atanan / Atanamayan Dersler sayfasından açılan istatistik
    "nobetci_ders_doldurma_istatistik",
    "kurul:gorevlerim",
}

# Yönetici "Devamsızlık ve Nöbet İşlemleri" menüsünün gösterildiği sayfalar
NOBET_MENUSU_SAYFALARI = {
    "devamsizlik_nobet_islemleri",
    "devamsizlik_list",
    "devamsizlik_create",
    "devamsizlik_update",
    "devamsizlik_delete",
    "nobet_dagitim",
    "manuel_dagitim",
    "gunun_nobetcileri",
    "nobet_ders_doldurma",
    "nobetci_ders_doldurma_istatistik",
    "nobet_gorevi_listesi",
}

# Yönetici "Ders Programı İşlemleri" menüsünün gösterildiği sayfalar.
# `haftalik_ders_programi` Görevlerim menüsünde de var: öğretmen rolündeki
# kullanıcılarda (rehber öğretmen vb.) orada Görevlerim menüsü önceliklidir.
DERS_PROGRAMI_MENUSU_SAYFALARI = {
    "ders_programi_islemleri",
    "dersprogrami_listesi",
    "ogretmen_program",
    "sinif_program",
    "fet_kopru",
    "sinif_ogretmenleri",
    "haftalik_ders_programi",
    "dersdefteri:ders_listesi",
    "dersdefteri:gecmis_listesi",
    "dersdefteri:kayit_form",
    "rehber_ogretmenler",
    "sosyalkulup:danisman_ogretmenler",
}

# "Öğrenci İşleri" menüsünün gösterildiği sayfalar — ana sayfadaki bölüm gibi
# tüm kullanıcılara açıktır; bağlantılar menüde rol koşuluyla süzülür.
# `sosyalkulup:kulup_ogrencileri` Görevlerim menüsünde de var: öğretmen
# rolündekilerde orada Görevlerim menüsü önceliklidir.
OGRENCI_MENUSU_SAYFALARI = {
    "ogrenci_islemleri",
    "ogrenci:ogrenci_liste",
    "ogrenci:ogrenci_detay_duzenle",
    "ogrenci:sureksiz_devamsiz_listesi",
    "ogrenci:ogrenci_muaf_duzenle",
    "ogrenci:ayrilma_listesi",
    "ogrenci:ayrilma_ekle",
    "ogrenci:ayrilma_duzenle",
    "ogrenci:ayrilma_sil",
    "sinif_oturma_plani",
    "sosyalkulup:ogrenci_kulup_belirle",
    "sosyalkulup:kulup_listesi",
    "sosyalkulup:kulup_excel_yukle",
    "sosyalkulup:kulup_ogrencileri",
    "ogrencinobet:nobetci_form",
    "devamsizlik:ogrenci_devamsizlik_listesi",
    "devamsizlik:ogrenci_devamsizlik_pdf",
    # Faaliyetler (öğretmenin kendi faaliyetleri; onay/yönetim sayfaları Yönetim Paneli'nde)
    "faaliyet:faaliyet_liste",
    "faaliyet:faaliyet_olustur",
    "faaliyet:faaliyet_detay",
    "faaliyet:faaliyet_duzenle",
    "faaliyet:faaliyet_sil",
    "faaliyet:faaliyet_devamsizlik",
    "faaliyet:faaliyet_rapor",
}

# Müdür yardımcısı "Sınav İşlemleri" menüsünün gösterildiği tekil sayfalar...
SINAV_MENUSU_SAYFALARI = {
    "sinav_islemleri",
    "sinav:ogrenci_sinav_yeri",
    "sinav_oturum_istatistik",
    "sinav:sinav_yoklama_raporu",
    "sinav:sinav_yoklama_yok_detay",
}

# ...ve bütün sayfalarında menünün kalıcı olduğu modüller (URL ad alanı → menüde
# vurgulanacak modül bağlantısı). Modüllerin kendi üst gezinme çubukları da durur.
SINAV_MENUSU_MODULLERI = {
    "sinav": "sinav:index",
    "sorumluluk": "sorumluluk:sinav_liste",
    "sinavmedia": "sinav:index",  # Sınav Medya, Ortak Sınav alt menüsünde
}

# Modül içinde olup menünün gösterilmediği sayfalar: sınıfta tahtaya yansıtılan
# tam ekran medya oynatıcısı.
SINAV_MENUSU_HARIC = {"sinavmedia:oynat"}

# Müdür yardımcısı "Yönetim Paneli" menüsünün gösterildiği sayfalar...
YONETIM_MENUSU_SAYFALARI = {
    "yonetim_paneli",
    "okul_ayarlari",
    "personel_listesi",
    "personel_duzenle",
    "personel_sil",
    "veriaktar_ana",
    "faaliyet:faaliyet_onay_listesi",
    "faaliyet:faaliyet_yonetim_listesi",
    "faaliyet:faaliyet_toplu_rapor",
    "faaliyet:faaliyet_ogrenci_rapor",
}

# ...ve bütün sayfalarında menünün kalıcı olduğu bölümler (URL ad alanı → menüde
# vurgulanacak bağlantı). `okul` ad alanında yalnızca "yonetim" (CRUD) sayfaları
# sayılır; Ders Havuzu ayarları Ortak Sınav ders ayarlarından açılır.
YONETIM_MENUSU_MODULLERI = {
    "yedekleme": "yedekleme:yedek_listesi",
    "senesonu": "senesonu:gecis_listesi",
    "kurul": "kurul:index",
}
YONETIM_MENUSU_OKUL_SAYFALARI = {
    "okul:yonetim_index",
    "okul:yonetim_list",
    "okul:yonetim_create",
    "okul:yonetim_update",
    "okul:yonetim_delete",
    "okul:sinif_sube_yil_ata",
    "okul:sinif_sube_yil_sil",
    "okul:personel_okutma_yetkisi_ata",
}

# Müdür yardımcısı "Seçmeli Dersler" menüsü: `secmelidersler` ve `ogrencidersleri`
# app'lerinin bütün sayfalarında (ad alanları olmadığından view modülüne göre
# tanınır) ve Seçmeli Dersler'den açılan 9. sınıf yeni kayıt sayfalarında.
SECMELI_MENUSU_UYGULAMALARI = ("secmelidersler.", "ogrencidersleri.")
SECMELI_MENUSU_ON_EKLERI = ("ogrenci:yeni_kayit_",)

# Seçmeli sayfasının menüde vurgulanacak bağlantısı: URL adı ön ekine göre, ilk
# eşleşen kazanır (özelden genele sıralı).
SECMELI_UST_ON_EKLERI = (
    ("ogrdrs_", "ogrdrs_listesi"),
    ("ogrenci:yeni_kayit_", "ogrenci:yeni_kayit_hub"),
    ("secmeli_sinif_toplam_saat", "secmeli_sinif_toplam_saat"),
    ("secmeli_sinif_dagilimi", "secmeli_sinif_dagilimi"),
    ("secmeli_ortak_ders_", "secmeli_ortak_ders_listesi"),
    ("ortak_havuz_", "ortak_havuz_listesi"),
    ("secmeli_havuz_", "secmeli_havuz_listesi"),
    ("secmeli_alan_sube_", "secmeli_ders_yuku"),
    ("secmeli_yonetici_ders_yuku", "secmeli_ders_yuku"),
    ("secmeli_brans_paylasimi", "secmeli_ders_yuku"),
    ("secmeli_ders_brans_", "secmeli_ders_yuku"),
    ("secmeli_ders_sube_bol", "secmeli_ders_yuku"),
    ("secmeli_norm_kadro_", "secmeli_ders_yuku"),
    ("secmeli_ders_yuku", "secmeli_ders_yuku"),
    ("secmeli_alan_", "secmeli_alan_listesi"),
    ("secmeli_grup_", "secmeli_grup_listesi"),
    ("secmeli_ders_", "secmeli_grup_listesi"),
    ("ortalama_", "ortalama_listesi"),
    ("sinif_tekrari_", "sinif_tekrari_listesi"),
    ("tasdikname_", "tasdikname_listesi"),
)


# Kendi menüsü olmayan sayfalar: ana menüyle gösterilir. Değer, menüde vurgulanacak
# bağlantıdır. Ad alanının bütün sayfaları için anahtar "ad_alani:*" biçimindedir.
ANA_MENU_SAYFALARI = {
    "duyuru_listesi": "duyuru_listesi",
    "duyuru_ekle": "duyuru_listesi",
    "duyuru_duzenle": "duyuru_listesi",
    "duyuru_sil": "duyuru_listesi",
    "ogretmen_kullanici_listesi": "ogretmen_kullanici_listesi",
    "ogretmen_kullanici_olustur": "ogretmen_kullanici_listesi",
    "ogretmen_kullanici_onayla": "ogretmen_kullanici_listesi",
    "ogretmen_kullanici_kaldir": "ogretmen_kullanici_listesi",
    "devamsizlik:ogretmen_devamsizlik": "devamsizlik:ogretmen_devamsizlik",
    "devamsizlik:ogretmen_devamsizlik_ders": "devamsizlik:ogretmen_devamsizlik",
    "ogretmen_gunun_nobetcileri": "ogretmen_gunun_nobetcileri",
    "profil": None,
    "muduriyetcagri:*": "muduriyetcagri:gorusme_liste",
    "rehberlik:*": "rehberlik:gorusme_liste",
    "disiplin:*": "disiplin:gorusme_liste",
    # Yöneticilerde Ders Programı menüsüyle gösterilir; öğretmende buraya düşer
    "dersdefteri:*": "dersdefteri:ders_listesi",
    # Devamsızlık ve Nöbet menüsü yalnızca üst yöneticilerde; bu sayfaları açabilen
    # rehber öğretmen / disiplin kurulu buraya düşer
    "nobet_dagitim": None,
    "gunun_nobetcileri": None,
    "nobet_ders_doldurma": None,
}


def _ana_menu(request, sayfa, namespace):
    if sayfa in ANA_MENU_SAYFALARI:
        aktif_bag = ANA_MENU_SAYFALARI[sayfa]
    elif f"{namespace}:*" in ANA_MENU_SAYFALARI:
        aktif_bag = ANA_MENU_SAYFALARI[f"{namespace}:*"]
    else:
        return {}
    from django.utils import timezone

    from main.utils import get_ogretmen_gorev_verileri

    return {
        "yan_menu": "includes/ana_menu.html",
        "ana_menu_aktif": aktif_bag,
        "ana_menu_veri": get_ogretmen_gorev_verileri(request.user, timezone.localdate()),
    }


def _kurul_gorevi_var(user):
    from kurul.models import KurulUyesi
    from okul.utils import get_aktif_egitim_yili

    personel = getattr(user, "personel", None)
    return personel is not None and KurulUyesi.objects.filter(
        personel=personel, kurul__egitim_yili=get_aktif_egitim_yili()
    ).exists()


def _rehber_sinifi_var(user):
    from okul.auth import is_ust_yonetici

    if is_ust_yonetici(user):
        return True  # zaten her şeyi görür; sorgu gereksiz
    from ogrenci.services.rehberlik import rehberlik_sinif_sube

    return rehberlik_sinif_sube(user) is not None


def _secmeli_aktif(sayfa):
    for on_ek, ust in SECMELI_UST_ON_EKLERI:
        if sayfa.startswith(on_ek):
            return ust
    return sayfa


# Alt sayfadayken menüde vurgulanacak üst bağlantı (menü başına; aynı sayfa
# iki menüde farklı bir üst bağlantıya sahip olabilir)
UST_SAYFA = {
    "gorev": {
        "ogretmen_gozetim_sinif_listesi": "ogretmen_sinav_gozetim",
        "sinav_salon_yoklama": "ogretmen_sinav_gozetim",
        "ogretmen_yoklama_raporum": "ogretmen_sinav_gozetim",
        "ogretmen_sinav_medya": "ogretmen_sinav_gozetim",
        "nobetci_ders_doldurma_istatistik": "ogretmen_ders_doldurma",
    },
    "nobet": {
        "devamsizlik_create": "devamsizlik_list",
        "devamsizlik_update": "devamsizlik_list",
        "devamsizlik_delete": "devamsizlik_list",
        "manuel_dagitim": "nobet_ders_doldurma",
    },
    "ders_programi": {
        "dersdefteri:gecmis_listesi": "dersdefteri:ders_listesi",
        "dersdefteri:kayit_form": "dersdefteri:ders_listesi",
    },
    "sinav": {
        "sinav:sinav_yoklama_yok_detay": "sinav:sinav_yoklama_raporu",
    },
    "yonetim": {
        "personel_duzenle": "personel_listesi",
        "personel_sil": "personel_listesi",
        "faaliyet:faaliyet_toplu_rapor": "faaliyet:faaliyet_yonetim_listesi",
        "faaliyet:faaliyet_ogrenci_rapor": "faaliyet:faaliyet_yonetim_listesi",
        **{ad: "okul:yonetim_index" for ad in YONETIM_MENUSU_OKUL_SAYFALARI},
    },
    "ogrenci": {
        "ogrenci:ogrenci_detay_duzenle": "ogrenci:ogrenci_liste",
        "ogrenci:ogrenci_muaf_duzenle": "ogrenci:sureksiz_devamsiz_listesi",
        "ogrenci:ayrilma_ekle": "ogrenci:ayrilma_listesi",
        "ogrenci:ayrilma_duzenle": "ogrenci:ayrilma_listesi",
        "ogrenci:ayrilma_sil": "ogrenci:ayrilma_listesi",
        "sosyalkulup:kulup_excel_yukle": "sosyalkulup:kulup_listesi",
        "sosyalkulup:kulup_ogrencileri": "sosyalkulup:kulup_listesi",
        "faaliyet:faaliyet_detay": "faaliyet:faaliyet_liste",
        "faaliyet:faaliyet_duzenle": "faaliyet:faaliyet_liste",
        "faaliyet:faaliyet_sil": "faaliyet:faaliyet_liste",
        "faaliyet:faaliyet_devamsizlik": "faaliyet:faaliyet_liste",
        "faaliyet:faaliyet_rapor": "faaliyet:faaliyet_liste",
    },
}


def yan_menu(request):
    """Bulunulan sayfa bir sol menüye aitse o menünün verisini hazırlar.

    - Görevlerim menüsü: yalnızca "Görevlerim" düğmesini gören kullanıcılar
      (bkz. `is_ogretmen_menu`).
    - Devamsızlık ve Nöbet menüsü: yalnızca müdür yardımcısı / okul müdürü.
    - Ders Programı menüsü: yönetici grupları (bkz. `okul.auth.is_yonetici`).
    - Sınav İşlemleri menüsü: yalnızca müdür yardımcısı; Ortak Sınav, Sorumluluk
      ve Sınav Medya modüllerinin bütün sayfalarında da gösterilir.
    - Yönetim Paneli menüsü: yalnızca müdür yardımcısı; Okul Yönetimi (CRUD),
      Yedekleme ve Sene Sonu bölümlerinin bütün sayfalarında da gösterilir.
    - Seçmeli Dersler menüsü: yalnızca müdür yardımcısı; seçmeli ders ve öğrenci
      ders planlaması sayfalarının hepsinde.
    - Bilgi Panosu menüsü: yalnızca giriş sayfasında (pano ekranları tam ekran
      ayrı sayfalardır, menü taşımaz); sayfanın kendisi üst yöneticilere açıktır.
    - Ana menü: ana sayfanın sol tarafı ve kendi menüsü olmayan sayfalar
      (ANA_MENU_SAYFALARI) — giriş yapmış tüm kullanıcılar.
    - Öğrenci İşleri menüsü: giriş yapmış tüm kullanıcılar.
    Diğer sayfalarda hiç sorgu yapılmaz.
    """
    eslesme = getattr(request, "resolver_match", None)
    if eslesme is None or not request.user.is_authenticated:
        return {}
    sayfa = eslesme.view_name

    def aktif(menu):
        return UST_SAYFA[menu].get(sayfa, sayfa)

    if sayfa in GOREV_MENUSU_SAYFALARI:
        menu = _gorev_menusu(request, aktif("gorev"), eslesme)
        if menu:
            return menu
    if sayfa in NOBET_MENUSU_SAYFALARI and _is_ust_yonetici(request.user):
        return {
            "yan_menu": "includes/nobet_menu.html",
            "nobet_menu": {"aktif_sayfa": aktif("nobet")},
        }
    if sayfa in DERS_PROGRAMI_MENUSU_SAYFALARI:
        from okul.auth import is_yonetici

        if is_yonetici(request.user):
            return {
                "yan_menu": "includes/ders_programi_menu.html",
                "ders_programi_menu": {"aktif_sayfa": aktif("ders_programi")},
            }
    modul_koku = SINAV_MENUSU_MODULLERI.get(eslesme.namespace)
    if (sayfa in SINAV_MENUSU_SAYFALARI or modul_koku) and sayfa not in SINAV_MENUSU_HARIC:
        from okul.auth import is_mudur_yardimcisi

        if is_mudur_yardimcisi(request.user):
            from sinav.services.sinav_ozet import aktif_uretim

            if sayfa in SINAV_MENUSU_SAYFALARI:
                aktif_sayfa = aktif("sinav")
            else:
                aktif_sayfa = modul_koku
            return {
                "yan_menu": "includes/sinav_menu.html",
                "sinav_menu": {
                    "aktif_sayfa": aktif_sayfa,
                    "sinav_aktif_var": aktif_uretim() is not None,
                },
            }
    yonetim_koku = YONETIM_MENUSU_MODULLERI.get(eslesme.namespace)
    if (
        sayfa in YONETIM_MENUSU_SAYFALARI
        or sayfa in YONETIM_MENUSU_OKUL_SAYFALARI
        or yonetim_koku
    ):
        from okul.auth import is_mudur_yardimcisi

        if is_mudur_yardimcisi(request.user):
            return {
                "yan_menu": "includes/yonetim_menu.html",
                "yonetim_menu": {
                    "aktif_sayfa": sayfa if sayfa in ("kurul:gorev_yuku", "kurul:katalog") else (yonetim_koku or aktif("yonetim")),
                },
            }
    if (
        getattr(eslesme.func, "__module__", "").startswith(SECMELI_MENUSU_UYGULAMALARI)
        or sayfa.startswith(SECMELI_MENUSU_ON_EKLERI)
    ):
        from okul.auth import is_mudur_yardimcisi

        if is_mudur_yardimcisi(request.user):
            return {
                "yan_menu": "includes/secmeli_menu.html",
                "secmeli_menu": {"aktif_sayfa": _secmeli_aktif(sayfa)},
            }
    if sayfa == "index":
        # Ana sayfanın sol menüsü; görev verilerini (`ana_menu_veri`) view zaten hesaplar
        return {"yan_menu": "includes/ana_menu.html"}
    if sayfa == "bilgi_panosu":
        return {
            "yan_menu": "includes/pano_menu.html",
            "pano_menu": {"goster": request.GET.get("goster") or "pano"},
        }
    if sayfa in OGRENCI_MENUSU_SAYFALARI:
        return {
            "yan_menu": "includes/ogrenci_menu.html",
            "ogrenci_menu": {
                "aktif_sayfa": aktif("ogrenci"),
                # Öğrenci Listesi / Sosyal Kulübü Belirle, yönetici olmayanlara yalnızca
                # rehberi oldukları sınıf için açılır (bkz. ogrenci.views.ogrenci_liste)
                "rehber_sinifi_var": _rehber_sinifi_var(request.user),
            },
        }
    return _ana_menu(request, sayfa, eslesme.namespace)


def _gorev_menusu(request, aktif, eslesme):
    from main.utils import get_ogretmen_gorev_verileri
    from okul.auth import is_ogretmen_menu

    if not is_ogretmen_menu(request.user):
        return {}

    from django.utils import timezone

    from okul.utils import get_aktif_egitim_yili
    from sosyalkulup.services.kulup import ogretmen_kulupleri

    gorev = get_ogretmen_gorev_verileri(request.user, timezone.localdate())
    return {
        "yan_menu": "includes/gorev_menu.html",
        "gorev_menu": {
            "aktif_sayfa": aktif,
            "aktif_pk": eslesme.kwargs.get("pk"),
            "sinav_gozetim_var": gorev["sinav_gozetim_var"],
            "kurul_gorevi_var": _kurul_gorevi_var(request.user),
            "sorumluluk_gorev_var": gorev["sorumluluk_gorev_var"],
            "sorumluluk_takvim_var": gorev["sorumluluk_takvim_var"],
            "sosyal_kulupler": list(
                ogretmen_kulupleri(request.user, get_aktif_egitim_yili())
            ),
        },
    }
