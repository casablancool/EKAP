from dataclasses import replace
from pathlib import Path

import pytest

from degerlendir.calistir import degerlendir
from degerlendir.metrikler import (alan_hatalari, eksik_bulma_orani, karisiklik_matrisi, sinif_dogrulugu,
                                   yanlis_giremez)
from src.ayarlar import Ayarlar
from src.depo import Depo
from src.eslestir import EslesmeLLMCevabi
from src.modeller import IhaleAnalizi, Karar
from src.yardimci import LLMIstemcisi
from tests.sahte import FakeIstemci, fake_cevap

G, S, X = Karar.GIREBILIR, Karar.SARTLI, Karar.GIREMEZ
CIFTLER = [(G, G), (G, S), (S, S), (X, X), (S, X)]


def test_matris_ve_dogruluk():
    matris = karisiklik_matrisi(CIFTLER)
    assert matris[G][S] == 1 and matris[S][X] == 1 and matris[X][G] == 0
    dogruluk = sinif_dogrulugu(CIFTLER)
    assert dogruluk[G] == 0.5 and dogruluk[S] == 0.5 and dogruluk[X] == 1.0
    assert sinif_dogrulugu([(G, G)])[X] is None
    assert yanlis_giremez(CIFTLER) == 1


def test_alan_hatalari():
    analiz = IhaleAnalizi(ozet="x", yaklasik_maliyet_tl=10_050_000, is_deneyimi_orani=None,
                          yeterlik_belgeleri=["yetkili satici belgesi aslı"])
    assert alan_hatalari({"yaklasik_maliyet_tl": 10_000_000}, analiz) == []
    hatalar = alan_hatalari({"yaklasik_maliyet_tl": 12_000_000}, analiz)
    assert len(hatalar) == 1 and hatalar[0].startswith("yaklasik_maliyet_tl:")
    assert alan_hatalari({"yeterlik_belgeleri": ["Yetkili Satıcı Belgesi"]}, analiz) == []
    assert alan_hatalari({"is_deneyimi_orani": None}, analiz) == []
    assert len(alan_hatalari({"is_deneyimi_orani": 0.25}, analiz)) == 1


def test_eksik_bulma_orani():
    assert eksik_bulma_orani([], ["x"]) is None
    assert eksik_bulma_orani(["Yetkili Satıcı Belgesi", "ISO 27001"], ["yetkili satıcı belgesi"]) == 0.5


def test_degerlendir_sahte_llm(tmp_path):
    def cevap(kw):
        if kw["output_format"] is IhaleAnalizi:
            return fake_cevap(IhaleAnalizi(ozet="x"))
        return fake_cevap(EslesmeLLMCevabi(karar=G, gerekceler=["uygun"]))

    ayar = replace(Ayarlar(), cikti_dizini=tmp_path, gunluk_limit_usd=10)
    depo = Depo(":memory:")
    sonuc = degerlendir(Path("degerlendir/altin"), LLMIstemcisi(ayar, depo, FakeIstemci(cevap)), ayar)
    assert {"matris", "dogruluk", "yanlis_giremez", "maliyet_ihale_basi", "vakalar"} <= sonuc.keys()
    assert len(sonuc["vakalar"]) == len(list(Path("degerlendir/altin").glob("*.json"))) >= 2
    assert all(v["maliyet_usd"] >= 0 for v in sonuc["vakalar"])
