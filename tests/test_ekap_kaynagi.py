import json
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest

from src.ayarlar import Ayarlar
from src.modeller import Firma
from src.toplayici.ekap_kaynagi import EkapKaynagi, ListeOzeti, liste_secici
from src.toplayici.kaynak import KaynakHatasi
from tests.sahte import FakeTasiyici, ornek_profil

SINCE, BUGUN = date(2026, 10, 25), date(2026, 10, 27)
DETAY_HATASI = "/IhaleDetay/GetByIhaleIdIhaleDetay: 3 deneme başarısız: HTTP 503"


def kaynak(tasiyici, **kw):
    return EkapKaynagi(tasiyici, bugun=lambda: BUGUN, **kw)


def fikstur_ikn(*adlar) -> list[str]:
    return [o["ikn"] for ad in adlar
            for o in json.loads(Path(f"tests/fikstur/ekap/{ad}").read_text(encoding="utf-8"))["list"]]


def test_iki_sayfa_toplanir():
    t = FakeTasiyici()
    sonuc = kaynak(t).yeni_ihaleleri_getir(SINCE)
    assert len(sonuc) == 5
    listeler = [g for y, g in t.istekler if y == "/Ihale/GetListByParameters"]
    assert [g["paginationSkip"] for g in listeler] == [0, 50]
    assert listeler[0]["paginationTake"] == 50
    assert listeler[0]["ilanTarihSaatBaslangic"] == "2026-10-25T00:00:00"
    assert listeler[0]["ilanTarihSaatBitis"] == "2026-10-27T23:59:59"


def test_ayni_ikn_iki_sayfada_bir_kez():
    sonuc = kaynak(FakeTasiyici()).yeni_ihaleleri_getir(SINCE)
    ikns = [i.ikn for i in sonuc]
    assert len(ikns) == len(set(ikns)) == len(set(fikstur_ikn("liste-1.json", "liste-2.json")))


def test_bt_ihalesi_tam_detayli():
    bt = next(i for i in kaynak(FakeTasiyici()).yeni_ihaleleri_getir(SINCE) if i.ikn == "2026/1874068")
    assert bt.okas_kodlari[0] == "72260000" and bt.tur == "hizmet" and "İhale Kayıt Numarası" in bt.metin


def test_yalnizca_katilima_acik(monkeypatch):
    t = FakeTasiyici()
    asil = t._oku
    def oku(ad):
        veri = asil(ad)
        if ad == "liste-1.json":
            veri["list"][1]["ihaleDurum"] = "6"  # yapım ihalesi (ikinci sayfada tekrarı yok)
        return veri
    t._oku = oku
    sonuc = kaynak(t).yeni_ihaleleri_getir(SINCE)
    assert "2026/2082996" not in [i.ikn for i in sonuc]
    assert "yapim-ihale-id" not in t.detay_idleri()


def test_bilinen_ihale_detaylanmaz():
    t = FakeTasiyici()
    k = kaynak(t, bilinen=lambda ikn: ikn == "2026/1874068")
    assert "2026/1874068" not in [i.ikn for i in k.yeni_ihaleleri_getir(SINCE)]
    assert "bt-ihale-id" not in t.detay_idleri()
    assert k.son_istatistik["bilinen"] == 1


def test_on_secici_eler():
    t = FakeTasiyici()
    k = kaynak(t, on_secici=lambda o: o.tur == "hizmet")
    sonuc = k.yeni_ihaleleri_getir(SINCE)
    assert sonuc and all(i.tur == "hizmet" for i in sonuc)
    assert "yapim-ihale-id" not in t.detay_idleri()
    assert k.son_istatistik["secilmeyen"] >= 1


def test_detay_hatasi_tek_ihaleyi_atlar():
    t = FakeTasiyici({("/IhaleDetay", "bt-ihale-id"): KaynakHatasi(DETAY_HATASI)})
    k = kaynak(t)
    sonuc = k.yeni_ihaleleri_getir(SINCE)
    assert len(sonuc) == 4 and "2026/1874068" not in [i.ikn for i in sonuc]
    assert k.son_istatistik["detay_hatasi"] == 1


def test_detay_4xx_toplayiciyi_durdurur():
    t = FakeTasiyici({("/IhaleDetay", "yapim-ihale-id"): KaynakHatasi("/IhaleDetay/…: HTTP 403 (bot koruması)")})
    with pytest.raises(KaynakHatasi, match="HTTP 403") as e:
        kaynak(t).yeni_ihaleleri_getir(SINCE)
    assert [i.ikn for i in e.value.kismi] == ["2026/1874068"]


def test_yarida_kesilirse_kismi_sonuc():
    t = FakeTasiyici({("/Ihale", 50): KaynakHatasi("/Ihale/GetListByParameters: HTTP 403")})
    with pytest.raises(KaynakHatasi, match="HTTP 403") as e:
        kaynak(t).yeni_ihaleleri_getir(SINCE)
    assert len(e.value.kismi) == 3


def test_beklenmeyen_liste():
    class Bozuk(FakeTasiyici):
        def post(self, yol, govde):
            return {"foo": 1}
    with pytest.raises(KaynakHatasi, match="beklenmeyen liste"):
        kaynak(Bozuk()).yeni_ihaleleri_getir(SINCE)


def ozet(**kw) -> ListeOzeti:
    temel = dict(id="x", ikn="2026/1", baslik="Alım", idare="İdare", il="Ankara", tur="mal", durum="2",
                 son_teklif=datetime(2026, 11, 20, 10))
    temel.update(kw)
    return ListeOzeti(**temel)


def test_liste_secici():
    firma = Firma(1, ornek_profil(ihale_turleri=["mal"], hizmet_illeri=["Ankara"],
                                  anahtar_kelimeler=["çok özel kelime"]), True)
    secici = liste_secici([firma], Ayarlar(), BUGUN)
    assert secici(ozet()) is True
    assert secici(ozet(tur="hizmet")) is False
    assert secici(ozet(il=None)) is True
    assert secici(ozet(son_teklif=datetime.combine(BUGUN + timedelta(days=1), datetime.min.time()))) is False
    assert liste_secici([], Ayarlar(), BUGUN)(ozet()) is False
