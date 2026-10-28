from dataclasses import replace

import pytest

from src import eposta
from src.ayarlar import Ayarlar
from src.eposta import DosyaGonderici, SmtpGonderici, yonetici_uyar
from src.rapor import Ozet

OZET = Ozet(konu="EKAP: 2 uygun ihale – 28.10.2026", metin="Merhaba\nEksik: Yetkili Satıcı Belgesi",
            html="<p>Merhaba</p>")


class SahteSmtp:
    ornekler: list = []

    def __init__(self, sunucu, port, timeout=None):
        self.sunucu, self.port, self.timeout = sunucu, port, timeout
        self.tls = False
        self.giris = None
        self.mesajlar = []
        SahteSmtp.ornekler.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def starttls(self):
        self.tls = True

    def login(self, kullanici, sifre):
        self.giris = (kullanici, sifre)

    def send_message(self, mesaj):
        self.mesajlar.append(mesaj)


@pytest.fixture
def smtp(monkeypatch):
    SahteSmtp.ornekler = []
    monkeypatch.setattr(eposta.smtplib, "SMTP", SahteSmtp)
    monkeypatch.setattr(eposta.smtplib, "SMTP_SSL", SahteSmtp)
    return SahteSmtp


def ayar(**degisiklik):
    temel = dict(smtp_kullanici="ben@gmail.com", smtp_sifre="uygulama-sifresi", gonderen="ben@gmail.com",
                 yonetici_eposta="ben@gmail.com")
    temel.update(degisiklik)
    return replace(Ayarlar(), **temel)


def test_mesaj_iki_parcali(smtp):
    SmtpGonderici(ayar()).gonder(["a@firma.com", "b@firma.com"], OZET, "firma-1")
    mesaj = smtp.ornekler[0].mesajlar[0]
    assert mesaj.get_content_type() == "multipart/alternative"
    turler = [p.get_content_type() for p in mesaj.iter_parts()]
    assert turler == ["text/plain", "text/html"]
    assert "Eksik" in mesaj.get_body(("plain",)).get_content()
    assert str(mesaj["Subject"]) == "EKAP: 2 uygun ihale – 28.10.2026"
    assert mesaj["To"] == "a@firma.com, b@firma.com"


def test_port_587_starttls(smtp):
    SmtpGonderici(ayar(smtp_port=587)).gonder(["a@firma.com"], OZET, "firma-1")
    s = smtp.ornekler[0]
    assert s.tls is True and s.giris == ("ben@gmail.com", "uygulama-sifresi") and s.timeout == 30


def test_port_465_ssl(monkeypatch):
    kullanilan = []
    monkeypatch.setattr(eposta.smtplib, "SMTP_SSL", lambda *a, **k: kullanilan.append("ssl") or SahteSmtp(*a, **k))
    monkeypatch.setattr(eposta.smtplib, "SMTP", lambda *a, **k: kullanilan.append("plain") or SahteSmtp(*a, **k))
    SmtpGonderici(ayar(smtp_port=465)).gonder(["a@firma.com"], OZET, "firma-1")
    assert kullanilan == ["ssl"] and SahteSmtp.ornekler[-1].tls is False


def test_dosya_gonderici(tmp_path):
    DosyaGonderici(tmp_path).gonder(["a@firma.com"], OZET, "firma-1")
    metin = (tmp_path / "firma-1.txt").read_text(encoding="utf-8")
    assert "a@firma.com" in metin and OZET.konu in metin and "Yetkili Satıcı" in metin
    assert (tmp_path / "firma-1.html").read_text(encoding="utf-8") == OZET.html


def test_yonetici_uyar_hata_yutar(caplog):
    class Bozuk:
        def gonder(self, *a):
            raise OSError("SMTP kapalı")

    yonetici_uyar(Bozuk(), ayar(), "çalışma başarısız", "ayrıntı")
    assert "SMTP kapalı" in caplog.text


def test_yonetici_uyar_konu_ve_kacis():
    alinan = []

    class Kayit:
        def gonder(self, alicilar, ozet, etiket):
            alinan.append((alicilar, ozet, etiket))

    yonetici_uyar(Kayit(), ayar(), "çalışma başarısız", "hata <x>")
    alicilar, ozet, etiket = alinan[0]
    assert alicilar == ["ben@gmail.com"] and etiket == "yonetici"
    assert ozet.konu == "[ekap-ajan] çalışma başarısız" and "&lt;x&gt;" in ozet.html
