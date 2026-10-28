"""EKAP v2'nin halka açık JSON API'sinden ihale toplayıcısı.

Ayrıntılar ve gerekçeler: docs/superpowers/spikes/2026-10-28-ekap-erisim-raporu.md
"""
import json
import logging
import re
import ssl
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime
from html.parser import HTMLParser
from typing import Protocol

from src.ayarlar import Ayarlar
from src.metin import tr_baslik
from src.modeller import Firma, IhaleHam
from src.on_filtre import on_filtre
from src.toplayici.kaynak import KaynakHatasi

logger = logging.getLogger(__name__)

TABAN = "https://ekapv2.kik.gov.tr/b_ihalearama/api"
TUR = {"1": "mal", "2": "yapim", "3": "hizmet"}  # 4 = danışmanlık: modelde yok → None


@dataclass(frozen=True)
class ListeOzeti:
    id: str
    ikn: str
    baslik: str
    idare: str
    il: str | None
    tur: str | None
    durum: str
    son_teklif: datetime | None


def _tarih_saat(deger) -> datetime | None:
    try:
        return datetime.strptime(deger, "%d.%m.%Y %H:%M")
    except (TypeError, ValueError):
        return None


def liste_ozeti(ham: dict) -> ListeOzeti:
    if not ham.get("ikn") or not ham.get("id"):
        raise KaynakHatasi("beklenmeyen liste öğesi")
    il = (ham.get("ihaleIlAdi") or "").strip()
    return ListeOzeti(
        id=ham["id"], ikn=ham["ikn"], baslik=ham.get("ihaleAdi") or "", idare=ham.get("idareAdi") or "",
        il=tr_baslik(il) if il else None, tur=TUR.get(str(ham.get("ihaleTip"))),
        durum=str(ham.get("ihaleDurum")), son_teklif=_tarih_saat(ham.get("ihaleTarihSaat")),
    )


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

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)

    def handle_data(self, data):
        self.parcalar.append(data)


def html_metin(html: str) -> str:
    ayristirici = _MetinCikar()
    ayristirici.feed(html)
    satirlar = (re.sub(r"[ \t\r\xa0]+", " ", s).strip() for s in "".join(ayristirici.parcalar).split("\n"))
    return "\n".join(s for s in satirlar if s)


def kalici_baglanti(ikn: str) -> str:
    """Sitenin 'Paylaş' düğmesinin ürettiği, ihale detayını doğrudan açan adres."""
    return "https://ekapv2.kik.gov.tr/ekap/search/" + ikn.replace("/", "_")


class Tasiyici(Protocol):
    def post(self, yol: str, govde: dict) -> dict: ...


def _tls_baglami() -> ssl.SSLContext:
    # Sunucu yalnızca RSA anahtar değişimli AES128-GCM-SHA256 sunuyor; OpenSSL 3 bunu varsayılan
    # güvenlik seviyesinde reddediyor. Sertifika doğrulaması açık kalır (spike raporu §5).
    baglam = ssl.create_default_context()
    baglam.set_ciphers("DEFAULT:@SECLEVEL=1")
    return baglam


class HttpTasiyici:
    """Nazik HTTP: istekler arası en az istek_araligi_sn, yalnızca 5xx/ağ hatasında 3 deneme.

    4xx veya JSON olmayan yanıt bot koruması ya da API değişikliği demektir: hemen durur, aşmaya çalışmaz.
    """

    DENEME = 3
    BEKLEMELER = (2, 4)

    def __init__(self, ayarlar: Ayarlar, acici=urllib.request.urlopen, uyku=time.sleep, saat=time.monotonic):
        self.aralik = ayarlar.istek_araligi_sn
        self.user_agent = "ekap-ajan/0.1" + (f" (+mailto:{ayarlar.iletisim_eposta})" if ayarlar.iletisim_eposta else "")
        self.acici, self.uyku, self.saat = acici, uyku, saat
        self.tls = _tls_baglami()
        self.istek_sayisi = 0
        self._son: float | None = None

    def _bekle(self) -> None:
        if self._son is not None:
            kalan = self.aralik - (self.saat() - self._son)
            if kalan > 0:
                self.uyku(kalan)
        self._son = self.saat()

    def post(self, yol: str, govde: dict) -> dict:
        veri = json.dumps(govde).encode("utf-8")
        son_hata: Exception | None = None
        for deneme in range(self.DENEME):
            if deneme:
                self.uyku(self.BEKLEMELER[deneme - 1])
            self._bekle()
            istek = urllib.request.Request(TABAN + yol, data=veri, method="POST", headers={
                "Content-Type": "application/json", "Accept": "application/json", "User-Agent": self.user_agent})
            self.istek_sayisi += 1
            try:
                with self.acici(istek, timeout=30, context=self.tls) as yanit:
                    ham = yanit.read()
            except urllib.error.HTTPError as hata:
                if hata.code < 500:
                    raise KaynakHatasi(f"{yol}: HTTP {hata.code} (bot koruması veya API değişikliği olabilir)") from hata
                son_hata = hata
            except (urllib.error.URLError, TimeoutError, ConnectionError) as hata:
                son_hata = hata
            else:
                try:
                    sonuc = json.loads(ham.decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError):
                    sonuc = None
                if not isinstance(sonuc, dict):
                    raise KaynakHatasi(f"{yol}: JSON olmayan yanıt (bot koruması veya API değişikliği olabilir)")
                return sonuc
            logger.warning("EKAP %s deneme %d başarısız: %s", yol, deneme + 1, son_hata)
        raise KaynakHatasi(f"{yol}: {self.DENEME} deneme başarısız: {son_hata}")


