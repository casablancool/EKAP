from src.metin import icerir_mi, tl_bicimle, tr_ascii, tr_baslik, tr_kucuk


def test_tr_baslik():
    assert tr_baslik("İZMİR") == "İzmir"
    assert tr_baslik("ŞANLIURFA") == "Şanlıurfa"
    assert tr_baslik("ISPARTA") == "Isparta"
    assert tr_baslik("AFYON-KARAHİSAR") == "Afyon-Karahisar"
    assert tr_baslik("KIRIKKALE") == "Kırıkkale"


def test_tr_kucuk_noktali_i():
    assert tr_kucuk("İSTANBUL") == "istanbul"
    assert tr_kucuk("ISPARTA") == "ısparta"
    assert tr_ascii("Iğdır") == "igdir"
    assert tr_ascii("İZMİR") == "izmir"


def test_icerir_mi():
    assert icerir_mi("AĞ ALTYAPISI Kurulumu", "ağ altyapısı") is True
    assert icerir_mi("x", "") is False


def test_tl_bicimle():
    assert tl_bicimle(1250000) == "1.250.000 TL"
    assert tl_bicimle(999.5) == "1.000 TL"
    assert tl_bicimle(0) == "0 TL"
