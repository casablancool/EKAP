from datetime import date, datetime

from src.modeller import EslesmeSonucu, Karar
from src.rapor import bos_hafta_notu, ihale_blogu, ozet_olustur
from tests.sahte import ornek_ihale

BUGUN = date(2026, 10, 28)


def sonuc(karar, gerekceler=("Benzer iş tanımına uyuyor.",), eksikler=()):
    return EslesmeSonucu(karar=karar, gerekceler=list(gerekceler)[:3], eksikler=list(eksikler))


def satir(ikn, karar, son, **ihale):
    return ornek_ihale(ikn, baslik=f"İhale {ikn}", son_teklif=son, **ihale), sonuc(karar)


def test_bos_ise_none():
    assert ozet_olustur("Firma", [], 0, BUGUN) is None
    assert ozet_olustur("Firma", [satir("1", Karar.GIREMEZ, None)], 3, BUGUN) is None


def test_siralama():
    satirlar = [
        satir("S", Karar.SARTLI, datetime(2026, 10, 30, 10)),
        satir("G15", Karar.GIREBILIR, datetime(2026, 11, 15, 10)),
        satir("G05", Karar.GIREBILIR, datetime(2026, 11, 5, 10)),
        satir("GN", Karar.GIREBILIR, None),
    ]
    metin = ozet_olustur("Firma", satirlar, 0, BUGUN).metin
    sira = [metin.index(f"İhale {k}") for k in ("G05", "G15", "GN", "S")]
    assert sira == sorted(sira)


def test_sartli_eksik():
    s = (ornek_ihale("1"), sonuc(Karar.SARTLI, eksikler=["Yetkili Satıcı Belgesi"]))
    assert "Eksik: Yetkili Satıcı Belgesi" in ozet_olustur("Firma", [s], 0, BUGUN).metin


def test_eksik_alanlar():
    blok = "\n".join(ihale_blogu(ornek_ihale("1", yaklasik_maliyet_tl=None, il=None, son_teklif=None),
                                 sonuc(Karar.GIREBILIR)))
    assert "Yaklaşık maliyet" not in blok and "None" not in blok and "Son teklif" not in blok


def test_maliyet_ve_tarih_bicimi():
    blok = "\n".join(ihale_blogu(ornek_ihale("1", yaklasik_maliyet_tl=1_250_000,
                                             son_teklif=datetime(2026, 11, 5, 14, 30)), sonuc(Karar.GIREBILIR)))
    assert "Son teklif: 05.11.2026 14:30" in blok and "Yaklaşık maliyet: 1.250.000 TL" in blok


def test_blok_satir_sayisi():
    bes = ["a", "b", "c", "d", "e"]
    g = EslesmeSonucu(karar=Karar.GIREBILIR, gerekceler=bes[:3])
    s = EslesmeSonucu(karar=Karar.SARTLI, gerekceler=bes[:3], eksikler=["x"])
    assert len(ihale_blogu(ornek_ihale(), g)) <= 6
    assert len(ihale_blogu(ornek_ihale(), s)) <= 6
    assert ihale_blogu(ornek_ihale(), s)[0].startswith("⚠️ ŞARTLI · ")
    assert ihale_blogu(ornek_ihale(), g)[0].startswith("✅ GİREBİLİR · ")


def test_html_kacis():
    s = (ornek_ihale("1", baslik="A & B <x>"), sonuc(Karar.GIREBILIR))
    html = ozet_olustur("Firma", [s], 0, BUGUN).html
    assert "&amp;" in html and "<x>" not in html
    assert 'href="https://ekapv2.kik.gov.tr/ekap/search/1"' in html


def test_uygun_olmayan():
    s = [(ornek_ihale("1"), sonuc(Karar.GIREBILIR))]
    assert "12 ihale daha incelendi, uygun değil." in ozet_olustur("Firma", s, 12, BUGUN).metin
    assert "ihale daha incelendi" not in ozet_olustur("Firma", s, 0, BUGUN).metin


def test_kisisel_veri_yok():
    s = [(ornek_ihale("1", metin="İrtibat: Ahmet Yılmaz 0312 000 00 00"), sonuc(Karar.GIREBILIR))]
    ozet = ozet_olustur("Firma", s, 0, BUGUN)
    assert "Ahmet" not in ozet.metin and "Ahmet" not in ozet.html


def test_konu_ve_altbilgi():
    s = [satir("1", Karar.GIREBILIR, None), satir("2", Karar.SARTLI, None)]
    ozet = ozet_olustur("Örnek Ltd.", s, 0, BUGUN)
    assert ozet.konu == "EKAP: 2 uygun ihale – 28.10.2026"
    assert ozet.metin.startswith("Merhaba Örnek Ltd., bugün sizin için 1 uygun ve 1 şartlı ihale bulduk.")
    assert "Bu e-posta karar desteği amaçlıdır." in ozet.metin and "karar desteği" in ozet.html


def test_bos_hafta_notu():
    ozet = bos_hafta_notu("Örnek Ltd.", date(2026, 10, 30))
    assert ozet.konu == "EKAP: bu hafta uygun ihale çıkmadı – 30.10.2026"
    assert "bu hafta profilinize uygun ihale çıkmadı" in ozet.metin
