# EKAP Erişim Spike Raporu

Tarih: 28.10.2026 · Plan: `docs/superpowers/plans/2026-10-28-plan1-ekap-erisim-spike.md`

**Kısa sonuç:** EKAP v2'nin kendi arayüzünün kullandığı halka açık JSON API, giriş, token, çerez veya CAPTCHA istemeden, düz Python ile çalışıyor. Bir günün tüm ilanları ~14 istekte listeleniyor, her ihalenin tam ilan metni tek bir detay isteğiyle geliyor. İki günlük denemede 32 isteğin hiçbiri hata vermedi. **Önerim: Plan 3'te toplayıcıyı bu API üzerine kurmak.**

---

## 1. Kurallar

| Kontrol | Sonuç |
|---|---|
| `https://ekap.kik.gov.tr/robots.txt` (→ `/ekap/robots.txt`) | `User-agent: *` / `Disallow:` (boş). Hiçbir yol yasaklanmamış. |
| `https://ekapv2.kik.gov.tr/robots.txt` | Dosya yok, adres uygulamanın sayfasını döndürüyor. Kısıt tanımlanmamış. |
| Kullanım koşulları | Sitede bağlantısı yok. Tek hukuki bağlantı KİK'in "Aydınlatma Metni ve Açık Rıza Metni" (ihale.gov.tr). Otomatik erişimden söz etmiyor. |
| Giriş / e-imza | Arama, liste ve ilan metni girişsiz açık. Doküman indirme ve teklif verme girişli; bunlara dokunulmadı. |
| CAPTCHA | Karşılaşılmadı. Ancak arayüz açılışta `GET /b_han/api/human-verification/status` çağırıyor: ileride bot kontrolü açılabilir. |

**Karar:** Yasaklayan bir kural yok (durum: *belirsiz, yasak değil*). Nazik erişim kuralları (2,5 sn aralık, kendini tanıtan User-Agent, yalnızca açık veriler) korunmalı. İsteğe bağlı: `ekapyardim@kik.gov.tr` adresine kısa bir bilgilendirme e-postası atılması, ileride bir sorun çıkarsa iyi niyetin kaydı olur.

## 2. Uç noktalar ve filtreler

Taban adres: `https://ekapv2.kik.gov.tr/b_ihalearama/api`. Hepsi `POST`, gövde JSON, yanıt JSON. Özel başlık gerekmiyor.

| Uç nokta | Gövde | Döndürdüğü |
|---|---|---|
| `/Ihale/GetListByParameters` | `{"ilanTarihSaatBaslangic": "2026-10-27T00:00:00", "ilanTarihSaatBitis": "2026-10-27T23:59:59", "paginationSkip": 0, "paginationTake": 50}` | `{"list": [...], "totalCount": N}`. Her öğe: `id`, `ikn`, `ihaleAdi`, `ihaleTip` (1 mal, 2 yapım, 3 hizmet, 4 danışmanlık), `ihaleUsulAciklama`, `ihaleDurum` (2 = katılıma açık, 6 = iptal), `idareAdi`, `ihaleIlAdi`, `ihaleTarihSaat` (son teklif, `gg.aa.yyyy SS:dd`) |
| `/IhaleDetay/GetByIhaleIdIhaleDetay` | `{"ihaleId": "<listeden gelen id>"}` | `item.ihaleBilgi` (iş yeri, OKAS metni, tarihler), `item.ihtiyacKalemiOkasList[].kodu`, `item.ihaleOzellikList` (iş deneyimi / mali yeterlik isteniyor mu), `item.ilanList[]` (`ilanTarihi`, `baslik`, **`veriHtml` = tam ilan metni**) |
| `/Ilan/GetList` | `{"ihaleId": "..."}` | Yalnızca ilan listesi (detayda zaten var, gerek yok) |

