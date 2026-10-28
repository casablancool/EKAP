# EKAP İhale Ajanı

## 1. Ne yapar

Her hafta içi sabah:

1. EKAP'ta yeni yayımlanan ihaleleri toplar,
2. her ihalenin şartlarını **bir kez** LLM ile çıkarır,
3. her müşteri firmanın profiliyle karşılaştırır,
4. her firmaya kısa bir Türkçe e-posta gönderir: girebileceği (✅), eksiğini giderirse girebileceği (⚠️) ihaleler ve nedenleri.

Uygun ihale yoksa e-posta gitmez. Aynı gün ikinci kez çalışırsa tekrar e-posta göndermez.

Klasörler:

| Yer | İçerik |
|---|---|
| `src/` | Kod |
| `yonet.py` | Yönetim komutları |
| `ilanlar/` | Yerel ilan dosyaları (`EKAP_KAYNAK=dosya` iken kaynak; canlı için bkz. §9) |
| `degerlendir/` | Doğruluk ölçümü |
| `dagitim/` | Sunucu dosyaları |
| `docs/` | Tasarım, planlar, müşteri profil formu |

## 2. Windows kurulumu (PowerShell)

```
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
Copy-Item .env.example .env
pytest
```

`.env` dosyasını açıp en az `ANTHROPIC_API_KEY`, SMTP ayarları ve `EKAP_YONETICI_EPOSTA` değerlerini doldurun. `.env` asla git'e girmez.

## 3. Linux / VPS kurulumu

Ubuntu/Debian üzerinde tek seferlik kurulum:

```
sudo apt install python3 python3-venv sqlite3 git
sudo useradd --system --create-home --home-dir /opt/ekap-ajan ekap
sudo -u ekap git clone <özel-repo-adresi> /opt/ekap-ajan
cd /opt/ekap-ajan
sudo -u ekap python3 -m venv .venv
sudo -u ekap .venv/bin/pip install -r requirements.txt
sudo -u ekap cp .env.example .env && sudo chmod 600 .env    # sonra .env'i doldurun
sudo chmod +x dagitim/yedekle.sh
sudo cp dagitim/ekap-ajan.service dagitim/ekap-ajan.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now ekap-ajan.timer
```

Kontrol:

```
systemctl list-timers ekap-ajan.timer           # bir sonraki çalışma zamanı
systemd-analyze calendar "Mon..Fri *-*-* 07:30:00 Europe/Istanbul"
sudo systemctl start ekap-ajan.service          # şimdi bir kez çalıştır
journalctl -u ekap-ajan -n 50                   # son çalışmanın çıktısı
```

**Yedek:** Her çalışmadan önce `veri/yedek/` altına veritabanı yedeği alınır ve 14 gün saklanır. Haftada bir bu klasörü sunucu dışına kopyalayın (ör. `scp`). Sunucu kaybolursa müşteri profilleri de kaybolur.

## 4. Gmail ile gönderim

1. Gönderici Gmail hesabında iki adımlı doğrulamayı açın.
2. Google Hesabı → Güvenlik → **Uygulama şifreleri** bölümünden bir şifre oluşturun.
3. `.env` içinde şunları ayarlayın:
   - `SMTP_SUNUCU=smtp.gmail.com`
   - `SMTP_PORT=587`
   - `SMTP_KULLANICI=<gmail adresi>`
   - `SMTP_SIFRE=<uygulama şifresi>`
   - `EKAP_GONDEREN=<gmail adresi>`

Gmail günde ~500 alıcı sınırı uygular; pilot için fazlasıyla yeterli.

## 5. Günlük işleyiş

Normalde hiçbir şey yapmanız gerekmez. Size gelebilecek e-postalar:

- **`[ekap-ajan] çalışma uyarısı`:** Çalışma tamamlandı, ama bazı ihaleler, firmalar veya kaynaklar hata verdi ya da günlük LLM limiti aşıldı. E-postada özet ve hata listesi var. Diğer firmalara özetler gitmiştir.
- **`[ekap-ajan] çalışma başarısız`:** Beklenmeyen bir hata çalışmayı durdurdu ve hiçbir müşteriye e-posta gitmedi. Hata ayrıntısı e-postada.
  - Sorunu giderdikten sonra `python yonet.py calistir` ile aynı günü yeniden çalıştırın.
  - Daha önce gönderilmiş özetler tekrar gönderilmez.

Kayıtlar: `veri/kayitlar/<tarih>.log` ve sunucuda `journalctl -u ekap-ajan`. Hatalı LLM yanıtları `cikti/_hata_*.txt` dosyalarında.

Yararlı komutlar:

| Komut | Ne yapar |
|---|---|
| `python yonet.py calistir --gonderme` | E-posta göndermeden çalıştırır; özetler `cikti/onizleme/<tarih>/` altına yazılır |
| `python yonet.py calistir --firma 3` | Yalnızca bir firma için çalıştırır |
| `python yonet.py calistir --yeniden-analiz` | Önbellekteki analizleri yok sayıp ihaleleri yeniden çıkarır (prompt değişince) |
| `python yonet.py rapor-onizle 3` | Saklı eşleşmelerden özeti dosyaya yazar; LLM çağırmaz |
| `python calistir.py ilanlar/x.json` | Tek ilanı örnek profille dener, sonucu ekrana yazar |

## 6. Yeni firma ekleme (≤ 15 dakika)

