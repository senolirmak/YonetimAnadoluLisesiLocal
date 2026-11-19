"""APT deposunu imzalamak için en küçük OpenPGP (RFC 4880) uygulaması.

Yalnızca gerekeni yapar: Ed25519 anahtarı (EdDSA, algoritma 22) ile v4
imza üretir, açık anahtarı APT'nin `signed-by=` ile okuduğu ikili anahtarlık
biçiminde dışa verir ve Release dosyası için açık metin imza (InRelease) ile
ayrık imza (Release.gpg) üretir. Tahtadaki `gpgv` (APT) bunları doğrular.

Sunucuda `gpg` / gpg-agent / GNUPGHOME gerekmez; imzalama `cryptography`
ile yapılır. Özel anahtar yalnızca sunucudaki anahtar dosyasında durur.
"""

import base64
import hashlib
import struct

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    NoEncryption,
    PrivateFormat,
    PublicFormat,
)

_ALGO_EDDSA = 22
_HASH_SHA256 = 8
_ED25519_OID = bytes.fromhex("2b06010401da470f01")  # 1.3.6.1.4.1.11591.15.1

IMZA_IKILI = 0x00  # ayrık imza: dosyanın baytları olduğu gibi
IMZA_METIN = 0x01  # açık metin imza: satır sonları CRLF'ye çevrilir
_IMZA_POZITIF_SERTIFIKA = 0x13

_ALT_OLUSTURMA_ZAMANI = 2
_ALT_YAYINCI_KIMLIGI = 16
_ALT_ANAHTAR_BAYRAKLARI = 27
_ALT_YAYINCI_PARMAK_IZI = 33


def _mpi(sayi_baytlari):
    """Baştaki sıfırları atılmış büyük-endian tamsayı → MPI (bit sayısı + baytlar)."""
    veri = sayi_baytlari.lstrip(b"\x00")
    bit = (len(veri) - 1) * 8 + veri[0].bit_length() if veri else 0
    return struct.pack(">H", bit) + veri


def _paket(etiket, govde):
    """Yeni biçim paket başlığı (RFC 4880 4.2.2)."""
    uzunluk = len(govde)
    if uzunluk < 192:
        boy = bytes([uzunluk])
    elif uzunluk < 8384:
        uzunluk -= 192
        boy = bytes([(uzunluk >> 8) + 192, uzunluk & 0xFF])
    else:
        boy = b"\xff" + struct.pack(">I", uzunluk)
    return bytes([0xC0 | etiket]) + boy + govde


def _alt_paket(tur, veri):
    return bytes([len(veri) + 1, tur]) + veri  # tüm alt paketlerimiz < 191 bayt


def _crc24(veri):
    crc = 0xB704CE
    for bayt in veri:
        crc ^= bayt << 16
        for _ in range(8):
            crc <<= 1
            if crc & 0x1000000:
                crc ^= 0x1864CFB
    return crc & 0xFFFFFF


def zirhla(veri, tur="SIGNATURE"):
    """ASCII zırh (RFC 4880 6.2)."""
    b64 = base64.b64encode(veri).decode("ascii")
    satirlar = [b64[i : i + 64] for i in range(0, len(b64), 64)]
    crc = base64.b64encode(struct.pack(">I", _crc24(veri))[1:]).decode("ascii")
    return (
        f"-----BEGIN PGP {tur}-----\n\n"
        + "\n".join(satirlar)
        + f"\n={crc}\n-----END PGP {tur}-----\n"
    )