**Filtreler** (liste isteğinin alanları, sitenin JS paketinden okundu): `ilanTarihSaatBaslangic/Bitis`, `ihaleTarihSaatBaslangic/Bitis`, `ihaleTuruIdList`, `ihaleIlIdList`, `okasBransKodList`, `ihaleDurumIdList`, `ihaleUsulIdList`, `searchText` (+ `ihaleAdindaAra`, `ihaleIlanindaAra`, `benzerIsMaddesindeAra` …) ve "iş deneyimi belgesi isteniyor mu" gibi evet/hayır alanları.

**Sayfalama:** `paginationTake` en fazla **50** (100 ve 500 istendiğinde de 50 döndü). Bir gün için yaklaşık 14 istek gerekiyor.

**Kalıcı ilan bağlantısı:** `https://ekapv2.kik.gov.tr/ekap/search/<İKN, "/" yerine "_">`, örneğin `.../ekap/search/2026_1874068`. Sitenin "Paylaş" düğmesinin ürettiği adres bu; tarayıcıda ihale detayını doğrudan açtığı denendi.

## 3. `IhaleHam` alan eşlemesi

| Kaynak alan | Bizim alan | 5 örnekte dolu |
|---|---|---|
| `ikn` | `ikn` | 5/5 |
| `ihaleAdi` | `baslik` | 5/5 |
| `idareAdi` | `idare` | 5/5 |
| `ihaleIlAdi` | `il` | 5/5 (büyük harf; `tr_ascii` ile karşılaştırılmalı) |
| `ihaleTip` | `tur` | 5/5 (4 = danışmanlık → şimdilik `null`) |
| `ilanList[0].ilanTarihi` | `yayin_tarihi` | 5/5 |
| `ihaleTarihSaat` | `son_teklif` | 5/5 |
| — | `yaklasik_maliyet_tl` | **0/5. EKAP ilanlarında yaklaşık maliyet yayımlanmıyor.** |
| `ihtiyacKalemiOkasList[].kodu` | `okas_kodlari` | 5/5 (yalnızca detayda) |
| `ilanList[].veriHtml` → düz metin | `metin` | 5/5 (7 500–8 100 karakter) |
| paylaş deseni | `kaynak_url` | 5/5 |

Örnekler `ilanlar/` altında:

| Dosya | İçerik |
|---|---|
| `spike-2026-1874068.json` | Ağ/BT hizmeti, Ankara, DHMİ. Referans vakaya en yakın örnek: ISO/IEC 27001 istiyor, iş deneyimi teklif bedelinin %25'i. |
| `spike-2026-2061061.json` | Mal: spor malzemesi, Konya |
| `spike-2026-1998683.json` | Hizmet: CNC torna bakım, Ankara |
| `spike-2026-2082996.json` | Yapım: asfalt kaplama |
| `spike-2026-2117982.json` | Mal: akaryakıt. BT firmasına açıkça uygun değil. |

**KVKK:** Örnek metinlerde kişi adı görülmedi. Yalnızca idarenin kurumsal adresi ve telefonu var. Tasarımdaki kural (metin e-postaya konmaz) yeterli.

## 4. Hacim

| Gün | Toplam | Mal | Hizmet | Yapım | Danışmanlık |
|---|---|---|---|---|---|
| Pzt 26.10.2026 | 698 | 323 | 253 | 121 | 1 |
| Sal 27.10.2026 | 642 | 307 | 214 | 119 | 2 |

En çok ihale çıkan iller (iki gün toplamı): İstanbul 178, Ankara 164, İzmir 62, Konya 51, Antalya 35, Bursa 33.

