"""E-posta gönderimi: SMTP (Gmail uygulama şifresiyle çalışır), dosyaya yazma (kuru çalıştırma), yönetici uyarısı."""
import html
import logging
import smtplib
from email.message import EmailMessage
from pathlib import Path
from typing import Protocol

from src.ayarlar import Ayarlar
from src.rapor import Ozet

logger = logging.getLogger(__name__)


class EpostaGonderici(Protocol):
    def gonder(self, alicilar: list[str], ozet: Ozet, etiket: str) -> None: ...


class SmtpGonderici:
    def __init__(self, ayarlar: Ayarlar):
        self.ayarlar = ayarlar

    def gonder(self, alicilar: list[str], ozet: Ozet, etiket: str) -> None:
        a = self.ayarlar
        mesaj = EmailMessage()
        mesaj["From"] = a.gonderen
        mesaj["To"] = ", ".join(alicilar)
        mesaj["Subject"] = ozet.konu
        mesaj.set_content(ozet.metin)
        mesaj.add_alternative(ozet.html, subtype="html")
        if a.smtp_port == 465:
            baglanti = smtplib.SMTP_SSL(a.smtp_sunucu, a.smtp_port, timeout=30)
        else:
            baglanti = smtplib.SMTP(a.smtp_sunucu, a.smtp_port, timeout=30)
        with baglanti as smtp:
            if a.smtp_port != 465:
                smtp.starttls()
            smtp.login(a.smtp_kullanici, a.smtp_sifre)
            smtp.send_message(mesaj)
        logger.info("e-posta gönderildi: %s (%d alıcı)", etiket, len(alicilar))


class DosyaGonderici:
    def __init__(self, dizin: Path):
        self.dizin = Path(dizin)

    def gonder(self, alicilar: list[str], ozet: Ozet, etiket: str) -> None:
        self.dizin.mkdir(parents=True, exist_ok=True)
        (self.dizin / f"{etiket}.txt").write_text(
            f"Alıcılar: {', '.join(alicilar)}\nKonu: {ozet.konu}\n\n{ozet.metin}", encoding="utf-8")
        (self.dizin / f"{etiket}.html").write_text(ozet.html, encoding="utf-8")
        logger.info("özet dosyaya yazıldı: %s", self.dizin / f"{etiket}.html")


def yonetici_uyar(gonderici: EpostaGonderici, ayarlar: Ayarlar, konu: str, metin: str) -> None:
    """Yöneticiye kısa uyarı. Asla istisna fırlatmaz: uyarının başarısızlığı çalışmayı düşürmemeli."""
    if not ayarlar.yonetici_eposta:
        logger.error("yönetici e-postası tanımlı değil; uyarı yalnızca kayda yazıldı: %s\n%s", konu, metin)
        return
    ozet = Ozet(f"[ekap-ajan] {konu}", metin, f"<pre>{html.escape(metin)}</pre>")
    try:
        gonderici.gonder([ayarlar.yonetici_eposta], ozet, "yonetici")
    except Exception:
        logger.exception("yönetici uyarısı gönderilemedi: %s", konu)
