# Müşteri Profil Formu

Yeni firmaya gönderilecek sorular. Google Forms'a soru soru kopyalanabilir. Yanıtlar geldikten sonra en alttaki eşleme tablosuyla `profil.json`'a dönüştürülür.

---

## Firmaya gönderilecek metin

> Size uygun ihaleleri her sabah e-postayla gönderebilmemiz için aşağıdaki soruları yanıtlamanızı rica ederiz. Bilgileriniz yalnızca ihale eşleştirmesi için kullanılır. Emin olmadığınız soruları boş bırakabilirsiniz.

1. **Firmanızın unvanı nedir?**
   Örnek: *Örnek Ağ Teknolojileri Ltd. Şti.*

2. **İhale bildirimlerinin gideceği e-posta adres(ler)i nedir?** (virgülle ayırın)
   Örnek: *teklif@ornekag.com.tr, satis@ornekag.com.tr*

3. **Hangi tür ihalelere giriyorsunuz?** (birden fazla seçilebilir: Mal alımı / Hizmet alımı / Yapım işi)
   Örnek: *Mal alımı, Hizmet alımı*

4. **Firmanızın faaliyet alanını anlatan anahtar kelimeler nelerdir?** (ihale başlıklarında geçebilecek kelimeler, virgülle ayırın)
   Örnek: *ağ altyapısı, yapısal kablolama, fiber optik, switch, sunucu*

5. **Bildiğiniz OKAS / CPV kodları varsa yazın.** (bilmiyorsanız boş bırakın, biz bulalım)
   Örnek: *32420000, 72260000*

6. **Hangi illerdeki ihalelere giriyorsunuz?** ("Tüm Türkiye" de yazabilirsiniz)
   Örnek: *Ankara, Kırıkkale, Konya*

7. **Genelde en az kaç TL'lik ihalelere teklif veriyorsunuz?**
   Örnek: *500.000 TL*

8. **Genelde en fazla kaç TL'lik ihalelere teklif veriyorsunuz?**
   Örnek: *15.000.000 TL*

9. **Sahip olduğunuz belgeler ve sertifikalar nelerdir?** (TSE, ISO, Yetkili Satıcı, Yetki Belgesi vb., virgülle ayırın)
   Örnek: *TS EN ISO 9001, TSE Hizmet Yeterlilik Belgesi*

10. **İş deneyim belgeleriniz:** Her belge için **güncellenmiş tutar**, yıl ve işin kısa tanımı.
    Örnek: *6.000.000 TL — 2024 — Kampüs ağ altyapısı kurulumu; 2.500.000 TL — 2022 — Sunucu ve switch temini*

11. **Geçen yılki toplam cironuz (TL)?** (isteğe bağlı)
    Örnek: *18.000.000 TL*

12. **Geçen yıl sonu özkaynak tutarınız (TL)?** (isteğe bağlı)
    Örnek: *4.000.000 TL*

13. **Bankalardan alabileceğiniz kullanılmamış kredi / teminat mektubu kapasitesi (TL)?** (isteğe bağlı)
    Örnek: *3.000.000 TL*

14. **Eklemek istediğiniz bir not var mı?** (girmek istemediğiniz idareler, özel durumlar)
    Örnek: *Belediye ihalelerini tercih ediyoruz.*

---

## Yanıt → profil eşleme tablosu (yönetici için)

| Soru | Profil alanı | Dönüştürme |
|---|---|---|
| 1 | `ad` | Olduğu gibi |
| 2 | `eposta` | Virgülle ayrılmış metni listeye çevirin |
| 3 | `ihale_turleri` | Mal alımı → `"mal"`, Hizmet alımı → `"hizmet"`, Yapım işi → `"yapim"` |
| 4 | `anahtar_kelimeler` | Listeye çevirin. Çok genel kelimeleri ("hizmet", "alım") çıkarın |
| 5 | `okas_kodlari` | Yalnızca rakamlar, liste. Boşsa firmanın geçmiş ihalelerinden 2–4 haneli ön ek bulun |
| 6 | `hizmet_illeri` | Liste. "Tüm Türkiye" → `[]` |
| 7 | `tipik_ihale_buyuklugu.min_tl` | Sayı, TL (nokta ve "TL" olmadan: `500000`) |
| 8 | `tipik_ihale_buyuklugu.max_tl` | Sayı, TL |
| 9 | `belgeler` | Liste; belge adlarını ilanlarda geçtiği gibi yazın (ör. `"TS EN ISO 9001"`) |
| 10 | `is_deneyimleri` | Her belge için `{"tutar_tl": 6000000, "yil": 2024, "tur": "…"}` |
| 11 | `mali.ciro_tl` | Sayı veya `null` |
| 12 | `mali.ozkaynak_tl` | Sayı veya `null` |
| 13 | `mali.banka_referans_tl` | Sayı veya `null` |
| 14 | `notlar` | Olduğu gibi |
| 7–8 | `tipik_ihale_buyuklugu` | İki alanlı nesne: `{"min_tl": …, "max_tl": …}`; biri boşsa `null` |
| 11–13 | `mali` | Üç alanlı nesne: `{"ciro_tl": …, "ozkaynak_tl": …, "banka_referans_tl": …}` |

Sonra (≤ 15 dk):

```
python yonet.py firma sablon > firma.json        # boş şablon; yanıtlarla doldurun
python yonet.py profil dogrula firma.json
python yonet.py firma ekle --dosya firma.json
python yonet.py calistir --firma <ID> --gonderme
python yonet.py rapor-onizle <ID>
```
