from dataclasses import replace
from datetime import date

import anthropic
import httpx2
import pytest

from src.ayarlar import Ayarlar
from src.depo import Depo
from src.modeller import IhaleAnalizi, Kullanim
from src.yardimci import LimitAsildi, LLMHatasi, LLMIstemcisi, maliyet_hesapla
from tests.sahte import FakeIstemci, fake_cevap

BUGUN = date(2026, 10, 28)


@pytest.fixture
def ayar(tmp_path):
    return replace(Ayarlar(), cikti_dizini=tmp_path)


@pytest.fixture
def depo():
    return Depo(":memory:")


def cagir(llm, model="claude-sonnet-5-5"):
    return llm.cagir(islem="analiz", model=model, efor="low", sistem="s", icerik="metin",
                     cikti_tipi=IhaleAnalizi, ikn="2026/1", tarih=BUGUN)


def test_maliyet_hesapla(ayar):
    assert maliyet_hesapla("claude-haiku-5-5", 1_000_000, 1_000_000, ayar) == pytest.approx(0.60)
    assert maliyet_hesapla("claude-sonnet-5-5", 1000, 200, ayar) == pytest.approx(0.004)


def test_basarili_cagri(ayar, depo):
    fake = FakeIstemci(lambda kw: fake_cevap(IhaleAnalizi(ozet="tamam")))
    sonuc, kullanim = cagir(LLMIstemcisi(ayar, depo, fake))
    assert sonuc.ozet == "tamam"
    assert kullanim == Kullanim("claude-sonnet-5-5", 1000, 200, pytest.approx(0.004))
    assert depo.bugunku_harcama_usd(BUGUN) == pytest.approx(0.004)


def test_limit_asildi(ayar, depo):
    depo.kullanim_kaydet("analiz", "X", None, Kullanim("claude-sonnet-5-5", 1, 1, 5.0), BUGUN)
    fake = FakeIstemci(lambda kw: fake_cevap(IhaleAnalizi(ozet="x")))
    with pytest.raises(LimitAsildi):
        cagir(LLMIstemcisi(ayar, depo, fake))
    assert fake.cagrilar == []


def test_ret_hata_dosyasi(ayar, depo, tmp_path):
    fake = FakeIstemci(lambda kw: fake_cevap(None, stop_reason="refusal"))
    with pytest.raises(LLMHatasi):
        cagir(LLMIstemcisi(ayar, depo, fake))
    dosyalar = list(tmp_path.glob("_hata_analiz_2026_1_*.txt"))
    assert len(dosyalar) == 1 and "ham çıktı" in dosyalar[0].read_text(encoding="utf-8")
    assert depo.bugunku_harcama_usd(BUGUN) > 0


def test_zaman_asimi(ayar, depo, tmp_path):
    def zaman_asimi(kw):
        raise anthropic.APITimeoutError(request=httpx2.Request("POST", "https://api.anthropic.com"))

    with pytest.raises(LLMHatasi):
        cagir(LLMIstemcisi(ayar, depo, FakeIstemci(zaman_asimi)))
    assert len(list(tmp_path.glob("_hata_analiz_*.txt"))) == 1


def test_fallback_parametreleri(ayar, depo):
    fake = FakeIstemci(lambda kw: fake_cevap(IhaleAnalizi(ozet="x")))
    llm = LLMIstemcisi(ayar, depo, fake)
    cagir(llm, "claude-sonnet-5-5")
    cagir(llm, "claude-haiku-5-5")
    sonnet, haiku = fake.cagrilar
    assert sonnet["fallbacks"] == "default" and sonnet["betas"] == ["server-side-fallback-2026-07-01"]
    assert "fallbacks" not in haiku and "betas" not in haiku
    assert haiku["output_format"] is IhaleAnalizi and haiku["output_config"] == {"effort": "low"}
