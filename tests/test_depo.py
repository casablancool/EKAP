import sqlite3
from datetime import date, datetime

import pytest

from src.depo import GOCLER, Depo
from src.modeller import EslesmeSonucu, IhaleAnalizi, Karar, Kullanim
from tests.sahte import ornek_ihale, ornek_profil

BUGUN = date(2026, 10, 28)


def kullanim(usd: float) -> Kullanim:
    return Kullanim(model="claude-sonnet-5-5", girdi_token=100, cikti_token=10, maliyet_usd=usd)


def sonuc(karar: Karar) -> EslesmeSonucu:
    return EslesmeSonucu(karar=karar, gerekceler=["neden"])


@pytest.fixture
def depo():
    return Depo(":memory:")


def test_ihale_tekrar_kaydi(depo):
    assert depo.ihale_kaydet(ornek_ihale("2026/1")) is True
    assert depo.ihale_kaydet(ornek_ihale("2026/1")) is False
    assert depo.ihale_getir("2026/1").ikn == "2026/1"
    assert depo.baglanti.execute("SELECT COUNT(*) FROM ihaleler").fetchone()[0] == 1


def test_islenecek_ihaleler(depo):
    depo.ihale_kaydet(ornek_ihale("2026/1", son_teklif=datetime(2026, 10, 27, 10)))
    depo.ihale_kaydet(ornek_ihale("2026/2", son_teklif=datetime(2026, 11, 5, 10)))
    depo.ihale_kaydet(ornek_ihale("2026/3", son_teklif=None))
    assert sorted(i.ikn for i in depo.islenecek_ihaleler(BUGUN)) == ["2026/2", "2026/3"]


def test_analiz_onbellek_son_surum(depo):
    depo.analiz_kaydet("2026/1", IhaleAnalizi(ozet="v1"), "claude-sonnet-5-5", "analiz-v1", kullanim(0.1))
    depo.analiz_kaydet("2026/1", IhaleAnalizi(ozet="v2"), "claude-sonnet-5-5", "analiz-v2", kullanim(0.1))
    assert depo.analiz_getir("2026/1").ozet == "v2"
    assert depo.analiz_getir("2026/9") is None


def test_firma_ekle_listele_durdur(depo):
    depo.firma_ekle(ornek_profil(ad="A"))
    depo.firma_ekle(ornek_profil(ad="B"))
    depo.firma_durum(2, False)
    assert [f.id for f in depo.firmalar()] == [1]
    assert [f.id for f in depo.firmalar(sadece_aktif=False)] == [1, 2]
    assert depo.firma_getir(2).aktif is False
    assert depo.firma_getir(99) is None


def test_firma_guncelle(depo):
    depo.firma_ekle(ornek_profil(ad="A"))
    depo.firma_guncelle(1, ornek_profil(ad="Yeni"))
    assert depo.firma_getir(1).profil.ad == "Yeni"


def test_eslesme_profil_degisince_yok(depo):
    depo.eslesme_kaydet("2026/1", 1, "a", sonuc(Karar.GIREBILIR), "m", "eslestirme-v1")
    assert depo.eslesme_getir("2026/1", 1, "a") is not None
    assert depo.eslesme_getir("2026/1", 1, "b") is None
    assert depo.islendi_mi("2026/1", 1, "a") is True
    assert depo.islendi_mi("2026/1", 1, "b") is False


def test_eleme_islendi_sayilir(depo):
    depo.eleme_kaydet("2026/1", 1, "a", ["tür uyumsuz: yapim"])
    assert depo.islendi_mi("2026/1", 1, "a") is True


def test_gonderilmemis_eslesmeler(depo):
    depo.ihale_kaydet(ornek_ihale("X"))
    depo.ihale_kaydet(ornek_ihale("Y"))
    depo.eslesme_kaydet("X", 1, "a", sonuc(Karar.GIREBILIR), "m", "v1")
    depo.eslesme_kaydet("Y", 1, "a", sonuc(Karar.GIREMEZ), "m", "v1")
    satirlar = depo.gonderilmemis_eslesmeler(1, "a")
    assert [i.ikn for i, _ in satirlar] == ["X"]
    assert satirlar[0][1].karar == Karar.GIREBILIR
    depo.gonderim_kaydet(1, BUGUN, ["X"], "gonderildi")
    assert depo.gonderilmemis_eslesmeler(1, "a") == []


def test_gonderim_hata_sonra_basari(depo):
    depo.gonderim_kaydet(1, BUGUN, ["X"], "hata", "SMTP reddetti")
    assert depo.gonderim_var_mi(1, BUGUN) is False
    depo.gonderim_kaydet(1, BUGUN, ["X"], "gonderildi")
    assert depo.gonderim_var_mi(1, BUGUN) is True


def test_hafta_gonderim_var_mi(depo):
    depo.gonderim_kaydet(1, date(2026, 10, 26), [], "gonderildi")  # Pazartesi
    assert depo.hafta_gonderim_var_mi(1, date(2026, 10, 30)) is True  # aynı hafta Cuma
    assert depo.hafta_gonderim_var_mi(1, date(2026, 11, 2)) is False  # sonraki hafta


def test_bugunku_harcama(depo):
    depo.kullanim_kaydet("analiz", "X", None, kullanim(0.5), BUGUN)
    depo.kullanim_kaydet("eslestirme", "X", 1, kullanim(0.25), BUGUN)
    depo.kullanim_kaydet("analiz", "Y", None, kullanim(1.0), date(2026, 10, 27))
    assert depo.bugunku_harcama_usd(BUGUN) == pytest.approx(0.75)


def test_firma_aylik_maliyet(depo):
    depo.kullanim_kaydet("analiz", "X", None, kullanim(0.30), BUGUN)
    depo.kullanim_kaydet("eslestirme", "X", 1, kullanim(0.10), BUGUN)
    depo.eslesme_kaydet("X", 1, "a", sonuc(Karar.GIREBILIR), "m", "v1")
    depo.eslesme_kaydet("X", 2, "b", sonuc(Karar.GIREMEZ), "m", "v1")
    assert depo.firma_aylik_maliyet(1, "2026-10") == pytest.approx(0.25)
    assert depo.firma_aylik_maliyet(2, "2026-10") == pytest.approx(0.15)
    assert depo.firma_aylik_maliyet(1, "2026-11") == pytest.approx(0.0)


def test_goc_iki_kez(tmp_path):
    yol = tmp_path / "alt" / "e.db"
    Depo(yol)
    Depo(yol)
    with sqlite3.connect(yol) as b:
        assert b.execute("PRAGMA user_version").fetchone()[0] == len(GOCLER)


def test_uygun_olmayan_sayisi(depo):
    depo.eleme_kaydet("A", 1, "a", ["tür uyumsuz: yapim"])
    depo.eleme_kaydet("B", 1, "a", ["il hizmet alanı dışında: İzmir"])
    depo.eslesme_kaydet("C", 1, "a", sonuc(Karar.GIREMEZ), "m", "v1")
    assert depo.uygun_olmayan_sayisi(1, "a") == 3
    depo.gonderim_kaydet(1, BUGUN, [], "gonderildi")
    depo.eleme_kaydet("D", 1, "a", ["tür uyumsuz: yapim"])
    assert depo.uygun_olmayan_sayisi(1, "a") == 1