Sektör tahmini, 1 340 ilanın **başlığından** anahtar kelimeyle yapıldı (OKAS'a göre kesin dağılım için her ihalenin detayını çekmek gerekir; yapılmadı):

| Grup | Pay | Günlük ≈ |
|---|---|---|
| Yemek / gıda | %23 | 155 |
| Bina inşaat / onarım | %13 | 86 |
| Taşıma / araç kiralama | %10 | 66 |
| Temizlik / personel / güvenlik | %9 | 61 |
| Akaryakıt / enerji | %8 | 56 |
| Tıbbi sarf / laboratuvar | %6 | 38 |
| Asfalt / yol | %5 | 32 |
| Bilişim / ağ | %2,3 | 15 |

## 5. Güvenilirlik ve riskler

- **Hız:** 32 istek, 0 hata, yanıt süresi 283–619 ms. Tarayıcıdaki aynı istekler 150–270 ms.
- **Eski TLS:** Sunucu yalnızca `AES128-GCM-SHA256` (RSA anahtar değişimi) sunuyor. OpenSSL 3 bunu varsayılan ayarda reddediyor. Çözüm: bu adrese özel bağlamda `set_ciphers("DEFAULT:@SECLEVEL=1")`. Sertifika doğrulaması açık kalıyor. Sunucu ayarı değişirse bu satır gereksiz hale gelir; kırılmaz.
- **`id` kararsız:** Aynı ihale farklı liste çağrılarında farklı `id` hash'iyle döndü. `id` asla saklanmamalı: liste → detay aynı çalışma içinde yapılmalı, kalıcı anahtar İKN olmalı.
- **Dil:** Tarayıcı dışından gelen isteklerde `ihaleDurumAciklama` İngilizce döndü ("Tender Canceled"). Kodlar (`ihaleDurum`, `ihaleTip`) kullanılmalı, açıklama metinleri değil.
- **Bot kontrolü:** `human-verification/status` uç noktası var. Ileride açılırsa toplayıcı JSON yerine farklı bir yanıt ya da 403/429 alır. O durumda toplayıcı durmalı ve yöneticiyi uyarmalı; aşmaya çalışmamalı.
- **Düzeltme ilanları (zeyilname):** `ilanList` birden çok ilan içerebiliyor. Bir ihale yayımlandıktan sonra düzeltildiğinde, İKN üzerinden tekilleştirme yaptığımız için değişiklik gözden kaçabilir. Bu iki günde gözlenmedi (açık soru 2).
- **Arayüz değişikliği:** API sitenin kendi iç API'si; belgelenmemiş, haber verilmeden değişebilir. Plan 3'te kayıtlı yanıtlarla testler ve "beklenmeyen biçim" durumunda yönetici uyarısı şart.

## 6. Önerilen yaklaşım

**EKAP v2 iç JSON API'si, iki aşamalı:**

1. **Liste:** Her sabah, son `geri_bakis_gun` (3) günün `ilanTarihSaat` aralığı için tüm sayfalar (≈ 40 istek, ≈ 2 dk). Yalnızca `ihaleDurum == "2"` (katılıma açık).
2. **Ucuz ön eleme listede:** Detay çekmeden önce yalnızca liste alanlarıyla (tür, il) **tüm aktif firmalar** için ön filtre. En az bir firmaya uyan ve veritabanında henüz olmayan ihaleler için detay isteği (5 firmayla tahminen günde 50–200 istek, 2–8 dk).
3. **Detay:** OKAS, ilan tarihi ve tam metin buradan; sonra mevcut Plan 2 akışı (OKAS + anahtar kelime filtresi, analiz, eşleştirme).

Toplama süresi günde 5–15 dakika. Zamanlayıcı 07:30'da başlarsa e-postalar 08:00 civarında çıkar.

**Bozulursa yedek:** Aynı uç noktalar tarayıcıdan çalıştığı sürece, gerekirse başsız tarayıcıyla (Playwright) aynı API'yi sayfa bağlamından çağırmak. Bu, ağır bir bağımlılık getirir; yalnızca düz HTTP kesin olarak kapanırsa düşünülmeli.

### Plan 2'ye etkileri (onayınızla güncellenecek)

1. **Yaklaşık maliyet yok.** Ön filtrenin tutar kuralı (Task 6, kural 5) pratikte hiç çalışmayacak. Kod kalabilir; recall'a zararı yok.
2. **Oranlar "teklif edilen bedel"e göre.** İş deneyimi ve iş hacmi kriterleri yaklaşık maliyete değil, firmanın kendi teklifine oranla veriliyor ("teklif edilen bedelin %25'inden az olmamak üzere"). Task 9'daki kurallar bu yüzden hep "belirsiz" çıkar. Öneri: kurallar **firmanın bu ihalede verebileceği en yüksek teklifi** hesaplasın: `min(en büyük iş deneyimi / iş deneyimi oranı, ciro / ciro oranı)`. Bu üst sınır, firmanın tipik ihale büyüklüğünün alt sınırının altındaysa ŞARTLI ("İş deneyiminizle bu ihalede en fazla 2.400.000 TL teklif verebilirsiniz"), çok altındaysa (`kesin_red_esigi`) GİREMEZ. Bu satır e-postada gerekçe olarak da çok değerli.
3. **Danışmanlık türü:** Günde 1–2 ihale; `tur = null` olarak geçer (filtreden geçer). Modele eklemek gerekmiyor.
4. **İl adları büyük harfle geliyor** ("İSTANBUL"). `tr_ascii` karşılaştırması zaten bunu çözüyor.
5. **Maliyet:** Analiz tüm ilanlara değil yalnızca ön filtreden geçenlere uygulanıyor. Yine de tek bir geniş profilli firma günde yüzlerce ihaleyi geçirebilir. Günlük limit (5 USD) ve Haiku değerlendirmesi önemli.

## 7. Plan 3 taslağı

- `src/toplayici/ekap_kaynagi.py`:
  - `EkapKaynagi(ayarlar, on_secici: Callable[[dict], bool])`, `Kaynak` protokolünü uygular
  - `_post(yol, govde)`: aralık, User-Agent (`ekap-ajan/<sürüm> (+mailto:<EKAP_YONETICI_EPOSTA>)`), 3 deneme + üstel bekleme, SECLEVEL=1 TLS bağlamı
  - `_gunun_listesi(baslangic, bitis) -> list[dict]`: sayfalama, `totalCount` doğrulaması
  - `_detay(ihale_id) -> dict`
  - `ihale_ham_olustur(ozet, detay) -> IhaleHam`: spike'taki eşleme; HTML → metin `html.parser` ile
  - Beklenmeyen biçimde (JSON değil, `list` / `item` alanı yok, 403/429) → `KaynakHatasi`, yönetici uyarısı
- Test fikstürleri: `tests/fikstur/ekap/liste-*.json` ve `detay-*.json` (`spike/ham/` içindeki yanıtlardan küçültülmüş), `urllib` yerine sahte taşıyıcı enjekte edilir; ağa çıkan test yok.
- Testler: sayfalama (`totalCount` 120 → 3 sayfa), iptal ihalesinin atlanması, `id`'nin saklanmaması, HTML → metin, kalıcı bağlantı, `ihaleTip` 4 → `None`, biçim değişince `KaynakHatasi`.
- `yonet.py calistir`: `EKAP_KAYNAK=ekap` olduğunda `EkapKaynagi`.

## 8. Açık sorular

1. **Hedef sektör:** Bilişim/ağ günde yalnızca ~15 ihale (başlığa göre). Hacim yemek, inşaat, temizlik ve taşımada çok daha yüksek. Satış erişiminiz hangi sektörde? Profil şeması ilk sektöre göre genişleyebilir (ör. yemek için "günlük öğün kapasitesi", temizlik için "personel sayısı").
2. **Zeyilname:** Düzeltme ilanları takip edilsin mi? Öneri: MVP'de hayır. Pilot sırasında bir düzeltmenin kaçırıldığı görülürse, son teklif tarihi gelmemiş ihalelerin detayını haftada bir yeniden çekmek.
3. **KİK'e bilgilendirme:** `ekapyardim@kik.gov.tr` adresine kısa bir bilgilendirme e-postası gönderilsin mi? (Gönderimi siz yaparsınız.)
4. **User-Agent e-postası:** Toplayıcının User-Agent başlığında hangi iletişim adresi yer alsın?
5. **Plan 2 değişiklikleri:** Bölüm 6'daki "en yüksek teklif" kuralı Plan 2'ye işlensin mi?
