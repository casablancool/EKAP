from dataclasses import replace
from datetime import date

import pytest

from src.analiz import PROMPT_SURUMU, analiz_al
from src.ayarlar import Ayarlar
from src.depo import Depo
from src.modeller import IhaleAnalizi, Kullanim
from src.yardimci import LLMIstemcisi
from tests.sahte import FakeIstemci, fake_cevap, ornek_ihale

BUGUN = date(2026, 10, 28)


@pytest.fixture
def ortam(tmp_path):
    ayar = replace(Ayarlar(), cikti_dizini=tmp_path)
    depo = Depo(":memory:")
    fake = FakeIstemci(lambda kw: fake_cevap(IhaleAnalizi(ozet="yeni")))
    return ayar, depo, fake, LLMIstemcisi(ayar, depo, fake)


def test_onbellekten_doner(ortam):
    ayar, depo, fake, llm = ortam
    depo.analiz_kaydet("2026/1", IhaleAnalizi(ozet="eski"), "m", "analiz-v1", Kullanim("m", 1, 1, 0.0))
    assert analiz_al(ornek_ihale("2026/1"), depo, llm, ayar, BUGUN).ozet == "eski"
    assert fake.cagrilar == []


def test_yeni_analiz_kaydedilir(ortam):
    ayar, depo, fake, llm = ortam
    ihale = ornek_ihale("2026/1", metin="Yetkili Satıcı Belgesi istenir.")
    assert analiz_al(ihale, depo, llm, ayar, BUGUN).ozet == "yeni"
    assert len(fake.cagrilar) == 1
    assert fake.cagrilar[0]["model"] == "claude-sonnet-5-5"
    assert ihale.metin in fake.cagrilar[0]["messages"][0]["content"]
    satir = depo.baglanti.execute("SELECT prompt_surumu, model FROM analizler").fetchone()
    assert tuple(satir) == (PROMPT_SURUMU, "claude-sonnet-5-5") and PROMPT_SURUMU == "analiz-v1"


def test_yeniden(ortam):
    ayar, depo, fake, llm = ortam
    depo.analiz_kaydet("2026/1", IhaleAnalizi(ozet="eski"), "m", "analiz-v0", Kullanim("m", 1, 1, 0.0))
    assert analiz_al(ornek_ihale("2026/1"), depo, llm, ayar, BUGUN, yeniden=True).ozet == "yeni"
    assert len(fake.cagrilar) == 1
    assert depo.analiz_getir("2026/1").ozet == "yeni"
