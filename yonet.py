"""Yönetim CLI'si: firmalar, profiller, elle ve zamanlanmış çalıştırma."""
import argparse
import json
import sys
import traceback
from datetime import date
from pathlib import Path

from pydantic import ValidationError

from src.ayarlar import Ayarlar, ayarlari_yukle
from src.calisma import gunluk_calistir, kayit_kur, ozet_metni
from src.depo import Depo
from src.eposta import DosyaGonderici, SmtpGonderici, yonetici_uyar
from src.modeller import FirmaProfili
from src.rapor import ozet_olustur
from src.toplayici.dosya_kaynagi import DosyaKaynagi
from src.yardimci import LLMIstemcisi

SABLON = {
    "ad": "",
    "eposta": [],
    "ihale_turleri": [],
    "anahtar_kelimeler": [],
    "okas_kodlari": [],
    "hizmet_illeri": [],
    "tipik_ihale_buyuklugu": {"min_tl": None, "max_tl": None},
    "belgeler": [],
    "is_deneyimleri": [{"tutar_tl": 0, "yil": 2025, "tur": ""}],
    "mali": {"ciro_tl": None, "ozkaynak_tl": None, "banka_referans_tl": None},
    "notlar": "",
}


def _hata(mesaj: str) -> int:
    print(mesaj, file=sys.stderr)
    return 1


def _profil_oku(dosya: str) -> FirmaProfili | None:
    """Profili okur ve doğrular; hatalıysa alan yollarını stderr'e yazar ve None döner."""
    try:
        return FirmaProfili.model_validate_json(Path(dosya).read_text(encoding="utf-8"))
    except FileNotFoundError:
        _hata(f"Dosya bulunamadı: {dosya}")
    except ValidationError as hata:
        for e in hata.errors():
            _hata(f"{'.'.join(str(p) for p in e['loc']) or '(kök)'}: {e['msg']}")
    return None


def _json(profil: FirmaProfili) -> str:
    return json.dumps(profil.model_dump(mode="json"), ensure_ascii=False, indent=2)


def _firma(arg, depo: Depo) -> int:
    if arg.komut == "sablon":
        print(json.dumps(SABLON, ensure_ascii=False, indent=2))
        return 0
    if arg.komut == "listele":
        print(f"{'id':>3}  {'ad':<40} {'durum':<11} eposta")
        for f in depo.firmalar(sadece_aktif=False):
            durum = "aktif" if f.aktif else "durduruldu"
            print(f"{f.id:>3}  {f.profil.ad:<40} {durum:<11} {', '.join(f.profil.eposta)}")
        return 0
    if arg.komut == "ekle":
        profil = _profil_oku(arg.dosya)
        if profil is None:
            return 1
        print(f"Firma eklendi: {depo.firma_ekle(profil)} {profil.ad}")
        return 0

    firma = depo.firma_getir(arg.id)
    if firma is None:
        return _hata(f"Firma bulunamadı: {arg.id}")
    if arg.komut == "goster":
        if arg.dosya:
            Path(arg.dosya).write_text(_json(firma.profil), encoding="utf-8")
            print(f"Profil yazıldı: {arg.dosya}")
        else:
            print(_json(firma.profil))
    elif arg.komut == "duzenle":
        profil = _profil_oku(arg.dosya)
        if profil is None:
            return 1
        depo.firma_guncelle(firma.id, profil)
        print(f"Firma güncellendi: {firma.id} {profil.ad}")
    elif arg.komut in ("durdur", "aktif"):
        depo.firma_durum(firma.id, arg.komut == "aktif")
        print(f"Firma {firma.id}: {'aktif' if arg.komut == 'aktif' else 'durduruldu'}")
    return 0


