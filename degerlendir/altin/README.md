# Golden set — etiketleme kılavuzu

Her dosya bir vaka:

```json
{
  "ihale": { ...IhaleHam alanları (ilanlar/*.json ile aynı)... },
  "beklenen": {
    "karar": "GİREBİLİR | ŞARTLI GİREBİLİR | GİREMEZ",
    "eksikler": ["ŞARTLI ise firmanın eksik olduğu somut şeyler"],
    "alanlar": {"is_deneyimi_orani": 0.25, "ciro_orani": 0.25, "yaklasik_maliyet_tl": null,
                "yeterlik_belgeleri": ["ISO/IEC 27001"]}
  },
  "profil": "isteğe bağlı; yoksa degerlendir/profil.json",
  "not": "bu etiketin gerekçesi"
}
```

## Nasıl etiketlenir

1. İlanı ve gerekirse idari şartnameyi okuyun.
2. `degerlendir/profil.json`'daki firma için uzman gözüyle karar verin: girebilir mi, neyi eksik?
3. `alanlar` içine yalnızca emin olduğunuz değerleri yazın. Oranlar teklif bedeline göre kesirdir (%25 → 0.25). İlanda olmayan değer `null`.
4. `not` alanına neden bu kararı verdiğinizi bir cümleyle yazın.

## Gereken karışım

En az 10, ideal olarak 20 vaka:

- ≥ 3 mal, ≥ 3 hizmet, ≥ 3 yapım
- ≥ 4 açıkça uymayan ihale (reddetmenin de test edilmesi için)
- referans vakaya benzeyen birkaç BT/ağ ihalesi

Yeni ilan toplamak için: `python spike/ekap_dene.py --tarih <gün> --ornek-yaz` (5 ilan yazar), sonra dosyayı bu klasöre vaka biçiminde kopyalayın.

**Mevcut 3 vaka taslaktır** (`not` alanında "TASLAK ETİKET"). Kararları siz doğrulayın.
