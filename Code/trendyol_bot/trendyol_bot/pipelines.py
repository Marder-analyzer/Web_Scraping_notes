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
        # FAZ 4 - Madde 15: saat basi hiz takibi
        self.saat_basi_sayac  = 0
        self.mevcut_saat      = None
        self.hourly_snapshots = []

        # FAZ 4 - Madde 17: kategori sayaci
        self.kategori_sayac = {}

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
        
        self.start_time     = datetime.now(timezone.utc)
        self.islenen_toplam = 0

        # FAZ 3: JOBDIR varsa job_id sabit kalir
        jobdir = spider.settings.get('JOBDIR')
        if jobdir:
            self.job_id = jobdir.replace("/", "_").replace("\\", "_")
        else:
            self.job_id = self.start_time.strftime("%Y%m%d_%H%M%S")

        # $setOnInsert: kayıt zaten varsa hiçbir şey yazmaz, yoksa oluşturur
        result = self.jobs_col.update_one(
            {"job_id": self.job_id},
            {
                "$setOnInsert": {
                    "status":          "Running",
                    "start_time":      self.start_time,
                    "stats":           self.stats,
                    "total_processed": 0,
                    "current_page":    1
                },
                "$set": {
                    "last_ping": datetime.now(timezone.utc)
                }
            },
            upsert=True
        )

        if result.upserted_id:
            spider.logger.info(f"[Pipeline] Yeni oturum | job_id={self.job_id}")
        else:
            spider.logger.info(f"[Pipeline] Resume | job_id={self.job_id} | kaldigi yerden devam")

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
            
        # --- FAZ 4: Madde 17 - Kategori sayaci ---
        kategori = adapter.get("category", "")
        if kategori:
            ana_kat = kategori.split(" > ")[-1].strip() if " > " in kategori else kategori
            self.kategori_sayac[ana_kat] = self.kategori_sayac.get(ana_kat, 0) + 1

        # --- FAZ 4: Madde 15 - Saat basi snapshot ---
        simdi = datetime.now(timezone.utc)
        if simdi.hour != self.mevcut_saat:
            hiz = round(self.saat_basi_sayac / 60, 1)
            snapshot = {
                "saat":        f"{self.mevcut_saat:02d}:00",
                "islenen":     self.saat_basi_sayac,
                "hiz_urun_dk": hiz,
                "zaman":       simdi
            }
            self.hourly_snapshots.append(snapshot)
            self.jobs_col.update_one(
                {"job_id": self.job_id},
                {"$push": {"hourly_stats": snapshot}}
            )
            spider.logger.info(
                f"[Pipeline] Saat ozeti | {snapshot['saat']} | "
                f"{self.saat_basi_sayac} urun | hiz={hiz} urun/dk"
            )
            self.mevcut_saat     = simdi.hour
            self.saat_basi_sayac = 0

        self.saat_basi_sayac += 1

        # --- 5. HEARTBEAT - Her 10 urunde bir ---
        self.islenen_toplam += 1
        if self.islenen_toplam % 10 == 0:
            top5 = sorted(self.kategori_sayac.items(), key=lambda x: x[1], reverse=True)[:5]
            self.jobs_col.update_one(
                {"job_id": self.job_id},
                {"$set": {
                    "stats":           self.stats,
                    "last_ping":       datetime.now(timezone.utc),
                    "total_processed": self.islenen_toplam,
                    "current_page":    getattr(spider, "current_page", 1),
                    "kategori_stats":  self.kategori_sayac,
                    "top5_kategori":   dict(top5)
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

        # Son saatin snapshot'i
        if self.saat_basi_sayac > 0:
            hiz = round(self.saat_basi_sayac / max(duration / 60, 1), 1)
            snapshot = {
                "saat":        f"{self.mevcut_saat:02d}:00 (son)",
                "islenen":     self.saat_basi_sayac,
                "hiz_urun_dk": hiz,
                "zaman":       end_time
            }
            self.hourly_snapshots.append(snapshot)
            self.jobs_col.update_one(
                {"job_id": self.job_id},
                {"$push": {"hourly_stats": snapshot}}
            )

        # Madde 16: Genel ortalama
        if self.hourly_snapshots:
            ortalama_hiz  = round(sum(s["hiz_urun_dk"] for s in self.hourly_snapshots) / len(self.hourly_snapshots), 1)
            en_hizli      = max(self.hourly_snapshots, key=lambda s: s["hiz_urun_dk"])
        else:
            ortalama_hiz  = round(self.islenen_toplam / max(duration / 60, 1), 1)
            en_hizli      = {"saat": "-", "hiz_urun_dk": ortalama_hiz}

        # Madde 17: Kategori raporu
        en_cok = sorted(self.kategori_sayac.items(), key=lambda x: x[1], reverse=True)

        ozet = {
            "ortalama_hiz_urun_dk": ortalama_hiz,
            "en_hizli_saat":        en_hizli["saat"],
            "en_hizli_saat_hiz":    en_hizli["hiz_urun_dk"],
            "toplam_kategori":      len(self.kategori_sayac),
            "en_cok_urun_kategori": en_cok[0][0] if en_cok else "-",
            "en_cok_urun_adet":     en_cok[0][1] if en_cok else 0,
        }

        self.jobs_col.update_one(
            {"job_id": self.job_id},
            {"$set": {
                "status":           "Completed",
                "end_time":         end_time,
                "duration_seconds": duration,
                "stats":            self.stats,
                "total_processed":  self.islenen_toplam,
                "kategori_stats":   self.kategori_sayac,
                "top5_kategori":    dict(en_cok[:5]),
                "ozet":             ozet
            }}
        )
        self.client.close()

        spider.logger.info(
            f"[Pipeline] Bitti | sure={duration}s | "
            f"toplam={self.islenen_toplam} | "
            f"yeni={self.stats['yeni_urun']} | "
            f"guncelleme={self.stats['yeni_gun_kaydi']} | "
            f"degisim={self.stats['gun_ici_degisim']} | "
            f"drop_fiyatsiz={self.stats['drop_fiyatsiz']} | "
            f"drop_hata={self.stats['drop_hata']} | "
            f"ort_hiz={ortalama_hiz} urun/dk | "
            f"kategori={len(self.kategori_sayac)}"
        )