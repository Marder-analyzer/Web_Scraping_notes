from itemadapter import ItemAdapter
from scrapy.exceptions import DropItem
import re
import os


class TrendyolBotPipeline:

    def __init__(self):
        self.seen_urls = set()
        self.kaydedilen_sayisi = 0
        self.silinen_sayisi = 0

        #  Önceki çekimlerden kalan URL'leri yükle (restart koruması) 
        self.seen_urls_file = "seen_urls.txt"
        if os.path.exists(self.seen_urls_file):
            with open(self.seen_urls_file, "r", encoding="utf-8") as f:
                self.seen_urls = set(line.strip() for line in f if line.strip())

        # Dosyayı ekleme modunda aç (append) — kapanışta değil, anlık yaz
        self._seen_file_handle = open(self.seen_urls_file, "a", encoding="utf-8")

    def process_item(self, item, spider):
        url = item.get("url", "")
        clean_url = url.split("?")[0] if url else ""

        # 1. KOPYA KONTROLÜ 
        if clean_url in self.seen_urls:
            self._drop("Kopya", clean_url, spider)

        self.seen_urls.add(clean_url)
        self._seen_file_handle.write(clean_url + "\n")
        self._seen_file_handle.flush()
        item["url"] = clean_url

        #  2. FİYAT TEMİZLİĞİ 
        price_raw = item.get("price", "-1")

        # Liste geldiyse geçerli ilk değeri al
        if isinstance(price_raw, list):
            price_raw = next((p for p in price_raw if str(p).strip() not in ["-1", "", "None"]), "-1")

        price_str = str(price_raw).strip()

        if price_str in ["-1", "", "Yok", "None"]:
            self._drop("Fiyat Yok", clean_url, spider)

        try:
            item["price"] = self._fiyat_temizle(price_str)
        except ValueError:
            self._drop("Fiyat Hatası", clean_url, spider)

        #  3. ÖZELLİK (ATTRIBUTES) KONTROLÜ 
        attributes = item.get("attributes", {})
        if not attributes or attributes == {"Bilgi": "-1"}:
            # Özellik yoksa silme — sadece boş işaretle
            item["attributes"] = {}

        #  4. DEĞERLENDİRME PUANI 
        item["evaluation"] = self._sayi_temizle(
            item.get("evaluation", "-1"), float_mi=True, varsayilan=-1
        )

        #  5. DEĞERLENDİRME SAYISI 
        item["evaluation_len"] = self._sayi_temizle(
            item.get("evaluation_len", "-1"), float_mi=False, varsayilan=-1
        )

        self.kaydedilen_sayisi += 1
        spider.logger.info(
            f"KAYDEDİLDİ | Kaydedilen: {self.kaydedilen_sayisi} | Silinen: {self.silinen_sayisi}"
        )
        return item

    #  Yardımcı: DropItem + sayaç 
    def _drop(self, sebep: str, url: str, spider):
        self.silinen_sayisi += 1
        spider.logger.info(
            f"SİLİNDİ ({sebep}) | "
            f"Kaydedilen: {self.kaydedilen_sayisi} | "
            f"Silinen: {self.silinen_sayisi}"
        )
        raise DropItem(f"ÇÖPE ATILDI ({sebep}): {url}")

    #  Yardımcı: Türkçe fiyat → float 
    @staticmethod
    def _fiyat_temizle(price_str: str) -> float:
        """
        Desteklenen formatlar:
          1.250,99  →  1250.99
          1250,99   →  1250.99
          1250.99   →  1250.99  (nokta zaten ondalık)
          1250      →  1250.0
        """
        # Sadece rakam, nokta ve virgül bırak
        s = re.sub(r"[^\d.,]", "", price_str)

        if not s:
            raise ValueError(f"Fiyat boş: {price_str}")

        # İkisi de varsa: Türkçe format (1.250,99)
        if "." in s and "," in s:
            s = s.replace(".", "").replace(",", ".")
        # Sadece virgül varsa: ondalık ayracı
        elif "," in s:
            s = s.replace(",", ".")
        # Sadece nokta varsa: binlik mi ondalık mı?
        elif "." in s:
            parts = s.split(".")
            # Son kısım 3 haneli → binlik ayraç (1.250 → 1250)
            if len(parts[-1]) == 3:
                s = s.replace(".", "")
            # Aksi halde ondalık nokta (1250.99 → 1250.99)

        return round(float(s), 2)

    # Yardımcı: Genel sayı temizleyici 
    @staticmethod
    def _sayi_temizle(raw, float_mi: bool, varsayilan):
        """Liste veya string olarak gelen evaluation/evaluation_len'i temizler."""
        if isinstance(raw, list):
            raw = next((r for r in raw if str(r).strip() not in ["-1", "", "None"]), "-1")

        s = str(raw).strip()

        if s in ["-1", "", "Yok", "None", "0.0", "0"]:
            return varsayilan

        try:
            if float_mi:
                # Puanlama için (Örn: 4,5 -> 4.5)
                s_clean = re.sub(r"[^\d.,]", "", s).replace(",", ".")
                if not s_clean:
                    return varsayilan
                return round(float(s_clean), 1)
            else:
                # Yorum sayısı için (Örn: "1.250" veya "1.250 Değerlendirme" -> 1250)
                # Noktayı ve diğer her şeyi silip SADECE rakamları alıyoruz.
                s_clean = re.sub(r"[^\d]", "", s)
                if not s_clean:
                    return varsayilan
                return int(s_clean)
                
        except Exception:
            return varsayilan

    # Spider kapandığında dosyayı kapat 
    def close_spider(self, spider):
        self._seen_file_handle.close()
        spider.logger.info(
            f"Pipeline kapandı. "
            f"Toplam kaydedilen: {self.kaydedilen_sayisi}, "
            f"silinen: {self.silinen_sayisi}"
        )