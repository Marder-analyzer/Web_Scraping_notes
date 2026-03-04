import pymongo
from itemadapter import ItemAdapter
from scrapy.exceptions import DropItem
import re
from datetime import datetime, timezone

class TrendyolBotPipeline:

    def __init__(self):
        self.mongo_uri = "mongodb://localhost:27017/"
        self.mongo_db = "neuranovav_db"  # Asistanımızın ana veritabanı
        
        # İstatistikler
        self.yeni_urun_sayisi = 0
        self.guncellenen_fiyat_sayisi = 0
        self.silinen_sayisi = 0

    def open_spider(self, spider):
        # Spider başladığında veritabanına bağlan
        self.client = pymongo.MongoClient(self.mongo_uri)
        self.db = self.client[self.mongo_db]
        
        self.products_col = self.db["products"]
        self.prices_col = self.db["price_history"]
        self.jobs_col = self.db["jobs"]
        
        # İndeksler (background=True ile sistemi kilitlemez)
        self.products_col.create_index("url", unique=True, background=True)
        self.prices_col.create_index([("url", pymongo.ASCENDING), ("date", pymongo.ASCENDING)], unique=True, background=True)
        
        # --- GÖREV BAŞLANGICI VE İLK HEARTBEAT ---
        self.start_time = datetime.now(timezone.utc)
        self.job_id = self.start_time.strftime("%Y%m%d_%H%M%S")
        self.islenen_toplam = 0
        
        # Bot çalışmaya başlar başlamaz "Running" statüsünde kayıt açıyoruz
        self.jobs_col.insert_one({
            "job_id": self.job_id,
            "status": "Running",
            "start_time": self.start_time,
            "new_items_inserted": 0,
            "prices_updated": 0,
            "items_dropped": 0
        })

    def process_item(self, item, spider):
        adapter = ItemAdapter(item)
        
        # Spider zaten URL'yi mükemmel temizleyip satıcı/fiyat parametrelerini koruyarak gönderiyor.
        # Burada sadece olduğu gibi alıyoruz, string parçalaması YOK.
        url = adapter.get("url", "")

        # 1. FİYAT TEMİZLİĞİ
        price_raw = adapter.get("price", "-1")
        if isinstance(price_raw, list):
            price_raw = next((p for p in price_raw if str(p).strip() not in ["-1", "", "None"]), "-1")

        price_str = str(price_raw).strip()
        if price_str in ["-1", "", "Yok", "None"]:
            self._drop("Fiyat Yok", url, spider)

        try:
            temiz_fiyat = self._fiyat_temizle(price_str)
            adapter["price"] = temiz_fiyat
        except ValueError:
            self._drop("Fiyat Hatası", url, spider)

        # 2. ÖZELLİK VE DEĞERLENDİRME TEMİZLİĞİ
        attributes = adapter.get("attributes", {})
        if not attributes or attributes == {"Bilgi": "-1"}:
            adapter["attributes"] = {}

        adapter["evaluation"] = self._sayi_temizle(adapter.get("evaluation", "-1"), float_mi=True, varsayilan=-1)
        adapter["evaluation_len"] = self._sayi_temizle(adapter.get("evaluation_len", "-1"), float_mi=False, varsayilan=-1)

        # --- MONGODB UPSERT İŞLEMLERİ ---
        
        # 1. Products Koleksiyonu (Sabit Veriler)
        product_data = {
            "title": adapter.get("title"),
            "category": adapter.get("category"),
            "attributes": adapter.get("attributes"),
            "images": adapter.get("images"),
            "explanation": adapter.get("explanation"),
            "last_seen": datetime.now(timezone.utc)
        }
        
        # Ürün varsa günceller, yoksa yeni ekler (Sonucu değişkene alıyoruz)
        product_result = self.products_col.update_one(
            {"url": url}, 
            {"$set": product_data}, 
            upsert=True
        )

        # 2. Price History Koleksiyonu (Dinamik/Geçmiş Veriler)
        today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d") 
        
        price_data = {
            "price": temiz_fiyat,
            "evaluation": adapter.get("evaluation"),
            "evaluation_len": adapter.get("evaluation_len")
        }
        
        price_result = self.prices_col.update_one(
            {"url": url, "date": today_str},
            {"$set": price_data},
            upsert=True
        )

        # --- DOĞRU İSTATİSTİK SAYIMI ---
        if product_result.upserted_id:
            self.yeni_urun_sayisi += 1
        elif price_result.upserted_id or price_result.modified_count > 0:
            self.guncellenen_fiyat_sayisi += 1

        # --- HEARTBEAT (CANLI GÜNCELLEME) ---
        self.islenen_toplam += 1
        # Her 50 üründe bir veritabanındaki raporu canlı olarak günceller
        if self.islenen_toplam % 50 == 0:
            self.jobs_col.update_one(
                {"job_id": self.job_id},
                {"$set": {
                    "new_items_inserted": self.yeni_urun_sayisi,
                    "prices_updated": self.guncellenen_fiyat_sayisi,
                    "items_dropped": self.silinen_sayisi,
                    "last_ping": datetime.now(timezone.utc)
                }}
            )

        return item

    def _drop(self, sebep: str, url: str, spider):
        self.silinen_sayisi += 1
        raise DropItem(f"ÇÖPE ATILDI ({sebep}): {url}")

    @staticmethod
    def _fiyat_temizle(price_str: str) -> float:
        s = re.sub(r"[^\d.,]", "", price_str)
        if not s: raise ValueError(f"Fiyat boş: {price_str}")
        if "." in s and "," in s: s = s.replace(".", "").replace(",", ".")
        elif "," in s: s = s.replace(",", ".")
        elif "." in s:
            parts = s.split(".")
            if len(parts[-1]) == 3: s = s.replace(".", "")
        return round(float(s), 2)

    @staticmethod
    def _sayi_temizle(raw, float_mi: bool, varsayilan):
        if isinstance(raw, list):
            raw = next((r for r in raw if str(r).strip() not in ["-1", "", "None"]), "-1")
        s = str(raw).strip()
        if s in ["-1", "", "Yok", "None", "0.0", "0"]: return varsayilan
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
        end_time = datetime.now(timezone.utc)
        
        # Bot BİTTİĞİNDE durumu "Completed" olarak güncelliyoruz
        self.jobs_col.update_one(
            {"job_id": self.job_id},
            {"$set": {
                "status": "Completed",
                "end_time": end_time,
                "duration_seconds": round((end_time - self.start_time).total_seconds(), 2),
                "new_items_inserted": self.yeni_urun_sayisi,
                "prices_updated": self.guncellenen_fiyat_sayisi,
                "items_dropped": self.silinen_sayisi
            }}
        )
        self.client.close()
            
        spider.logger.info("-" * 50)
        spider.logger.info(f"JOB RAPORU BİTİRİLDİ: {self.yeni_urun_sayisi} Yeni, {self.guncellenen_fiyat_sayisi} Güncel")
        spider.logger.info("-" * 50)