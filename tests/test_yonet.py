import json

import pytest

import yonet
from src.depo import Depo
from src.modeller import FirmaProfili


@pytest.fixture
def depo():
    return Depo(":memory:")


def profil_dosyasi(tmp_path, **degisiklik):
    veri = json.loads(open("profil.json", encoding="utf-8").read())
    veri.update(degisiklik)
    yol = tmp_path / "p.json"
    yol.write_text(json.dumps(veri, ensure_ascii=False), encoding="utf-8")
    return str(yol)


def test_firma_ekle_ve_listele(tmp_path, depo, capsys):
    assert yonet.ana(["firma", "ekle", "--dosya", profil_dosyasi(tmp_path)], depo=depo) == 0
    capsys.readouterr()
    assert yonet.ana(["firma", "listele"], depo=depo) == 0
    cikti = capsys.readouterr().out
    assert "1" in cikti and "Örnek Ağ Teknolojileri" in cikti and "aktif" in cikti


def test_firma_ekle_gecersiz(tmp_path, depo, capsys):
    dosya = profil_dosyasi(tmp_path, tipik_ihale_buyuklugu={"min_tl": 5_000_000, "max_tl": 1_000_000})
    assert yonet.ana(["firma", "ekle", "--dosya", dosya], depo=depo) == 1
    assert "tipik_ihale_buyuklugu" in capsys.readouterr().err
    assert depo.firmalar(sadece_aktif=False) == []


def test_firma_durdur_aktif(tmp_path, depo, capsys):
    yonet.ana(["firma", "ekle", "--dosya", profil_dosyasi(tmp_path)], depo=depo)
    yonet.ana(["firma", "durdur", "1"], depo=depo)
    capsys.readouterr()
    yonet.ana(["firma", "listele"], depo=depo)
    assert "durduruldu" in capsys.readouterr().out
    yonet.ana(["firma", "aktif", "1"], depo=depo)
    yonet.ana(["firma", "listele"], depo=depo)
    assert "durduruldu" not in capsys.readouterr().out


def test_firma_duzenle(tmp_path, depo):
    yonet.ana(["firma", "ekle", "--dosya", profil_dosyasi(tmp_path)], depo=depo)
    assert yonet.ana(["firma", "duzenle", "1", "--dosya", profil_dosyasi(tmp_path, ad="Yeni Ad")], depo=depo) == 0
    assert depo.firma_getir(1).profil.ad == "Yeni Ad"


def test_firma_goster_dosyaya(tmp_path, depo):
    yonet.ana(["firma", "ekle", "--dosya", profil_dosyasi(tmp_path)], depo=depo)
    hedef = tmp_path / "cikis.json"
    assert yonet.ana(["firma", "goster", "1", "--dosya", str(hedef)], depo=depo) == 0
    assert FirmaProfili.model_validate_json(hedef.read_text(encoding="utf-8")).ad.startswith("Örnek")


def test_profil_dogrula(tmp_path, capsys):
    assert yonet.ana(["profil", "dogrula", profil_dosyasi(tmp_path)]) == 0
    assert "Profil geçerli." in capsys.readouterr().out
    assert yonet.ana(["profil", "dogrula", profil_dosyasi(tmp_path, eposta=["firma.com"])]) == 1


def test_sablon_alanlari(depo, capsys):
    assert yonet.ana(["firma", "sablon"], depo=depo) == 0
    assert json.loads(capsys.readouterr().out).keys() == FirmaProfili.model_fields.keys()


def _ayar(tmp_path):
    from dataclasses import replace

    from src.ayarlar import Ayarlar
    return replace(Ayarlar(), veri_dizini=tmp_path / "veri", cikti_dizini=tmp_path / "cikti",
                   yonetici_eposta="yonetici@ornek.com")


def test_calistir_beklenmeyen_hata(tmp_path, depo, monkeypatch):
    from tests.sahte import FakeKaynak, KayitGonderici

    def patla(*a, **k):
        raise RuntimeError("beklenmeyen")

    monkeypatch.setattr(yonet, "gunluk_calistir", patla)
    gonderici = KayitGonderici()
    kod = yonet.ana(["calistir"], depo=depo, ayarlar=_ayar(tmp_path), gonderici=gonderici,
                    kaynaklar=[FakeKaynak([])])
    assert kod == 2
    alicilar, ozet, _ = gonderici.gonderilenler[0]
    assert alicilar == ["yonetici@ornek.com"] and "çalışma başarısız" in ozet.konu
    assert "beklenmeyen" in ozet.metin


