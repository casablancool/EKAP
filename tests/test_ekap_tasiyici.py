import json
import ssl
import urllib.error
from dataclasses import replace

import pytest

from src.ayarlar import Ayarlar
from src.toplayici.ekap_kaynagi import TABAN, HttpTasiyici
from src.toplayici.kaynak import KaynakHatasi

YOL = "/Ihale/GetListByParameters"


class Yanit:
    def __init__(self, govde: bytes):
        self.govde = govde

    def read(self):
        return self.govde

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class SahteAcici:
    """Sırayla verilen yanıtları döner; bir öğe istisna ise onu fırlatır."""

    def __init__(self, *yanitlar):
        self.yanitlar = list(yanitlar)
        self.istekler = []

    def __call__(self, istek, timeout=None, context=None):
        self.istekler.append((istek, timeout, context))
        sonraki = self.yanitlar.pop(0)
        if isinstance(sonraki, Exception):
            raise sonraki
        return Yanit(sonraki if isinstance(sonraki, bytes) else json.dumps(sonraki).encode("utf-8"))


def http_hata(kod: int) -> urllib.error.HTTPError:
    return urllib.error.HTTPError(TABAN + YOL, kod, "hata", {}, None)


class Saat:
    def __init__(self):
        self.t = 100.0
        self.uykular = []

    def __call__(self):
        return self.t

    def uyku(self, sn):
        self.uykular.append(sn)


def tasiyici(acici, iletisim="", saat=None):
    saat = saat or Saat()
    return HttpTasiyici(replace(Ayarlar(), iletisim_eposta=iletisim), acici=acici, uyku=saat.uyku, saat=saat), saat


def test_basliklar_ve_govde():
    acici = SahteAcici({"list": [], "totalCount": 0})
    t, _ = tasiyici(acici)
    assert t.post(YOL, {"paginationTake": 50}) == {"list": [], "totalCount": 0}
    istek, timeout, context = acici.istekler[0]
    assert istek.get_method() == "POST" and istek.full_url == TABAN + YOL
    assert istek.get_header("Content-type") == "application/json"
    assert istek.get_header("Accept") == "application/json"
    assert json.loads(istek.data) == {"paginationTake": 50}
    assert timeout == 30 and context.verify_mode == ssl.CERT_REQUIRED
    assert t.istek_sayisi == 1


def test_user_agent():
    assert tasiyici(SahteAcici(), "a@b.com")[0].user_agent == "ekap-ajan/0.1 (+mailto:a@b.com)"
    assert tasiyici(SahteAcici())[0].user_agent == "ekap-ajan/0.1"


def test_user_agent_istekte():
    acici = SahteAcici({})
    t, _ = tasiyici(acici, "a@b.com")
    t.post(YOL, {})
    assert acici.istekler[0][0].get_header("User-agent") == "ekap-ajan/0.1 (+mailto:a@b.com)"


def test_istek_araligi():
    t, saat = tasiyici(SahteAcici({}, {}))
    t.post(YOL, {})
    assert saat.uykular == []
    t.post(YOL, {})
    assert saat.uykular == [pytest.approx(2.5)]


def test_5xx_tekrar_dener():
    acici = SahteAcici(http_hata(500), http_hata(500), {"tamam": True})
    t, saat = tasiyici(acici)
    assert t.post(YOL, {}) == {"tamam": True}
    assert len(acici.istekler) == 3
    assert 2 in saat.uykular and 4 in saat.uykular


def test_baglanti_hatasi_tekrar_dener():
    acici = SahteAcici(urllib.error.URLError("dns"), TimeoutError(), {"tamam": True})
    t, _ = tasiyici(acici)
    assert t.post(YOL, {}) == {"tamam": True}


def test_5xx_uc_kez_sonra_hata():
    t, _ = tasiyici(SahteAcici(http_hata(503), http_hata(503), http_hata(503)))
    with pytest.raises(KaynakHatasi, match="3 deneme"):
        t.post(YOL, {})


def test_4xx_tekrar_denenmez():
    acici = SahteAcici(http_hata(429))
    t, _ = tasiyici(acici)
    with pytest.raises(KaynakHatasi, match="HTTP 429"):
        t.post(YOL, {})
    assert len(acici.istekler) == 1


def test_json_olmayan_yanit():
    acici = SahteAcici(b"<html>dogrulama</html>")
    t, _ = tasiyici(acici)
    with pytest.raises(KaynakHatasi, match="JSON olmayan"):
        t.post(YOL, {})
    assert len(acici.istekler) == 1
