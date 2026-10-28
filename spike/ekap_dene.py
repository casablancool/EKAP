"""EKAP erişim spike'ı — ATILACAK KOD, üretimde kullanılmaz.

Bir günün ilanlarını EKAP v2'nin halka açık arama API'sinden listeler, ham
yanıtları spike/ham/ altına kaydeder, türe göre sayar ve seçilen 5 ihaleyi
IhaleHam biçiminde ilanlar/ altına yazar.

Kullanım: python spike/ekap_dene.py --tarih 2026-10-27 [--eposta yonetici@ornek.com]
"""
import argparse
import json
import re
import ssl
import sys
import time
import urllib.error
import urllib.request
from collections import Counter
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path

TABAN = "https://ekapv2.kik.gov.tr/b_ihalearama/api"
ARALIK_SN = 2.5
SAYFA = 50  # sunucunun izin verdiği en büyük sayfa boyu
TUR = {"1": "mal", "2": "yapim", "3": "hizmet", "4": None}  # 4 = danışmanlık, modelde henüz yok
KOK = Path(__file__).resolve().parent.parent
HAM = KOK / "spike" / "ham"
ILANLAR = KOK / "ilanlar"

# Sunucu yalnızca RSA anahtar değişimli AES128-GCM-SHA256 sunuyor; OpenSSL 3 bunu
# varsayılan güvenlik seviyesinde reddediyor. Sertifika doğrulaması açık kalır.
TLS = ssl.create_default_context()
TLS.set_ciphers("DEFAULT:@SECLEVEL=1")

_son_istek = 0.0
istatistik = {"istek": 0, "hata": 0, "sureler_ms": []}


def post(yol: str, govde: dict, ua: str) -> dict:
    """Nazik POST: istekler arası en az ARALIK_SN, 5xx/zaman aşımında 3 deneme."""
    global _son_istek
    veri = json.dumps(govde).encode("utf-8")
    for deneme in range(3):
        bekle = ARALIK_SN - (time.monotonic() - _son_istek)
        if bekle > 0:
            time.sleep(bekle)
        istek = urllib.request.Request(
            TABAN + yol, data=veri, method="POST",
            headers={"Content-Type": "application/json", "Accept": "application/json", "User-Agent": ua},
        )
        t0 = time.monotonic()
        _son_istek = t0
        istatistik["istek"] += 1
        try:
            with urllib.request.urlopen(istek, timeout=30, context=TLS) as yanit:
                govde_yanit = yanit.read().decode("utf-8")
            istatistik["sureler_ms"].append(round((time.monotonic() - t0) * 1000))
            return json.loads(govde_yanit)
        except urllib.error.HTTPError as hata:
            istatistik["hata"] += 1
            print(f"  HTTP {hata.code} {yol} (deneme {deneme + 1})", file=sys.stderr)
            if hata.code < 500:
                raise
        except (urllib.error.URLError, TimeoutError) as hata:
            istatistik["hata"] += 1
            print(f"  ağ hatası {yol}: {hata} (deneme {deneme + 1})", file=sys.stderr)
        time.sleep(2 ** (deneme + 1))
    raise RuntimeError(f"{yol}: 3 deneme başarısız")


class _MetinCikar(HTMLParser):
    BLOK = {"br", "p", "div", "tr", "table", "center", "li", "h1", "h2", "h3"}

    def __init__(self):
        super().__init__()
        self.parcalar: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag in self.BLOK:
            self.parcalar.append("\n")
        elif tag == "td":
            self.parcalar.append(" ")

    def handle_data(self, data):
        self.parcalar.append(data)


def html_metin(html: str) -> str:
    p = _MetinCikar()
    p.feed(html)
    satirlar = [re.sub(r"[ \t\r\xa0]+", " ", s).strip() for s in "".join(p.parcalar).split("\n")]
    return "\n".join(s for s in satirlar if s)


def gunun_listesi(tarih: str, ua: str) -> list[dict]:
    govde = {"ilanTarihSaatBaslangic": f"{tarih}T00:00:00", "ilanTarihSaatBitis": f"{tarih}T23:59:59",
             "paginationTake": SAYFA}
    liste, atla, toplam = [], 0, None
    while toplam is None or atla < toplam:
        yanit = post("/Ihale/GetListByParameters", {**govde, "paginationSkip": atla}, ua)
        toplam = yanit["totalCount"]
        liste.extend(yanit["list"])
        (HAM / f"liste-{tarih}-{atla:05d}.json").write_text(json.dumps(yanit, ensure_ascii=False), encoding="utf-8")
        atla += SAYFA
        if not yanit["list"]:
            break
    print(f"{tarih}: totalCount={toplam}, alınan={len(liste)}, tekil İKN={len({x['ikn'] for x in liste})}")
    return liste


