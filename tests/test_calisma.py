from dataclasses import replace
from datetime import date

import pytest

from src.ayarlar import Ayarlar
from src.calisma import gunluk_calistir, ozet_metni
from src.depo import Depo
from src.eslestir import EslesmeLLMCevabi
from src.modeller import IhaleAnalizi, Karar
from src.yardimci import LLMIstemcisi
from tests.sahte import FakeIstemci, FakeKaynak, KayitGonderici, fake_cevap, ornek_ihale, ornek_profil

CARSAMBA = date(2026, 10, 28)
CUMA = date(2026, 10, 30)


class Ortam:
    def __init__(self, tmp_path, reddedilen_ikn: str | None = None, **ayar):
        self.ayar = replace(Ayarlar(), veri_dizini=tmp_path / "veri", cikti_dizini=tmp_path / "cikti", **ayar)
        self.depo = Depo(":memory:")
        self.reddedilen_ikn = reddedilen_ikn
        self.fake = FakeIstemci(self._cevap)
        self.llm = LLMIstemcisi(self.ayar, self.depo, self.fake)
        self.gonderici = KayitGonderici()

    def _cevap(self, kw):
        if self.reddedilen_ikn and self.reddedilen_ikn in kw["messages"][0]["content"]:
            return fake_cevap(None, stop_reason="refusal")
        if kw["output_format"] is IhaleAnalizi:
            return fake_cevap(IhaleAnalizi(ozet="Ağ altyapısı işi"))
        return fake_cevap(EslesmeLLMCevabi(karar=Karar.GIREBILIR, gerekceler=["uygun"]))

    def cagri(self, islem_modeli: str) -> int:
        return sum(1 for c in self.fake.cagrilar if c["model"] == islem_modeli)

    @property
    def analiz_cagrisi(self):
        return sum(1 for c in self.fake.cagrilar if c["output_format"] is IhaleAnalizi)

    @property
    def eslestirme_cagrisi(self):
        return sum(1 for c in self.fake.cagrilar if c["output_format"] is EslesmeLLMCevabi)

    def calistir(self, ihaleler=None, tarih=CARSAMBA, kaynaklar=None, gonderici=None, **kw):
        kaynaklar = kaynaklar if kaynaklar is not None else [FakeKaynak(ihaleler or [])]
        return gunluk_calistir(self.depo, kaynaklar, self.ayar, self.llm, gonderici or self.gonderici, tarih, **kw)


def iki_ihale():
    return [ornek_ihale("2026/1"), ornek_ihale("2026/2")]


def test_uctan_uca_gonderir(tmp_path):
    o = Ortam(tmp_path)
    o.depo.firma_ekle(ornek_profil())
    sonuc = o.calistir(iki_ihale())
    assert len(o.gonderici.gonderilenler) == 1
    alicilar, ozet, etiket = o.gonderici.gonderilenler[0]
    assert alicilar == ["teklif@ornek.com.tr"] and etiket == "firma-1" and "2 uygun ihale" in ozet.konu
    assert o.depo.gonderim_var_mi(1, CARSAMBA)
    assert (sonuc.yeni, sonuc.analiz_edilen, sonuc.eslestirilen, sonuc.gonderilen) == (2, 2, 2, 1)
    assert sonuc.hatalar == []
    assert "Firma 1: bu ay $" in ozet_metni(sonuc)


def test_ayni_gun_tekrar_calisma(tmp_path):
    o = Ortam(tmp_path)
    o.depo.firma_ekle(ornek_profil())
    o.calistir(iki_ihale())
    cagri_sayisi = len(o.fake.cagrilar)
    ikinci = o.calistir(iki_ihale())
    assert len(o.gonderici.gonderilenler) == 1
    assert len(o.fake.cagrilar) == cagri_sayisi
    assert ikinci.atlanan_gonderim == 1 and ikinci.yeni == 0


def test_ertesi_gun_ayni_ihale_tekrar_gonderilmez(tmp_path):
    o = Ortam(tmp_path)
    o.depo.firma_ekle(ornek_profil())
    o.calistir(iki_ihale())
    o.calistir(iki_ihale(), tarih=date(2026, 10, 29))
    assert len(o.gonderici.gonderilenler) == 1


def test_analiz_bir_kez_coklu_firma(tmp_path):
    o = Ortam(tmp_path)
    o.depo.firma_ekle(ornek_profil(ad="A", eposta=["a@a.com"]))
    o.depo.firma_ekle(ornek_profil(ad="B", eposta=["b@b.com"]))
    o.calistir([ornek_ihale("2026/1")])
    assert o.analiz_cagrisi == 1 and o.eslestirme_cagrisi == 2
    assert len(o.gonderici.gonderilenler) == 2


