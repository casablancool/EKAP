from datetime import date
from pathlib import Path

import pytest

from src.toplayici.dosya_kaynagi import DosyaKaynagi
from src.toplayici.kaynak import KaynakHatasi
from tests.sahte import ornek_ihale


def yaz(dizin: Path, ad: str, **degisiklik) -> None:
    (dizin / ad).write_text(ornek_ihale(**degisiklik).model_dump_json(), encoding="utf-8")


def test_gecerli_dosyalar(tmp_path):
    yaz(tmp_path, "a.json", ikn="2026/1")
    yaz(tmp_path, "b.json", ikn="2026/2")
    assert [i.ikn for i in DosyaKaynagi(tmp_path).yeni_ihaleleri_getir(date(2026, 1, 1))] == ["2026/1", "2026/2"]


def test_bozuk_dosya_atlanir(tmp_path, caplog):
    yaz(tmp_path, "a.json", ikn="2026/1")
    (tmp_path / "bozuk.json").write_text('{"ikn": 1', encoding="utf-8")
    assert len(DosyaKaynagi(tmp_path).yeni_ihaleleri_getir(date(2026, 1, 1))) == 1
    assert "bozuk.json" in caplog.text


def test_since_filtresi(tmp_path):
    yaz(tmp_path, "a.json", ikn="2026/1", yayin_tarihi=date(2026, 10, 20))
    yaz(tmp_path, "b.json", ikn="2026/2", yayin_tarihi=date(2026, 10, 27))
    yaz(tmp_path, "c.json", ikn="2026/3", yayin_tarihi=None)
    sonuc = DosyaKaynagi(tmp_path).yeni_ihaleleri_getir(date(2026, 10, 25))
    assert [i.ikn for i in sonuc] == ["2026/2", "2026/3"]


def test_dizin_yok(tmp_path):
    with pytest.raises(KaynakHatasi):
        DosyaKaynagi(tmp_path / "yok").yeni_ihaleleri_getir(date(2026, 1, 1))


def test_ornek_ilanlar_gecerli():
    ihaleler = DosyaKaynagi(Path("ilanlar")).yeni_ihaleleri_getir(date(2000, 1, 1))
    assert len(ihaleler) == len(list(Path("ilanlar").glob("*.json"))) >= 5