def _ayristirici() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="yonet.py", description="EKAP ihale ajanı yönetimi")
    alt = ap.add_subparsers(dest="grup", required=True)

    firma = alt.add_parser("firma", help="firma işlemleri").add_subparsers(dest="komut", required=True)
    firma.add_parser("listele")
    firma.add_parser("sablon", help="boş profil JSON'u yazdırır")
    firma.add_parser("ekle").add_argument("--dosya", required=True)
    goster = firma.add_parser("goster")
    goster.add_argument("id", type=int)
    goster.add_argument("--dosya")
    duzenle = firma.add_parser("duzenle")
    duzenle.add_argument("id", type=int)
    duzenle.add_argument("--dosya", required=True)
    for ad in ("durdur", "aktif"):
        firma.add_parser(ad).add_argument("id", type=int)

    profil = alt.add_parser("profil", help="profil işlemleri").add_subparsers(dest="komut", required=True)
    profil.add_parser("dogrula").add_argument("dosya")

    calistir = alt.add_parser("calistir", help="günlük çalışma (zamanlayıcı da bunu çağırır)")
    calistir.add_argument("--tarih", type=date.fromisoformat, default=None)
    calistir.add_argument("--firma", type=int, default=None)
    calistir.add_argument("--gonderme", action="store_true", help="e-posta yerine cikti/onizleme/ altına yaz")
    calistir.add_argument("--yeniden-analiz", action="store_true")

    onizle = alt.add_parser("rapor-onizle", help="saklı eşleşmelerden özeti dosyaya yazar (LLM yok)")
    onizle.add_argument("firma_id", type=int)
    onizle.add_argument("--tarih", type=date.fromisoformat, default=None)
    return ap


def _kaynaklar(ayarlar: Ayarlar) -> list:
    if ayarlar.kaynak == "dosya":
        return [DosyaKaynagi(Path("ilanlar"))]
    raise ValueError(f"bilinmeyen kaynak: {ayarlar.kaynak} (EKAP_KAYNAK)")


def _calistir(arg, depo: Depo, ayarlar: Ayarlar, gonderici, kaynaklar, llm) -> int:
    tarih = arg.tarih or date.today()
    kayit_kur(ayarlar, tarih)
    gonderici = gonderici or SmtpGonderici(ayarlar)
    try:
        o = gunluk_calistir(depo, kaynaklar if kaynaklar is not None else _kaynaklar(ayarlar), ayarlar,
                            llm or LLMIstemcisi(ayarlar, depo), gonderici, tarih, firma_id=arg.firma,
                            gonder=not arg.gonderme, yeniden_analiz=arg.yeniden_analiz)
    except Exception:
        hata = traceback.format_exc()
        print(hata, file=sys.stderr)
        yonetici_uyar(gonderici, ayarlar, "çalışma başarısız", hata)
        return 2
    print(ozet_metni(o))
    if o.hatalar or o.limit_asildi:
        yonetici_uyar(gonderici, ayarlar, "çalışma uyarısı", ozet_metni(o))
        return 1
    return 0


def _rapor_onizle(arg, depo: Depo, ayarlar: Ayarlar) -> int:
    firma = depo.firma_getir(arg.firma_id)
    if firma is None:
        return _hata(f"Firma bulunamadı: {arg.firma_id}")
    tarih = arg.tarih or date.today()
    oz = firma.profil.ozet()
    ozet = ozet_olustur(firma.profil.ad, depo.gonderilmemis_eslesmeler(firma.id, oz),
                        depo.uygun_olmayan_sayisi(firma.id, oz), tarih)
    if ozet is None:
        print("Gösterilecek uygun ihale yok.")
        return 0
    dizin = ayarlar.cikti_dizini / "onizleme" / str(tarih)
    DosyaGonderici(dizin).gonder(firma.profil.eposta, ozet, f"firma-{firma.id}")
    print(f"Önizleme: {dizin / f'firma-{firma.id}.html'}")
    return 0


def ana(argv: list[str] | None = None, depo: Depo | None = None, ayarlar: Ayarlar | None = None,
        gonderici=None, kaynaklar: list | None = None, llm: LLMIstemcisi | None = None) -> int:
    arg = _ayristirici().parse_args(argv)
    if arg.grup == "profil":
        if _profil_oku(arg.dosya) is None:
            return 1
        print("Profil geçerli.")
        return 0
    ayarlar = ayarlar or ayarlari_yukle()
    if depo is None:
        depo = Depo(ayarlar.db_yolu)
    if arg.grup == "calistir":
        return _calistir(arg, depo, ayarlar, gonderici, kaynaklar, llm)
    if arg.grup == "rapor-onizle":
        return _rapor_onizle(arg, depo, ayarlar)
    return _firma(arg, depo)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    sys.exit(ana())
