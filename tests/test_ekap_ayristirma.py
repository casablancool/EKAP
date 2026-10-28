import json
import re
from datetime import date, datetime
from pathlib import Path

import pytest

from src.toplayici.ekap_kaynagi import html_metin, ihale_ham_olustur, kalici_baglanti, liste_ozeti
from src.toplayici.kaynak import KaynakHatasi

FIKSTUR = Path("tests/fikstur/ekap")


def oku(ad: str) -> dict:
    return json.loads((FIKSTUR / ad).read_text(encoding="utf-8"))


@pytest.fixture
def oge() -> dict:
    return oku("liste-1.json")["list"][0]


def test_liste_ozeti(oge):
    o = liste_ozeti(oge)
    assert re.match(r"^\d{4}/\d+$", o.ikn) and o.ikn == "2026/1874068"
    assert o.durum == "2" and isinstance(o.son_teklif, datetime)
    assert o.il == "Ankara" and o.tur == "hizmet" and o.id == "bt-ihale-id"


def test_il_turkce_baslik(oge):
    assert liste_ozeti({**oge, "ihaleIlAdi": "İZMİR"}).il == "İzmir"
    assert liste_ozeti({**oge, "ihaleIlAdi": ""}).il is None
    assert liste_ozeti({**oge, "ihaleIlAdi": None}).il is None


@pytest.mark.parametrize("tip, tur", [("1", "mal"), ("2", "yapim"), ("3", "hizmet"), ("4", None), (3, "hizmet")])
def test_tur_eslemesi(oge, tip, tur):
    assert liste_ozeti({**oge, "ihaleTip": tip}).tur == tur


def test_son_teklif_eksik(oge):
    assert liste_ozeti({**oge, "ihaleTarihSaat": None}).son_teklif is None
    assert liste_ozeti({**oge, "ihaleTarihSaat": "bozuk"}).son_teklif is None


def test_liste_ozeti_eksik_ikn(oge):
    with pytest.raises(KaynakHatasi):
        liste_ozeti({k: v for k, v in oge.items() if k != "ikn"})


def test_ihale_ham_olustur_bt_ihalesi(oge):
    ihale = ihale_ham_olustur(liste_ozeti(oge), oku("detay-2026-1874068.json"))
    assert ihale.okas_kodlari == ["72260000", "72263000", "48820000", "30230000"]
    assert ihale.yayin_tarihi == date(2026, 10, 27)
    assert "İhale Kayıt Numarası" in ihale.metin and "<" not in ihale.metin
    assert ihale.kaynak_url.endswith("/ekap/search/2026_1874068")
    assert ihale.kaynak == "ekap" and ihale.yaklasik_maliyet_tl is None and ihale.il == "Ankara"


def test_eksik_detay_alanlari(oge):
    ihale = ihale_ham_olustur(liste_ozeti(oge), {"item": {"ilanList": None, "ihtiyacKalemiOkasList": None}})
    assert ihale.yayin_tarihi is None and ihale.okas_kodlari == [] and ihale.metin == ""


def test_beklenmeyen_detay(oge):
    with pytest.raises(KaynakHatasi):
        ihale_ham_olustur(liste_ozeti(oge), {})


def test_html_metin():
    assert html_metin("<b>A</b><br/>B<table><tr><td>x</td><td>y</td></tr></table>") == "A\nB\nx y"


def test_kalici_baglanti():
    assert kalici_baglanti("2026/1874068") == "https://ekapv2.kik.gov.tr/ekap/search/2026_1874068"
