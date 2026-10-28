"""İhale metninden yapılandırılmış şart çıkarımı. Her ihale için bir kez yapılır ve saklanır."""
from datetime import date

from src.ayarlar import Ayarlar
from src.depo import Depo
from src.modeller import IhaleAnalizi, IhaleHam
from src.yardimci import LLMIstemcisi

PROMPT_SURUMU = "analiz-v1"

SISTEM_ISTEMI = """Sen Türk kamu ihalesi (4734 sayılı Kanun) ilanlarını okuyan bir uzmansın. Sana bir EKAP ihale \
ilanının metni verilecek. Bir firmanın bu ihaleye girip giremeyeceğini değerlendirmek için gereken şartları \
istenen alanlara çıkar.

Kurallar:
- Yalnızca metinde yazanı kullan. Metinde olmayan bir değer için null yaz; asla tahmin etme.
- Oranları kesir olarak yaz (%25 → 0.25). Bu oranlar isteklinin TEKLİF EDİLEN BEDELİNE göredir \
("teklif edilen bedelin %25'inden az olmamak üzere").
  - is_deneyimi_orani: iş deneyim belgesi için istenen oran.
  - ciro_orani: iş hacmi için istenen oran. Metin seçenek sunuyorsa "toplam ciro" oranını yaz.
  - banka_referans_orani: bankalardan temin edilecek kullanılmamış nakdi/gayrinakdi kredi oranı.
  - ozkaynak_orani: yalnızca teklif bedeline oranla verilmiş bir özkaynak şartı varsa. Bilanço oranları \
(öz kaynaklar/toplam aktif, cari oran vb.) bu alanlara girmez; onları diger_sartlar'a yaz.
- yaklasik_maliyet_tl: yalnızca metin açıkça bir yaklaşık maliyet tutarı veriyorsa (nadirdir).
- son_teklif_tarihi: ihale (teklif verme) tarihi ve saati, ISO biçiminde (YYYY-MM-DDTHH:MM).
- yeterlik_belgeleri: yalnızca isteklinin SAHİP OLMASI gereken sertifika, belge ve yetki belgeleri \
(ör. TSE belgesi, ISO 9001, ISO/IEC 27001, Yetkili Satıcı Belgesi, Yetki Belgesi). Her ihalede istenen standart \
teklif evrakını (teklif mektubu, geçici teminat, imza beyannamesi, iş ortaklığı beyannamesi, bilanço, iş hacmi \
belgeleri, iş deneyim belgesi) bu listeye koyma.
- benzer_is_tanimi: "benzer iş" olarak kabul edilecek işlerin tanımı, kısa alıntı.
- diger_sartlar: yukarıdakilere girmeyen önemli katılım şartları, her biri kısa bir cümle.
- Kişi adlarını ve telefon numaralarını hiçbir alana kopyalama.
- ozet: ihalenin konusunu anlatan tek bir Türkçe cümle."""


def analiz_icerigi(ihale: IhaleHam) -> str:
    baslik = [
        f"İKN: {ihale.ikn}",
        f"Başlık: {ihale.baslik}",
        f"İdare: {ihale.idare}",
        f"İl: {ihale.il or 'belirtilmemiş'}",
        f"Tür: {ihale.tur or 'belirtilmemiş'}",
        f"OKAS: {', '.join(ihale.okas_kodlari) or 'belirtilmemiş'}",
    ]
    return "\n".join(baslik) + "\n\n" + ihale.metin


def analiz_al(ihale: IhaleHam, depo: Depo, llm: LLMIstemcisi, ayarlar: Ayarlar, tarih: date,
              yeniden: bool = False) -> IhaleAnalizi:
    if not yeniden:
        onbellek = depo.analiz_getir(ihale.ikn)
        if onbellek is not None:
            return onbellek
    analiz, kullanim = llm.cagir(
        islem="analiz", model=ayarlar.model_analiz, efor=ayarlar.efor_analiz, sistem=SISTEM_ISTEMI,
        icerik=analiz_icerigi(ihale), cikti_tipi=IhaleAnalizi, ikn=ihale.ikn, tarih=tarih,
    )
    depo.analiz_kaydet(ihale.ikn, analiz, ayarlar.model_analiz, PROMPT_SURUMU, kullanim)
    return analiz
