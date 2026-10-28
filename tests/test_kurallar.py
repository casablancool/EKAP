from src.ayarlar import Ayarlar
from src.kurallar import kurallari_uygula
from src.modeller import IhaleAnalizi
from tests.sahte import ornek_profil

AYAR = Ayarlar()
DENEYIM = [{"tutar_tl": 6_000_000, "yil": 2024, "tur": "ağ kurulumu"}]


def ust_siniri(analiz: dict, profil: dict):
    sonuclar = kurallari_uygula(IhaleAnalizi(ozet="x", **analiz), ornek_profil(**profil), AYAR)
    return next((s for s in sonuclar if s.kriter == "teklif üst sınırı"), None)


def profil(min_tl=None, ciro=2_000_000, deneyim=DENEYIM):
    return {"is_deneyimleri": deneyim, "mali": {"ciro_tl": ciro},
            "tipik_ihale_buyuklugu": {"min_tl": min_tl}}


ORANLAR = {"is_deneyimi_orani": 0.25, "ciro_orani": 0.25}


def test_teklif_ust_siniri_ciro_sinirlar():
    s = ust_siniri(ORANLAR, profil(min_tl=5_000_000))
    assert s.durum == "saglar"
    assert s.aciklama == "İş hacmi şartına göre bu ihalede en fazla 8.000.000 TL teklif verebilirsiniz."


def test_teklif_ust_siniri_tipik_buyukluk_alti():
    s = ust_siniri(ORANLAR, profil(min_tl=10_000_000))
    assert s.durum == "saglamaz"
    assert s.eksik == "iş hacmi: en fazla 8.000.000 TL teklif verilebilir"


def test_kesin_red_yalnizca_yaklasik_maliyetle():
    assert ust_siniri({**ORANLAR, "yaklasik_maliyet_tl": 40_000_000}, profil()).durum == "kesin_red"
    assert ust_siniri(ORANLAR, profil(min_tl=40_000_000)).durum == "saglamaz"


def test_referans_yok():
    s = ust_siniri(ORANLAR, profil())
    assert s.durum == "belirsiz" and "8.000.000 TL" in s.aciklama


def test_deneyim_belgesi_yok():
    s = ust_siniri(ORANLAR, profil(min_tl=1_000_000, deneyim=[]))
    assert s.durum == "saglamaz" and s.eksik == "iş deneyim belgesi"


def test_oran_yok():
    assert ust_siniri({}, profil(min_tl=1_000_000)) is None


def test_belgeler():
    analiz = IhaleAnalizi(ozet="x", yeterlik_belgeleri=["Yetkili Satıcı Belgesi",
                                                         "ISO 9001 Kalite Yönetim Sistemi Belgesi"])
    sonuclar = kurallari_uygula(analiz, ornek_profil(belgeler=["TS EN ISO 9001"]), AYAR)
    belgeler = {s.kriter: s for s in sonuclar}
    assert belgeler["belge: Yetkili Satıcı Belgesi"].durum == "saglamaz"
    assert belgeler["belge: Yetkili Satıcı Belgesi"].eksik == "Yetkili Satıcı Belgesi"
    assert belgeler["belge: ISO 9001 Kalite Yönetim Sistemi Belgesi"].durum == "saglar"


def test_belge_ayni_metin():
    analiz = IhaleAnalizi(ozet="x", yeterlik_belgeleri=["ISO 9001 Kalite Yönetim Sistemi Belgesi"])
    sonuc = kurallari_uygula(analiz, ornek_profil(belgeler=["ISO 9001"]), AYAR)[0]
    assert sonuc.durum == "saglar"


def test_belge_standart_numarasi_farkli():
    analiz = IhaleAnalizi(ozet="x", yeterlik_belgeleri=["ISO/IEC 27001 Bilgi Güvenliği Yönetim Sistem Belgesi"])
    assert kurallari_uygula(analiz, ornek_profil(belgeler=["TS EN ISO/IEC 27001:2022"]), AYAR)[0].durum == "saglar"
    assert kurallari_uygula(analiz, ornek_profil(belgeler=["ISO 9001"]), AYAR)[0].durum == "saglamaz"