1. Firmaya [docs/musteri-profil-formu.md](docs/musteri-profil-formu.md) içindeki soruları gönderin (Google Forms'a kopyalanabilir).
2. `python yonet.py firma sablon > firma.json` ile boş bir şablon oluşturun ve yanıtlarla doldurun. Dosyanın sonundaki eşleme tablosuna bakın.
3. `python yonet.py profil dogrula firma.json` çalıştırın. Hata varsa alan adıyla gösterir.
4. `python yonet.py firma ekle --dosya firma.json` ile ekleyin. Komut firmanın numarasını (ID) yazar.
5. `python yonet.py calistir --firma <ID> --gonderme` ile e-posta göndermeden deneyin.
6. `python yonet.py rapor-onizle <ID>` ile özeti `cikti/onizleme/` altında açıp kontrol edin.

Diğer firma komutları:

| Komut | Ne yapar |
|---|---|
| `firma listele` | Tüm firmaları listeler |
| `firma goster <ID> --dosya f.json` | Profili düzenlemek için dosyaya yazar |
| `firma duzenle <ID> --dosya f.json` | Düzenlenmiş profili kaydeder |
| `firma durdur <ID>` | Firmaya e-posta gönderimini durdurur (ödeme yoksa) |
| `firma aktif <ID>` | Firmayı yeniden etkinleştirir |

Profil değişince, o firmaya henüz gönderilmemiş ihaleler yeni profille yeniden değerlendirilir.

## 7. Maliyet ve limit

- Her LLM çağrısının token ve maliyeti veritabanında tutulur. Her çalışmanın sonunda günlük toplam ve **firma başına bu ayki maliyet** yazdırılır.
- `EKAP_GUNLUK_LIMIT_USD` (varsayılan 5) aşılınca analiz durur, size uyarı gelir. O ana kadar hazır olan özetler yine de gönderilir.
- Modeller `.env` dosyasından ayarlanır:
  - `EKAP_MODEL_ANALIZ`: varsayılan `claude-sonnet-5-5`; değerlendirme yeterli bulursa `claude-haiku-5-5`
  - `EKAP_MODEL_ESLESTIRME`: varsayılan `claude-opus-5-5`
- İhale analizi tüm firmalar için bir kez yapılır. Eşleştirmeye tam metin değil yalnızca çıkarılmış şartlar gider.

## 8. Değerlendirme

Herhangi bir prompt veya model değişikliğinden önce çalıştırın. Bu komut gerçek API çağırır ve ücretlidir:

```
python degerlendir/calistir.py --model-analiz claude-haiku-5-5
python degerlendir/calistir.py --model-analiz claude-sonnet-5-5
```

Çıktı:

- sınıf başına doğruluk
- karışıklık matrisi
- **yanlış GİREMEZ sayısı** (en önemli metrik: firmanın girebileceği bir ihaleyi kaçırması)
- çıkarım alan hataları
- ihale başı maliyet

Sonuçlar `degerlendir/sonuclar/` altına kaydedilir. Vakalar `degerlendir/altin/` klasöründe; nasıl etiketleneceği `degerlendir/altin/README.md` dosyasında.

## 9. EKAP kaynağına geçiş

Varsayılan kaynak `ilanlar/` klasörüdür (deneme için). Canlı EKAP'a geçmek için `.env` dosyasında şunları ayarlayın:

```
EKAP_KAYNAK=ekap
EKAP_ILETISIM_EPOSTA=<User-Agent'ta görünecek iletişim adresi; boş bırakılabilir>
```

Toplayıcı EKAP'ın halka açık JSON API'sini kullanır (ayrıntılar: [spike raporu](docs/superpowers/spikes/2026-10-28-ekap-erisim-raporu.md)). Çalışma şekli:

- Son 3 günün ilanlarını listeler.
- Yalnızca liste bilgileriyle (tür, il, son teklif) hiçbir aktif firmanın işine yaramayacakları eler.
- Kalanların tam metnini çeker.
- İstekler arasında en az 2,5 sn bekler.

Günlük toplama, firma sayısına göre 5–15 dakika sürer.

**LLM'siz toplama:** `topla` komutu yalnızca toplar ve kaydeder; LLM çağırmaz.

```
python yonet.py topla                                  # bugünün ilanları, firma ön seçimiyle
python yonet.py topla --gun 3                          # son 3 gün
python yonet.py topla --hepsi --dizin cikti/adaylar    # tüm açık ilanlar dosyalara (golden set adayı bulmak için)
```

`--hepsi` her ilanın detayını çeker (günde ~700 istek, ~30 dk); arka planda çalıştırın.

**`kaynak ekap: … HTTP 403 / 429` veya `JSON olmayan yanıt` uyarısı:** Site bot koruması açmış ya da API değişmiş olabilir. Toplayıcı hemen durur, tekrar denemez ve korumayı aşmaya çalışmaz. O ana kadar toplanan ihalelerle günlük çalışma devam eder. Sorun sürerse spike raporunun 5–6. bölümlerine bakın.

## 10. Gizli anahtar kontrolü

Her `git push` öncesinde geçmişte anahtar olup olmadığını kontrol edin. Komut hiçbir şey yazdırmamalı.

PowerShell:

```
git log -p --all | Select-String -Pattern "sk-ant-|SMTP_SIFRE=."
```

bash:

```
git log -p --all | grep -E "sk-ant-|SMTP_SIFRE=."
```

`.env`, `veri/` ve `cikti/` klasörleri `.gitignore` ile dışarıda tutulur. Testler gerçek API'ye çıkmaz. GitHub Actions'taki test iş akışı gizli anahtar kullanmaz.