class Anahtar:
    """Ed25519 imza anahtarı. `olusturma` (epoch) anahtarın parmak izine girer;
    aynı tohum + aynı zaman her zaman aynı açık anahtarı verir."""

    def __init__(self, tohum, olusturma):
        if len(tohum) != 32:
            raise ValueError("Ed25519 tohumu 32 bayt olmalı.")
        self._ozel = Ed25519PrivateKey.from_private_bytes(tohum)
        self.olusturma = int(olusturma)
        acik = self._ozel.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
        self._acik_govde = (
            bytes([4])
            + struct.pack(">I", self.olusturma)
            + bytes([_ALGO_EDDSA, len(_ED25519_OID)])
            + _ED25519_OID
            + _mpi(b"\x40" + acik)
        )
        self.parmak_izi = hashlib.sha1(
            b"\x99" + struct.pack(">H", len(self._acik_govde)) + self._acik_govde,
            usedforsecurity=False,
        ).digest()
        self.kimlik = self.parmak_izi[-8:]

    @classmethod
    def uret(cls, olusturma):
        ozel = Ed25519PrivateKey.generate()
        return cls(ozel.private_bytes(Encoding.Raw, PrivateFormat.Raw, NoEncryption()), olusturma)

    def tohum(self):
        return self._ozel.private_bytes(Encoding.Raw, PrivateFormat.Raw, NoEncryption())

    def _imza(self, imza_turu, imzalanan, zaman, ek_alt_paketler=b""):
        hashli_alt = (
            _alt_paket(_ALT_OLUSTURMA_ZAMANI, struct.pack(">I", int(zaman)))
            + _alt_paket(_ALT_YAYINCI_PARMAK_IZI, b"\x04" + self.parmak_izi)
            + ek_alt_paketler
        )
        hashli = (
            bytes([4, imza_turu, _ALGO_EDDSA, _HASH_SHA256])
            + struct.pack(">H", len(hashli_alt))
            + hashli_alt
        )
        ozet = hashlib.sha256(
            imzalanan + hashli + b"\x04\xff" + struct.pack(">I", len(hashli))
        ).digest()
        imza = self._ozel.sign(ozet)
        hashsiz_alt = _alt_paket(_ALT_YAYINCI_KIMLIGI, self.kimlik)
        govde = (
            hashli
            + struct.pack(">H", len(hashsiz_alt))
            + hashsiz_alt
            + ozet[:2]
            + _mpi(imza[:32])
            + _mpi(imza[32:])
        )
        return _paket(2, govde)

    def acik_anahtarlik(self, kullanici_kimligi):
        """APT `signed-by=` için ikili anahtarlık: açık anahtar + kimlik + öz imza."""
        uid = kullanici_kimligi.encode("utf-8")
        imzalanan = (
            b"\x99"
            + struct.pack(">H", len(self._acik_govde))
            + self._acik_govde
            + b"\xb4"
            + struct.pack(">I", len(uid))
            + uid
        )
        oz_imza = self._imza(
            _IMZA_POZITIF_SERTIFIKA,
            imzalanan,
            self.olusturma,
            _alt_paket(_ALT_ANAHTAR_BAYRAKLARI, b"\x03"),  # sertifikalama + imzalama
        )
        return _paket(6, self._acik_govde) + _paket(13, uid) + oz_imza

    def ayrik_imza(self, veri, zaman):
        """Release.gpg: verinin baytları üzerine ikili imza (zırhlı)."""
        return zirhla(self._imza(IMZA_IKILI, veri, zaman)).encode("ascii")

    def acik_metin_imza(self, metin, zaman):
        """InRelease: açık metin imzalı belge (RFC 4880 7). Satır sonu boşlukları
        imzalanmaz; '-' ile başlayan satırlar kaçırılır."""
        satirlar = [s.rstrip(" \t") for s in metin.rstrip("\n").split("\n")]
        imzalanan = "\r\n".join(satirlar).encode("utf-8")
        imza = zirhla(self._imza(IMZA_METIN, imzalanan, zaman))
        kacirilmis = "\n".join(("- " + s) if s.startswith("-") else s for s in satirlar)
        return (
            "-----BEGIN PGP SIGNED MESSAGE-----\nHash: SHA256\n\n" + kacirilmis + "\n" + imza
        ).encode("utf-8")
