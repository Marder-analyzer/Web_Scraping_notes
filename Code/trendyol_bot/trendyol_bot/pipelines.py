import pymongo
import logging
from itemadapter import ItemAdapter
from scrapy.exceptions import DropItem
import re
from datetime import datetime, timezone

# pymongo'nun kendi DEBUG gürültüsünü kapat (madde 9)
logging.getLogger("pymongo").setLevel(logging.WARNING)

class TrendyolBotPipeline:

    def __init__(self):
        self.mongo_uri = "mongodb://localhost:27017/"
        self.mongo_db = "neuranovav_db"
        
        self.stats = {
            "yeni_urun": 0,
            "yeni_gun_kaydi": 0,
            "gun_ici_degisim": 0,
            "drop_fiyatsiz": 0,
            "drop_hata": 0
        }

    def open_spider(self, spider):
        self.client = pymongo.MongoClient(self.mongo_uri)
        self.db = self.client[self.mongo_db]
        
        self.products_col = self.db["products"]
        self.prices_col   = self.db["price_history"]
        self.jobs_col     = self.db["jobs"]
        
        self.products_col.create_index("url", unique=True, background=True)
        self.prices_col.create_index(
            [("url", pymongo.ASCENDING), ("date", pymongo.ASCENDING)],
            unique=True, background=True
        )
        
        self.start_time    = datetime.now(timezone.utc)
        self.job_id        = self.start_time.strftime("%Y%m%d_%H%M%S")
        self.islenen_toplam = 0
        
        self.jobs_col.insert_one({
            "job_id":          self.job_id,
            "status":          "Running",
            "start_time":      self.start_time,
            "last_ping":       datetime.now(timezone.utc),
            "stats":           self.stats,
            "total_processed": 0,
            "current_page":    1
        })

        # Madde 10: pipeline başlangıç logu - sadece 1 satır
        spider.logger.info(f"[Pipeline] Basladi | job_id={self.job_id}")

    def process_item(self, item, spider):
        adapter  = ItemAdapter(item)
        url      = adapter.get("url", "")

        # --- 1. FİYAT KONTROLÜ ---
        price_raw = adapter.get("price", "-1")
        if isinstance(price_raw, list):
            price_raw = next(
                (p for p in price_raw if str(p).strip() not in ["-1", "", "None"]), "-1"
            )

        price_str = str(price_raw).strip()
        if price_str in ["-1", "", "Yok", "None"]:
            try:
                with open("fiyatsiz_cope_gidenler.txt", "a", encoding="utf-8") as f:
                    f.write(url + "\n")
            except Exception as e:
                spider.logger.error(f"[Pipeline] Fiyatsiz link kaydedilemedi: {e}")
            self._drop("Fiyat Yok", url, spider, reason="drop_fiyatsiz")

        try:
            temiz_fiyat    = self._fiyat_temizle(price_str)
            adapter["price"] = temiz_fiyat
        except ValueError:
            self._drop("Fiyat Hatası", url, spider, reason="drop_hata")

        # --- 2. DİĞER TEMİZLİKLER ---
        attributes = adapter.get("attributes", {})
        if not attributes or attributes == {"Bilgi": "-1"}:
            adapter["attributes"] = {}

        adapter["evaluation"]     = self._sayi_temizle(adapter.get("evaluation", "-1"),     float_mi=True,  varsayilan=-1)
        adapter["evaluation_len"] = self._sayi_temizle(adapter.get("evaluation_len", "-1"), float_mi=False, varsayilan=-1)

        # --- 3. VERİTABANI İŞLEMLERİ ---
        product_data = {"last_seen": datetime.now(timezone.utc)}
        for key in ["title", "category", "attributes", "images", "explanation"]:
            val = adapter.get(key)
            if val:
                product_data[key] = val

        prod_res  = self.products_col.update_one({"url": url}, {"$set": product_data}, upsert=True)
        today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        price_data = {
            "price":          temiz_fiyat,
            "evaluation":     adapter.get("evaluation"),
            "evaluation_len": adapter.get("evaluation_len")
        }
        price_res = self.prices_col.update_one(
            {"url": url, "date": today_str},
            {"$set": price_data},
            upsert=True
        )

        # --- 4. SAYAÇ ---
        if prod_res.upserted_id:
            self.stats["yeni_urun"] += 1
        elif price_res.upserted_id:
            self.stats["yeni_gun_kaydi"] += 1
        elif price_res.modified_count > 0:
            self.stats["gun_ici_degisim"] += 1

        # --- 5. HEARTBEAT — Her 10 üründe bir (sadece DB'ye yaz, konsola değil) ---
        self.islenen_toplam += 1
        if self.islenen_toplam % 10 == 0:
            self.jobs_col.update_one(
                {"job_id": self.job_id},
                {"$set": {
                    "stats":           self.stats,
                    "last_ping":       datetime.now(timezone.utc),
                    "total_processed": self.islenen_toplam,
                    "current_page":    getattr(spider, "current_page", 1)
                }}
            )

        return item

    def _drop(self, sebep: str, url: str, spider, reason="drop_hata"):
        self.stats[reason] += 1
        raise DropItem(f"DROP ({sebep}): {url}")

    @staticmethod
    def _fiyat_temizle(price_str: str) -> float:
        s = re.sub(r"[^\d.,]", "", price_str)
        if not s: raise ValueError(f"Fiyat boş: {price_str}")
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
                return round(float(s_clean), 1) if s_clean else varsayilan
            else:
                s_clean = re.sub(r"[^\d]", "", s)
                return int(s_clean) if s_clean else varsayilan
        except Exception:
            return varsayilan

    def close_spider(self, spider):
        end_time = datetime.now(timezone.utc)
        duration = round((end_time - self.start_time).total_seconds(), 2)

        self.jobs_col.update_one(
            {"job_id": self.job_id},
            {"$set": {
                "status":           "Completed",
                "end_time":         end_time,
                "duration_seconds": duration,
                "stats":            self.stats,
                "total_processed":  self.islenen_toplam
            }}
        )
        self.client.close()

        # Madde 10: Session sonu özet — tek blok, sadece WARNING değil INFO seviyesinde
        spider.logger.info(
            f"[Pipeline] Bitti | sure={duration}s | "
            f"toplam={self.islenen_toplam} | "
            f"yeni={self.stats['yeni_urun']} | "
            f"guncelleme={self.stats['yeni_gun_kaydi']} | "
            f"degisim={self.stats['gun_ici_degisim']} | "
            f"drop_fiyatsiz={self.stats['drop_fiyatsiz']} | "
            f"drop_hata={self.stats['drop_hata']}"
        )