def test_bir_ihale_hatasi_calismayi_durdurmaz(tmp_path):
    o = Ortam(tmp_path, reddedilen_ikn="2026/1")
    o.depo.firma_ekle(ornek_profil())
    sonuc = o.calistir(iki_ihale())
    assert len(o.gonderici.gonderilenler) == 1
    assert "1 uygun ihale" in o.gonderici.gonderilenler[0][1].konu
    assert any("2026/1" in h for h in sonuc.hatalar)


def test_kaynak_hatasi_devam(tmp_path):
    o = Ortam(tmp_path)
    o.depo.firma_ekle(ornek_profil())
    sonuc = o.calistir(kaynaklar=[FakeKaynak(hata=OSError("bağlantı yok"), ad="bozuk"), FakeKaynak(iki_ihale())])
    assert len(o.gonderici.gonderilenler) == 1
    assert any("kaynak bozuk" in h for h in sonuc.hatalar)


def test_limit_asilinca_analiz_durur(tmp_path):
    o = Ortam(tmp_path, gunluk_limit_usd=0.0001)
    o.depo.firma_ekle(ornek_profil())
    sonuc = o.calistir(iki_ihale())
    assert sonuc.limit_asildi is True
    assert len(o.fake.cagrilar) == 1


def test_smtp_hatasi_digerlerini_durdurmaz_ve_tekrar_dener(tmp_path):
    o = Ortam(tmp_path)
    o.depo.firma_ekle(ornek_profil(ad="A", eposta=["a@a.com"]))
    o.depo.firma_ekle(ornek_profil(ad="B", eposta=["b@b.com"]))
    bozuk = KayitGonderici(basarisiz_alicilar={"a@a.com"})
    sonuc = o.calistir(iki_ihale(), gonderici=bozuk)
    assert [g[0] for g in bozuk.gonderilenler] == [["b@b.com"]]
    assert not o.depo.gonderim_var_mi(1, CARSAMBA)
    assert o.depo.baglanti.execute("SELECT durum FROM gonderimler WHERE firma_id = 1").fetchone()[0] == "hata"
    assert any("firma 1" in h for h in sonuc.hatalar)

    saglam = KayitGonderici()
    ikinci = o.calistir(iki_ihale(), gonderici=saglam)
    assert [g[0] for g in saglam.gonderilenler] == [["a@a.com"]]
    assert ikinci.atlanan_gonderim == 1


def test_profil_degisince_yeniden_eslestirilir(tmp_path):
    o = Ortam(tmp_path)
    o.depo.firma_ekle(ornek_profil())
    o.calistir([ornek_ihale("2026/1")])
    once = o.eslestirme_cagrisi
    o.depo.firma_guncelle(1, ornek_profil(notlar="yeni not"))
    o.calistir([ornek_ihale("2026/1")], tarih=date(2026, 10, 29))
    assert o.eslestirme_cagrisi == once + 1
    assert o.analiz_cagrisi == 1
    assert len(o.gonderici.gonderilenler) == 1


def test_gonderme_kapali_dosyaya_yazar(tmp_path):
    o = Ortam(tmp_path)
    o.depo.firma_ekle(ornek_profil())
    o.calistir(iki_ihale(), gonder=False)
    assert (o.ayar.cikti_dizini / "onizleme" / "2026-10-28" / "firma-1.html").exists()
    assert not o.depo.gonderim_var_mi(1, CARSAMBA)
    assert o.gonderici.gonderilenler == []


def test_haftalik_bos_not(tmp_path):
    o = Ortam(tmp_path)
    o.depo.firma_ekle(ornek_profil())
    o.calistir([], tarih=CUMA)
    assert o.gonderici.gonderilenler == []

    acik = Ortam(tmp_path, haftalik_bos_not=True)
    acik.depo.firma_ekle(ornek_profil())
    acik.calistir([], tarih=CARSAMBA)
    assert acik.gonderici.gonderilenler == []
    acik.calistir([], tarih=CUMA)
    assert len(acik.gonderici.gonderilenler) == 1
    assert "bu hafta uygun ihale çıkmadı" in acik.gonderici.gonderilenler[0][1].konu


def test_elenen_kaydedilir(tmp_path):
    o = Ortam(tmp_path)
    o.depo.firma_ekle(ornek_profil(ihale_turleri=["mal"]))
    sonuc = o.calistir([ornek_ihale("2026/9", tur="yapim")])
    assert sonuc.elenen == 1 and o.fake.cagrilar == []
    o.calistir([ornek_ihale("2026/1", tur="mal")], tarih=date(2026, 10, 29))
    assert "1 ihale daha incelendi, uygun değil." in o.gonderici.gonderilenler[0][1].metin


def test_tek_firma_secenegi(tmp_path):
    o = Ortam(tmp_path)
    o.depo.firma_ekle(ornek_profil(ad="A", eposta=["a@a.com"]))
    o.depo.firma_ekle(ornek_profil(ad="B", eposta=["b@b.com"]))
    o.calistir(iki_ihale(), firma_id=2)
    assert [g[0] for g in o.gonderici.gonderilenler] == [["b@b.com"]]