def ihale_ham(ozet: dict, detay: dict) -> dict:
    item = detay["item"]
    ilanlar = item.get("ilanList") or []
    ilan = ilanlar[0] if ilanlar else {}
    son = datetime.strptime(ozet["ihaleTarihSaat"], "%d.%m.%Y %H:%M") if ozet.get("ihaleTarihSaat") else None
    yayin = ilan.get("ilanTarihi", "")[:10] or None
    return {
        "ikn": ozet["ikn"],
        "baslik": ozet["ihaleAdi"],
        "idare": ozet["idareAdi"],
        "il": (ozet.get("ihaleIlAdi") or "").title() or None,
        "tur": TUR.get(str(ozet.get("ihaleTip"))),
        "yayin_tarihi": yayin,
        "son_teklif": son.isoformat() if son else None,
        "yaklasik_maliyet_tl": None,  # ilanlarda yayımlanmıyor
        "okas_kodlari": [o["kodu"] for o in item.get("ihtiyacKalemiOkasList") or []],
        "metin": "\n\n".join(html_metin(i.get("veriHtml") or "") for i in ilanlar),
        "kaynak_url": "https://ekapv2.kik.gov.tr/ekap/search/" + ozet["ikn"].replace("/", "_"),  # sitenin "Paylaş" bağlantısı
        "kaynak": "ekap",
    }


BT = re.compile(r"\b(ağ|network|kablolama|switch|bilgi işlem|siber|sunucu|fiber)\b", re.I)
UYUMSUZ = re.compile(r"yemek|temizlik|akaryakıt|kömür|asfalt", re.I)


def ornek_sec(liste: list[dict]) -> list[dict]:
    secilen, gorulen = [], set()

    def ekle(kosul):
        for x in liste:
            if x["ikn"] not in gorulen and x.get("ihaleDurum") == "2" and kosul(x):
                secilen.append(x)
                gorulen.add(x["ikn"])
                return

    ekle(lambda x: bool(BT.search(x["ihaleAdi"])))
    ekle(lambda x: str(x["ihaleTip"]) == "1")
    ekle(lambda x: str(x["ihaleTip"]) == "3")
    ekle(lambda x: str(x["ihaleTip"]) == "2")
    ekle(lambda x: bool(UYUMSUZ.search(x["ihaleAdi"])))
    return secilen


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tarih", required=True)
    ap.add_argument("--eposta", default="iletisim-belirtilmedi")
    ap.add_argument("--ornek-yaz", action="store_true", help="5 örneği ilanlar/ altına yaz")
    a = ap.parse_args()
    ua = f"ekap-ajan-spike/0.1 (+mailto:{a.eposta})"
    HAM.mkdir(parents=True, exist_ok=True)

    liste = gunun_listesi(a.tarih, ua)
    print("Türe göre:", dict(Counter(x["ihaleTipAciklama"] for x in liste)))
    print("Duruma göre:", dict(Counter(x["ihaleDurumAciklama"] for x in liste)))
    print("İlk 10 il:", Counter(x["ihaleIlAdi"] for x in liste).most_common(10))

    if a.ornek_yaz:
        ILANLAR.mkdir(exist_ok=True)
        for x in ornek_sec(liste):
            detay = post("/IhaleDetay/GetByIhaleIdIhaleDetay", {"ihaleId": x["id"]}, ua)
            ad = x["ikn"].replace("/", "-")
            (HAM / f"detay-{ad}.json").write_text(json.dumps(detay, ensure_ascii=False), encoding="utf-8")
            kayit = ihale_ham(x, detay)
            (ILANLAR / f"spike-{ad}.json").write_text(json.dumps(kayit, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"  örnek: {x['ikn']} [{kayit['tur']}] {x['ihaleAdi'][:70]} — metin {len(kayit['metin'])} karakter, OKAS {kayit['okas_kodlari']}")

    s = istatistik["sureler_ms"]
    print(f"İstek: {istatistik['istek']}, hata: {istatistik['hata']}, süre ms (min/ort/maks): "
          f"{min(s)}/{sum(s) // len(s)}/{max(s)}")


if __name__ == "__main__":
    main()
