"""Testlerde kullanılan örnek nesneler ve sahte bağımlılıklar."""
from collections.abc import Callable
from datetime import datetime
from types import SimpleNamespace

from src.modeller import FirmaProfili, IhaleHam


def fake_cevap(nesne, girdi: int = 1000, cikti: int = 200, stop_reason: str = "end_turn"):
    return SimpleNamespace(
        parsed_output=nesne,
        stop_reason=stop_reason,
        usage=SimpleNamespace(input_tokens=girdi, output_tokens=cikti),
        content=[SimpleNamespace(type="text", text="ham çıktı")],
    )


class FakeIstemci:
    """anthropic.Anthropic yerine geçer; her çağrının argümanlarını .cagrilar'da tutar.

    `cevaplar(kwargs)` ya bir fake_cevap döner ya da bir istisna fırlatır.
    """

    def __init__(self, cevaplar: Callable[[dict], object]):
        self.cevaplar = cevaplar
        self.cagrilar: list[dict] = []
        self.messages = SimpleNamespace(parse=self._parse)
        self.beta = SimpleNamespace(messages=SimpleNamespace(parse=self._parse))

    def _parse(self, **kw):
        self.cagrilar.append(kw)
        return self.cevaplar(kw)


class FakeTasiyici:
    """Kayıtlı EKAP fikstürlerini sunan sahte taşıyıcı (ağa çıkmaz).

    Liste: paginationSkip 0 → liste-1.json, 50 → liste-2.json. Detay: ihaleId → fikstür; bilinmeyen id için boş detay.
    `hatalar`: {(yol_öneki, anahtar): istisna} — anahtar liste için skip, detay için ihaleId.
    """

    def __init__(self, hatalar: dict | None = None):
        import json
        from pathlib import Path
        dizin = Path(__file__).parent / "fikstur" / "ekap"
        self._oku = lambda ad: json.loads((dizin / ad).read_text(encoding="utf-8"))
        self.hatalar = hatalar or {}
        self.istekler: list[tuple[str, dict]] = []
        self.detaylar = {"bt-ihale-id": "detay-2026-1874068.json", "yapim-ihale-id": "detay-2026-2082996.json"}

    def post(self, yol, govde):
        self.istekler.append((yol, govde))
        if yol.startswith("/Ihale/"):
            anahtar = govde["paginationSkip"]
            if ("/Ihale", anahtar) in self.hatalar:
                raise self.hatalar[("/Ihale", anahtar)]
            return self._oku({0: "liste-1.json", 50: "liste-2.json"}[anahtar])
        anahtar = govde["ihaleId"]
        if ("/IhaleDetay", anahtar) in self.hatalar:
            raise self.hatalar[("/IhaleDetay", anahtar)]
        if anahtar in self.detaylar:
            return self._oku(self.detaylar[anahtar])
        return {"item": {"ilanList": [], "ihtiyacKalemiOkasList": []}}

    def detay_idleri(self) -> list[str]:
        return [g["ihaleId"] for y, g in self.istekler if y.startswith("/IhaleDetay")]


class FakeKaynak:
    def __init__(self, ihaleler: list | None = None, hata: Exception | None = None, ad: str = "sahte"):
        self.ihaleler = ihaleler or []
        self.hata = hata
        self.ad = ad

    def yeni_ihaleleri_getir(self, since):
        if self.hata:
            raise self.hata
        return list(self.ihaleler)


class KayitGonderici:
    """Gönderilen e-postaları kaydeder; basarisiz_alicilar'dan birine gidecek e-postada hata fırlatır."""

    def __init__(self, basarisiz_alicilar: set[str] | None = None):
        self.basarisiz_alicilar = basarisiz_alicilar or set()
        self.gonderilenler: list[tuple] = []

    def gonder(self, alicilar, ozet, etiket):
        if self.basarisiz_alicilar & set(alicilar):
            raise OSError(f"SMTP reddetti: {alicilar}")
        self.gonderilenler.append((alicilar, ozet, etiket))


def ornek_ihale(ikn: str = "2026/1", **degisiklik) -> IhaleHam:
    veri = {
        "ikn": ikn,
        "baslik": "Ağ altyapısı yenileme",
        "idare": "Örnek Belediyesi",
        "il": "Ankara",
        "tur": "hizmet",
        "son_teklif": datetime(2026, 11, 10, 10, 0),
        "metin": "Kampüs ağ altyapısı ve yapısal kablolama işi.",
        "kaynak_url": f"https://ekapv2.kik.gov.tr/ekap/search/{ikn.replace('/', '_')}",
    }
    veri.update(degisiklik)
    return IhaleHam(**veri)


def ornek_profil(**degisiklik) -> FirmaProfili:
    veri = {
        "ad": "Örnek Ağ Ltd.",
        "eposta": ["teklif@ornek.com.tr"],
        "ihale_turleri": ["mal", "hizmet"],
        "anahtar_kelimeler": ["ağ altyapısı"],
    }
    veri.update(degisiklik)
    return FirmaProfili(**veri)
