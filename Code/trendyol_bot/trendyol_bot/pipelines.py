from itemadapter import ItemAdapter
from scrapy.exceptions import DropItem
import re
import os

class TrendyolBotPipeline:

    def __init__(self):
        self.seen_urls = set()
        self.kaydedilen_sayisi = 0
        self.silinen_sayisi = 0
        self.seen_urls_file = "seen_urls.txt"

    def open_spider(self, spider):
        # Spider başladığında (bir kere) çalışır.
        # Restart koruması: Önceki URL'leri hafızaya al.
        if os.path.exists(self.seen_urls_file):
            with open(self.seen_urls_file, "r", encoding="utf-8") as f:
                self.seen_urls = set(line.strip() for line in f if line.strip())
        
        # Dosyayı append modunda açıp spider boyunca açık tutuyoruz.
        self._seen_file_handle = open(self.seen_urls_file, "a", encoding="utf-8")

    def process_item(self, item, spider):
        adapter = ItemAdapter(item)
        
        # Spider zaten URL'yi mükemmel temizleyip satıcı/fiyat parametrelerini koruyarak gönderiyor.
        # Burada sadece olduğu gibi alıyoruz, string parçalaması YOK.
        url = adapter.get("url", "")

        # 1. KOPYA KONTROLÜ
        if url in self.seen_urls:
            self._drop("Kopya", url, spider)

        self.seen_urls.add(url)
        self._seen_file_handle.write(url + "\n")
        # DİKKAT: flush() kullanılmıyor, diske asenkron yazma performansı maksimize edildi.

        # 2. FİYAT TEMİZLİĞİ
        price_raw = adapter.get("price", "-1")
        if isinstance(price_raw, list):
            price_raw = next((p for p in price_raw if str(p).strip() not in ["-1", "", "None"]), "-1")

        price_str = str(price_raw).strip()

        if price_str in ["-1", "", "Yok", "None"]:
            self._drop("Fiyat Yok", url, spider)

        try:
            adapter["price"] = self._fiyat_temizle(price_str)
        except ValueError:
            self._drop("Fiyat Hatası", url, spider)

        # 3. ÖZELLİK (ATTRIBUTES) KONTROLÜ
        attributes = adapter.get("attributes", {})
        if not attributes or attributes == {"Bilgi": "-1"}:
            adapter["attributes"] = {}

        # 4. DEĞERLENDİRME PUANI VE SAYISI
        adapter["evaluation"] = self._sayi_temizle(
            adapter.get("evaluation", "-1"), float_mi=True, varsayilan=-1
        )
        adapter["evaluation_len"] = self._sayi_temizle(
            adapter.get("evaluation_len", "-1"), float_mi=False, varsayilan=-1
        )

        self.kaydedilen_sayisi += 1
        return item

    def _drop(self, sebep: str, url: str, spider):
        self.silinen_sayisi += 1
        raise DropItem(f"ÇÖPE ATILDI ({sebep}): {url}")

    @staticmethod
    def _fiyat_temizle(price_str: str) -> float:
        s = re.sub(r"[^\d.,]", "", price_str)
        if not s:
            raise ValueError(f"Fiyat boş: {price_str}")

        if "." in s and "," in s:
            s = s.replace(".", "").replace(",", ".")
        elif "," in s:
            s = s.replace(",", ".")
        elif "." in s:
            parts = s.split(".")
            if len(parts[-1]) == 3:
                s = s.replace(".", "")

        return round(float(s), 2)

    @staticmethod
    def _sayi_temizle(raw, float_mi: bool, varsayilan):
        if isinstance(raw, list):
            raw = next((r for r in raw if str(r).strip() not in ["-1", "", "None"]), "-1")

        s = str(raw).strip()
        if s in ["-1", "", "Yok", "None", "0.0", "0"]:
            return varsayilan

        try:
            if float_mi:
                s_clean = re.sub(r"[^\d.,]", "", s).replace(",", ".")
                if not s_clean: return varsayilan
                return round(float(s_clean), 1)
            else:
                s_clean = re.sub(r"[^\d]", "", s)
                if not s_clean: return varsayilan
                return int(s_clean)
        except Exception:
            return varsayilan

    def close_spider(self, spider):
        # İşlem bitince dosyayı güvenlice kapatıyoruz.
        if hasattr(self, '_seen_file_handle'):
            self._seen_file_handle.close()
            
        spider.logger.info("-" * 50)
        spider.logger.info("PIPELINE KAPANIŞ RAPORU (Gerçek Veriler)")
        spider.logger.info(f"Başarıyla Kaydedilen: {self.kaydedilen_sayisi}")
        spider.logger.info(f"Çöpe Atılan (Fiyatsız/Kopya): {self.silinen_sayisi}")
        spider.logger.info("-" * 50)