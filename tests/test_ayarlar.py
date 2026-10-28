import pytest

from src.ayarlar import ayarlari_yukle


def test_varsayilanlar():
    a = ayarlari_yukle({})
    assert a.model_analiz == "claude-sonnet-5-5"
    assert a.model_eslestirme == "claude-opus-5-5"
    assert a.gunluk_limit_usd == 5.0
    assert a.min_gun_kalan == 3
    assert a.haftalik_bos_not is False


def test_env_ezer():
    a = ayarlari_yukle({
        "EKAP_MODEL_ANALIZ": "claude-haiku-5-5",
        "EKAP_GUNLUK_LIMIT_USD": "2",
        "EKAP_HAFTALIK_BOS_NOT": "evet",
    })
    assert a.model_analiz == "claude-haiku-5-5"
    assert a.gunluk_limit_usd == 2.0
    assert a.haftalik_bos_not is True


def test_iletisim_eposta():
    assert ayarlari_yukle({"EKAP_ILETISIM_EPOSTA": "a@b.com"}).iletisim_eposta == "a@b.com"
    assert ayarlari_yukle({}).iletisim_eposta == ""


def test_sifre_repr_gizli():
    assert "gizli123" not in repr(ayarlari_yukle({"SMTP_SIFRE": "gizli123"}))


def test_bilinmeyen_model():
    with pytest.raises(ValueError, match="fiyat tablosunda yok"):
        ayarlari_yukle({"EKAP_MODEL_ANALIZ": "claude-x"})