def ihale_ham_olustur(ozet: ListeOzeti, detay: dict) -> IhaleHam:
    item = detay.get("item") if isinstance(detay, dict) else None
    if not isinstance(item, dict):
        raise KaynakHatasi("beklenmeyen detay yanıtı")
    ilanlar = item.get("ilanList") or []
    ilk_tarih = (ilanlar[0].get("ilanTarihi") or "")[:10] if ilanlar else ""
    return IhaleHam(
        ikn=ozet.ikn, baslik=ozet.baslik, idare=ozet.idare, il=ozet.il, tur=ozet.tur,
        yayin_tarihi=date.fromisoformat(ilk_tarih) if ilk_tarih else None,
        son_teklif=ozet.son_teklif, yaklasik_maliyet_tl=None,
        okas_kodlari=[o["kodu"] for o in item.get("ihtiyacKalemiOkasList") or [] if o.get("kodu")],
        metin="\n\n".join(html_metin(i.get("veriHtml") or "") for i in ilanlar).strip(),
        kaynak_url=kalici_baglanti(ozet.ikn), kaynak="ekap",
    )


SAYFA = 50
LISTE = "/Ihale/GetListByParameters"
DETAY = "/IhaleDetay/GetByIhaleIdIhaleDetay"


class EkapKaynagi:
    """İki aşamalı toplama: liste → (yalnızca liste alanlarıyla) ön seçim → seçilenlerin detayı.

    Listedeki `id` kararsız olduğu için detay, o id'nin geldiği sayfanın hemen ardından çekilir ve id saklanmaz.
    """

    ad = "ekap"

    def __init__(self, tasiyici: Tasiyici, on_secici: Callable[[ListeOzeti], bool] = lambda o: True,
                 bilinen: Callable[[str], bool] = lambda ikn: False, bugun: Callable[[], date] = date.today):
        self.tasiyici = tasiyici
        self.on_secici = on_secici
        self.bilinen = bilinen
        self.bugun = bugun
        self.son_istatistik: dict[str, int] = {}

    def _detay(self, ozet: ListeOzeti, ist: dict) -> IhaleHam | None:
        try:
            detay = self.tasiyici.post(DETAY, {"ihaleId": ozet.id})
        except KaynakHatasi as hata:
            if str(hata).startswith("/IhaleDetay") and "3 deneme" in str(hata):
                ist["detay_hatasi"] += 1
                logger.warning("EKAP detay alınamadı, sonraki çalışmada denenecek: %s (%s)", ozet.ikn, hata)
                return None
            raise
        ist["detay"] += 1
        return ihale_ham_olustur(ozet, detay)

    def yeni_ihaleleri_getir(self, since: date) -> list[IhaleHam]:
        ist = dict.fromkeys(("listelenen", "acik", "bilinen", "secilmeyen", "detay", "detay_hatasi"), 0)
        self.son_istatistik = ist
        toplanan: list[IhaleHam] = []
        gorulen: set[str] = set()
        govde = {"ilanTarihSaatBaslangic": f"{since}T00:00:00", "ilanTarihSaatBitis": f"{self.bugun()}T23:59:59",
                 "paginationTake": SAYFA}
        atla = 0
        try:
            while True:
                yanit = self.tasiyici.post(LISTE, {**govde, "paginationSkip": atla})
                liste, toplam = yanit.get("list"), yanit.get("totalCount")
                if not isinstance(liste, list) or not isinstance(toplam, int):
                    raise KaynakHatasi("beklenmeyen liste yanıtı")
                ist["listelenen"] += len(liste)
                for ham in liste:
                    ozet = liste_ozeti(ham)
                    if ozet.durum != "2" or ozet.ikn in gorulen:
                        continue
                    gorulen.add(ozet.ikn)
                    ist["acik"] += 1
                    if self.bilinen(ozet.ikn):
                        ist["bilinen"] += 1
                    elif not self.on_secici(ozet):
                        ist["secilmeyen"] += 1
                    elif (ihale := self._detay(ozet, ist)) is not None:
                        toplanan.append(ihale)
                if not liste or atla + SAYFA >= toplam:
                    break
                atla += SAYFA
        except KaynakHatasi as hata:
            logger.error("EKAP toplama yarıda kesildi (%d ihale kurtarıldı): %s", len(toplanan), hata)
            raise KaynakHatasi(str(hata), kismi=toplanan) from hata
        logger.info("EKAP: %(listelenen)d listelendi, %(acik)d açık, %(bilinen)d zaten kayıtlı, "
                    "%(secilmeyen)d seçilmedi, %(detay)d detay çekildi, %(detay_hatasi)d detay hatası", ist)
        return toplanan


def liste_secici(firmalar: list[Firma], ayarlar: Ayarlar, bugun: date) -> Callable[[ListeOzeti], bool]:
    """Herhangi bir aktif firmanın ön filtresinden (faaliyet kuralı hariç) geçebilecek ihaleleri seçer."""
    def sec(ozet: ListeOzeti) -> bool:
        ihale = IhaleHam(ikn=ozet.ikn, baslik=ozet.baslik, idare=ozet.idare, il=ozet.il, tur=ozet.tur,
                         son_teklif=ozet.son_teklif, metin="", kaynak_url=kalici_baglanti(ozet.ikn))
        return any(on_filtre(ihale, f.profil, bugun, ayarlar, faaliyet_kontrolu=False).gecti for f in firmalar)
    return sec
