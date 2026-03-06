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
        self.stats = {
            "yeni_urun": 0,           # Veritabanına hayatında ilk kez giren ürün
            "yeni_gun_kaydi": 0,      # Ürünü tanıyoruz ama BUGÜN ilk kez fiyatını aldık
            "gun_ici_degisim": 0,     #  fiyatı VEYA yorumu değişmiş
            "drop_fiyatsiz": 0,       
            "drop_hata": 0          
        }

    def open_spider(self, spider):
        self.client = pymongo.MongoClient(self.mongo_uri)
        self.db = self.client[self.mongo_db]
        
        self.products_col = self.db["products"]
        self.prices_col = self.db["price_history"]
        self.jobs_col = self.db["jobs"]
        
        self.products_col.create_index("url", unique=True, background=True)
        self.prices_col.create_index([("url", pymongo.ASCENDING), ("date", pymongo.ASCENDING)], unique=True, background=True)
        
        self.start_time = datetime.now(timezone.utc)
        self.job_id = self.start_time.strftime("%Y%m%d_%H%M%S")
        self.islenen_toplam = 0
        
        # Başlangıç Kaydı (Boş İstatistiklerle)
        self.jobs_col.insert_one({
            "job_id": self.job_id,
            "status": "Running",
            "start_time": self.start_time,
            "last_ping": datetime.now(timezone.utc),
            "stats": self.stats,
            "total_processed": 0,
            "current_page": 1
        })

    def process_item(self, item, spider):
        adapter = ItemAdapter(item)
        url = adapter.get("url", "")

        # 1. FİYAT KONTROLÜ
        price_raw = adapter.get("price", "-1")
        if isinstance(price_raw, list):
            price_raw = next((p for p in price_raw if str(p).strip() not in ["-1", "", "None"]), "-1")

        price_str = str(price_raw).strip()
        if price_str in ["-1", "", "Yok", "None"]:
            self._drop("Fiyat Yok", url, spider, reason="drop_fiyatsiz")

        try:
            temiz_fiyat = self._fiyat_temizle(price_str)
            adapter["price"] = temiz_fiyat
        except ValueError:
            self._drop("Fiyat Hatası", url, spider, reason="drop_hata")

        # 2. DİĞER TEMİZLİKLER
        attributes = adapter.get("attributes", {})
        if not attributes or attributes == {"Bilgi": "-1"}:
            adapter["attributes"] = {}

        adapter["evaluation"] = self._sayi_temizle(adapter.get("evaluation", "-1"), float_mi=True, varsayilan=-1)
        adapter["evaluation_len"] = self._sayi_temizle(adapter.get("evaluation_len", "-1"), float_mi=False, varsayilan=-1)

        # 3. VERİTABANI İŞLEMLERİ (UPSERT)
        
        # Sadece last_seen (son görülme) tarihini kesin olarak ekliyoruz
        product_data = {"last_seen": datetime.now(timezone.utc)}
        
        # Eğer örümcek bu verileri çekmişse (doluysa) güncelle, boşsa eski verilere dokunma!
        for key in ["title", "category", "attributes", "images", "explanation"]:
            val = adapter.get(key)
            if val:  # Veri boş (None) değilse ekle
                product_data[key] = val
        
        # Products Güncelleme
        prod_res = self.products_col.update_one({"url": url}, {"$set": product_data}, upsert=True)

        # Price History Güncelleme
        today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d") 
        price_data = {
            "price": temiz_fiyat,
            "evaluation": adapter.get("evaluation"),
            "evaluation_len": adapter.get("evaluation_len")
        }
        price_res = self.prices_col.update_one(
            {"url": url, "date": today_str},
            {"$set": price_data},
            upsert=True
        )

        # 4. DETAYLI SAYAÇ GÜNCELLEME (Net Ayrım)
        if prod_res.upserted_id:
            # Ana tabloya yeni eklendiyse, yepyeni bir üründür.
            self.stats["yeni_urun"] += 1
        elif price_res.upserted_id:
            # Ürün eski ama fiyat tablosuna BUGÜNÜN tarihiyle ilk defa girildi.
            self.stats["yeni_gun_kaydi"] += 1
        elif price_res.modified_count > 0:
            # Ürün eski, bugünün kaydı da zaten vardı ama Puan/Yorum/Fiyat bir şey değişti!
            self.stats["gun_ici_degisim"] += 1

        # 5. CANLI RAPOR (HEARTBEAT) - Her 10 üründe bir
        self.islenen_toplam += 1
        if self.islenen_toplam % 10 == 0:
            self.jobs_col.update_one(
                {"job_id": self.job_id},
                {"$set": {
                    "stats": self.stats,
                    "last_ping": datetime.now(timezone.utc),
                    "total_processed": self.islenen_toplam,
                    "current_page": getattr(spider, 'current_page', 1)
                }}
            )

        return item

    def _drop(self, sebep: str, url: str, spider, reason="drop_hata"):
        self.stats[reason] += 1
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
        self.jobs_col.update_one(
            {"job_id": self.job_id},
            {"$set": {
                "status": "Completed",
                "end_time": end_time,
                "duration_seconds": round((end_time - self.start_time).total_seconds(), 2),
                "stats": self.stats,
                "total_processed": self.islenen_toplam
            }}
        )
        self.client.close()