from dataclasses import replace
from datetime import date
from pathlib import Path

import pytest

from src.ayarlar import Ayarlar
from src.depo import Depo
from src.eslestir import EslesmeLLMCevabi, eslestir, kararlari_birlestir
from src.modeller import Firma, FirmaProfili, IhaleAnalizi, Karar, KuralSonucu
from src.yardimci import LLMIstemcisi
from tests.sahte import FakeIstemci, fake_cevap, ornek_ihale, ornek_profil

BUGUN = date(2026, 10, 28)
G, S, X = Karar.GIREBILIR, Karar.SARTLI, Karar.GIREMEZ


def kural(durum, kriter="belge: Yetkili Satıcı Belgesi", eksik=None, aciklama="a"):
    return KuralSonucu(kriter=kriter, durum=durum, aciklama=aciklama, eksik=eksik)


def cevap(karar, gerekceler=("uygun",), eksikler=()):
    return EslesmeLLMCevabi(karar=karar, gerekceler=list(gerekceler), eksikler=list(eksikler))


@pytest.mark.parametrize("kurallar, llm, karar, eksikler", [
    ([kural("kesin_red", "teklif üst sınırı")], None, X, []),
    ([kural("saglar")], cevap(G), G, []),
    ([kural("saglamaz", eksik="Yetkili Satıcı Belgesi")], cevap(G), S, ["Yetkili Satıcı Belgesi"]),
    ([kural("saglar")], cevap(X), X, []),
    ([kural("saglamaz", eksik="Yetkili Satıcı Belgesi")], cevap(S, eksikler=["yetkili satici belgesi"]), S,
     ["Yetkili Satıcı Belgesi"]),
    ([], cevap(S, eksikler=["ISO 27001"]), S, ["ISO 27001"]),
])
def test_birlestir(kurallar, llm, karar, eksikler):
    sonuc = kararlari_birlestir(kurallar, llm)
    assert sonuc.karar == karar
    assert sonuc.eksikler == eksikler
    assert sonuc.kurallar == kurallar


def test_gerekceler_ucle_sinirli_ve_ust_sinir_once():
    ust = kural("saglar", "teklif üst sınırı", aciklama="İş deneyimi şartına göre … verebilirsiniz.")
    sonuc = kararlari_birlestir([ust], cevap(G, gerekceler=["1", "2", "3", "4", "5"]))
    assert sonuc.gerekceler == ["İş deneyimi şartına göre … verebilirsiniz.", "1", "2"]


@pytest.fixture
def ortam(tmp_path):
    ayar = replace(Ayarlar(), cikti_dizini=tmp_path)
    fake = FakeIstemci(lambda kw: fake_cevap(cevap(G, ["Benzer iş tanımına uyuyor."])))
    return ayar, fake, LLMIstemcisi(ayar, Depo(":memory:"), fake)


def test_kesin_red_llm_cagirmaz(ortam):
    ayar, fake, llm = ortam
    analiz = IhaleAnalizi(ozet="x", is_deneyimi_orani=0.5, yaklasik_maliyet_tl=100_000_000)
    profil = ornek_profil(is_deneyimleri=[{"tutar_tl": 1_000_000, "yil": 2024, "tur": "x"}])
    sonuc = eslestir(ornek_ihale(), analiz, Firma(1, profil, True), llm, ayar, BUGUN)
    assert sonuc.karar == X and fake.cagrilar == []


def test_eposta_llme_gitmez(ortam):
    ayar, fake, llm = ortam
    eslestir(ornek_ihale(), IhaleAnalizi(ozet="x"), Firma(1, ornek_profil(), True), llm, ayar, BUGUN)
    assert "teklif@ornek.com.tr" not in fake.cagrilar[0]["messages"][0]["content"]
    assert fake.cagrilar[0]["model"] == "claude-opus-5-5"


def test_referans_vaka(ortam):
    ayar, fake, llm = ortam
    profil = FirmaProfili.model_validate_json(Path("profil.json").read_text(encoding="utf-8"))
    analiz = IhaleAnalizi(ozet="Ağ altyapısı", is_deneyimi_orani=0.25, ciro_orani=0.25,
                          yeterlik_belgeleri=["Yetkili Satıcı Belgesi"])
    sonuc = eslestir(ornek_ihale(), analiz, Firma(1, profil, True), llm, ayar, BUGUN)
    assert sonuc.karar == S
    assert "Yetkili Satıcı Belgesi" in sonuc.eksikler
    assert next(k for k in sonuc.kurallar if k.kriter == "teklif üst sınırı").durum == "saglar"
    assert sonuc.gerekceler[0].startswith(("İş deneyimi şartına göre", "İş hacmi şartına göre"))
