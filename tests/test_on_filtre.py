from datetime import date, datetime, timedelta

import pytest

from src.ayarlar import Ayarlar
from src.on_filtre import on_filtre
from tests.sahte import ornek_ihale, ornek_profil

BUGUN = date(2026, 10, 28)
AYAR = Ayarlar()


def filtre(ihale_degisiklik: dict, profil_degisiklik: dict | None = None):
    return on_filtre(ornek_ihale(**ihale_degisiklik), ornek_profil(**(profil_degisiklik or {})), BUGUN, AYAR)


def gun_sonra(n: int) -> datetime:
    return datetime.combine(BUGUN + timedelta(days=n), datetime.min.time()).replace(hour=10)


def test_tur():
    assert filtre({"tur": None}).gecti
    sonuc = filtre({"tur": "yapim"})
    assert not sonuc.gecti and sonuc.nedenler == ["tür uyumsuz: yapim"]


@pytest.mark.parametrize("il, iller, gecer", [
    ("İSTANBUL", ["istanbul"], True),
    ("Iğdır", ["Igdir"], True),
    ("İzmir", ["Ankara"], False),
    ("İzmir", [], True),
    (None, ["Ankara"], True),
])
def test_il_turkce_harf(il, iller, gecer):
    sonuc = filtre({"il": il}, {"hizmet_illeri": iller})
    assert sonuc.gecti is gecer
    if not gecer:
        assert sonuc.nedenler == [f"il hizmet alanı dışında: {il}"]


@pytest.mark.parametrize("ihale, profil, gecer", [
    ({"okas_kodlari": ["32420000-3"]}, {"okas_kodlari": ["3242"], "anahtar_kelimeler": []}, True),
    ({"okas_kodlari": ["45000000"], "metin": "Asfalt kaplama", "baslik": "Asfalt"},
     {"okas_kodlari": ["3242"], "anahtar_kelimeler": ["ağ altyapısı"]}, False),
    ({"okas_kodlari": [], "metin": "AĞ ALTYAPISI yenileme"}, {"anahtar_kelimeler": ["ağ altyapısı"]}, True),
    ({"okas_kodlari": ["45000000"], "metin": "ağ altyapısı işi"},
     {"okas_kodlari": ["3242"], "anahtar_kelimeler": ["ağ altyapısı"]}, True),
    ({"okas_kodlari": ["45000000"], "metin": "Asfalt", "baslik": "Asfalt"},
     {"okas_kodlari": [], "anahtar_kelimeler": []}, True),
])
def test_faaliyet(ihale, profil, gecer):
    sonuc = filtre(ihale, profil)
    assert sonuc.gecti is gecer
    if not gecer:
        assert sonuc.nedenler == ["faaliyet alanı uyumsuz"]


def test_son_teklif():
    yakin = filtre({"son_teklif": gun_sonra(2)})
    assert not yakin.gecti and "3 günden az" in yakin.nedenler[0]
    assert filtre({"son_teklif": gun_sonra(3)}).gecti
    assert filtre({"son_teklif": gun_sonra(-1)}).nedenler == ["son teklif tarihi geçmiş"]
    assert filtre({"son_teklif": None}).gecti


def test_maliyet():
    aralik = {"tipik_ihale_buyuklugu": {"min_tl": 1_000_000, "max_tl": 5_000_000}}
    assert filtre({"yaklasik_maliyet_tl": 900_000}, aralik).gecti
    dusuk = filtre({"yaklasik_maliyet_tl": 700_000}, aralik)
    assert dusuk.nedenler == ["yaklaşık maliyet tipik aralık dışında: 700.000 TL"]
    assert filtre({"yaklasik_maliyet_tl": None}, aralik).gecti
    assert filtre({"yaklasik_maliyet_tl": 700_000}).gecti


def test_faaliyet_kontrolu_kapali():
    ihale, profil = ornek_ihale(metin="", baslik="Genel alım"), ornek_profil(anahtar_kelimeler=["ağ altyapısı"])
    assert on_filtre(ihale, profil, BUGUN, AYAR, faaliyet_kontrolu=False).gecti is True
    assert on_filtre(ihale, profil, BUGUN, AYAR).gecti is False


def test_birden_cok_neden():
    sonuc = filtre({"tur": "yapim", "il": "İzmir"}, {"hizmet_illeri": ["Ankara"]})
    assert len(sonuc.nedenler) == 2