def test_calistir_ozet_yazar(tmp_path, depo, capsys):
    from tests.sahte import FakeKaynak, KayitGonderici
    kod = yonet.ana(["calistir", "--tarih", "2026-10-28"], depo=depo, ayarlar=_ayar(tmp_path),
                    gonderici=KayitGonderici(), kaynaklar=[FakeKaynak([])])
    assert kod == 0
    assert "Çalışma özeti — 28.10.2026" in capsys.readouterr().out


def test_calistir_hata_varsa_uyarir(tmp_path, depo):
    from tests.sahte import FakeKaynak, KayitGonderici
    gonderici = KayitGonderici()
    kod = yonet.ana(["calistir"], depo=depo, ayarlar=_ayar(tmp_path), gonderici=gonderici,
                    kaynaklar=[FakeKaynak(hata=OSError("bağlantı yok"))])
    assert kod == 1
    assert "çalışma uyarısı" in gonderici.gonderilenler[0][1].konu


def test_rapor_onizle(tmp_path, depo, capsys):
    from datetime import date

    from src.modeller import EslesmeSonucu, Karar
    from tests.sahte import ornek_ihale
    yonet.ana(["firma", "ekle", "--dosya", profil_dosyasi(tmp_path)], depo=depo)
    ayar = _ayar(tmp_path)
    assert yonet.ana(["rapor-onizle", "1"], depo=depo, ayarlar=ayar) == 0
    assert "Gösterilecek uygun ihale yok." in capsys.readouterr().out

    depo.ihale_kaydet(ornek_ihale("2026/1"))
    oz = depo.firma_getir(1).profil.ozet()
    depo.eslesme_kaydet("2026/1", 1, oz, EslesmeSonucu(karar=Karar.GIREBILIR, gerekceler=["uygun"]), "m", "v1")
    assert yonet.ana(["rapor-onizle", "1", "--tarih", "2026-10-28"], depo=depo, ayarlar=ayar) == 0
    assert (ayar.cikti_dizini / "onizleme" / "2026-10-28" / "firma-1.html").exists()
    assert not depo.gonderim_var_mi(1, date(2026, 10, 28))


def test_kaynak_ekap_secilir(tmp_path, depo):
    from dataclasses import replace
    from datetime import date
    ayar = _ayar(tmp_path)
    assert yonet._kaynaklar(replace(ayar, kaynak="ekap"), depo, date(2026, 10, 27))[0].ad == "ekap"
    assert yonet._kaynaklar(ayar, depo, date(2026, 10, 27))[0].ad == "dosya"
    with pytest.raises(ValueError):
        yonet._kaynaklar(replace(ayar, kaynak="x"), depo, date(2026, 10, 27))


def test_topla_dizine_yazar(tmp_path, depo, capsys):
    from src.modeller import IhaleHam
    from tests.sahte import FakeTasiyici
    hedef = tmp_path / "ilanlar"
    kod = yonet.ana(["topla", "--hepsi", "--dizin", str(hedef), "--tarih", "2026-10-27"], depo=depo,
                    ayarlar=_ayar(tmp_path), tasiyici=FakeTasiyici())
    assert kod == 0
    dosyalar = sorted(hedef.glob("*.json"))
    assert len(dosyalar) == 5
    assert all(IhaleHam.model_validate_json(d.read_text(encoding="utf-8")) for d in dosyalar)
    assert (hedef / "2026-1874068.json").exists()
    assert depo.ihale_getir("2026/1874068") is not None
    assert "5 ihale toplandı (5 yeni)" in capsys.readouterr().out


def test_topla_firma_secimi(tmp_path, depo):
    from tests.sahte import FakeTasiyici
    yonet.ana(["firma", "ekle", "--dosya", profil_dosyasi(tmp_path)], depo=depo)  # mal + hizmet, yapım yok
    t = FakeTasiyici()
    assert yonet.ana(["topla", "--tarih", "2026-10-27"], depo=depo, ayarlar=_ayar(tmp_path), tasiyici=t) == 0
    assert "yapim-ihale-id" not in t.detay_idleri()


def test_topla_hata_kismi_kaydeder(tmp_path, depo, capsys):
    from src.toplayici.kaynak import KaynakHatasi
    from tests.sahte import FakeTasiyici
    t = FakeTasiyici({("/Ihale", 50): KaynakHatasi("/Ihale/GetListByParameters: HTTP 403")})
    kod = yonet.ana(["topla", "--hepsi", "--tarih", "2026-10-27"], depo=depo, ayarlar=_ayar(tmp_path), tasiyici=t)
    assert kod == 1
    assert depo.ihale_getir("2026/1874068") is not None
    assert "HTTP 403" in capsys.readouterr().err


def test_bilinmeyen_firma(depo, capsys):
    assert yonet.ana(["firma", "durdur", "99"], depo=depo) == 1
    assert "Firma bulunamadı: 99" in capsys.readouterr().err
