import pymongo
import logging
from itemadapter import ItemAdapter
from scrapy.exceptions import DropItem
import re
from datetime import datetime, timezone

# pymongo'nun kendi DEBUG gürültüsünü kapat
logging.getLogger("pymongo").setLevel(logging.WARNING)

class TrendyolBotPipeline:

    def __init__(self):
        self.mongo_uri = "mongodb://localhost:27017/"
        self.mongo_db  = "neuranovav_db"

        self.stats = {
            "yeni_urun":       0,
            "yeni_gun_kaydi":  0,
            "gun_ici_degisim": 0,
            "drop_fiyatsiz":   0,
            "drop_hata":       0
        }

        # FAZ 4 - Madde 15: saat basi hiz takibi
        self.saat_basi_sayac  = 0
        self.mevcut_saat      = None
        self.hourly_snapshots = []

        # FAZ 4 - Madde 17: kategori sayaci
        self.kategori_sayac = {}

    def open_spider(self, spider):
        self.client = pymongo.MongoClient(self.mongo_uri)
        self.db     = self.client[self.mongo_db]

        self.products_col = self.db["products"]
        self.prices_col   = self.db["price_history"]
        self.jobs_col     = self.db["jobs"]

        self.products_col.create_index("url", unique=True, background=True)
        self.db["proxy_performance"].create_index("proxy", unique=True, background=True)
        self.db["failed_urls"].create_index("url", unique=True, background=True)

        self.prices_col.create_index(
            [("url", pymongo.ASCENDING), ("date", pymongo.ASCENDING)],
            unique=True, background=True
        )

        # FIX-1: jobs koleksiyonu için job_id unique index
        self.jobs_col.create_index("job_id", unique=True, background=True)
        # FIX-2: proxy_logs şişmesini önlemek için ts index
        self.db["proxy_logs"].create_index("ts", background=True)
        # FIX-3: bot_commands koleksiyonu için bot_id index
        self.db["bot_commands"].create_index("bot_id", unique=True, background=True)
        
        self.start_time     = datetime.now(timezone.utc)
        self.islenen_toplam = 0
        self.mevcut_saat    = self.start_time.hour

        # FAZ 3: JOBDIR varsa job_id sabit kalir
        jobdir = spider.settings.get('JOBDIR')
        if jobdir:
            self.job_id = jobdir.replace("/", "_").replace("\\", "_")
        else:
            self.job_id = self.start_time.strftime("%Y%m%d_%H%M%S")

        result = self.jobs_col.update_one(
            {"job_id": self.job_id},
            {
                "$setOnInsert": {
                    "start_time":      self.start_time,
                    "stats":           self.stats,
                    "total_processed": 0,
                    "current_page":    1,
                    "hourly_stats":    [],
                    "kategori_stats":  {},
                    "ozet":            {}
                },
                "$set": {
                    "status":    "Running",   # ← Her resume'de Running yaz
                    "last_ping": datetime.now(timezone.utc)
                }
            },
            upsert=True
        )

        if not result.upserted_id:
            mevcut = self.jobs_col.find_one({"job_id": self.job_id})
            if mevcut:
                self.islenen_toplam = mevcut.get("total_processed", 0)
                self.stats = mevcut.get("stats", self.stats)
                spider.logger.info(
                    f"[Pipeline] Resume | job_id={self.job_id} | "
                    f"onceki_toplam={self.islenen_toplam}"
                )
        else:
            spider.logger.info(f"[Pipeline] Yeni oturum | job_id={self.job_id}")
            
        # FAZ 5: Bot başladı maili
        self._send_status_mail(
            subject="🟢 NeuraNovaV Bot Başladı",
            baslik="Bot Çalışmaya Başladı",
            renk="#2e7d32",
            mesaj=f"Job ID: <b>{self.job_id}</b><br>Başlangıç: {self.start_time.strftime('%d/%m/%Y %H:%M')} UTC"
        )

    def process_item(self, item, spider):
        adapter    = ItemAdapter(item)
        url        = adapter.get("url", "")
        proxy_used = adapter.get("proxy_used", "Direct")

        # --- 1. FIYAT KONTROLU ---
        price_raw = adapter.get("price", "-1")
        if isinstance(price_raw, list):
            price_raw = next(
                (p for p in price_raw if str(p).strip() not in ["-1", "", "None"]), "-1"
            )
        price_str = str(price_raw).strip()
        if price_str in ["-1", "", "Yok", "None"]:
            self._record_url_error(url, proxy_used, "price_missing")
            self._drop("Fiyat Yok", url, spider, reason="drop_fiyatsiz", proxy=proxy_used)

        try:
            temiz_fiyat      = self._fiyat_temizle(price_str)
            adapter["price"] = temiz_fiyat
        except ValueError:
            self._drop("Fiyat Hatasi", url, spider, reason="drop_hata", proxy=proxy_used)

        # --- 2. DIGER TEMIZLIKLER ---
        attributes = adapter.get("attributes", {})
        if not attributes or attributes == {"Bilgi": "-1"}:
            adapter["attributes"] = {}
        adapter["evaluation"]     = self._sayi_temizle(adapter.get("evaluation",     "-1"), float_mi=True,  varsayilan=-1)
        adapter["evaluation_len"] = self._sayi_temizle(adapter.get("evaluation_len", "-1"), float_mi=False, varsayilan=-1)

        # --- 3. VERITABANI ISLEMLERI ---
        product_data = {
            "last_seen": datetime.now(timezone.utc),
            "scrape_method": "scrapy"  # imzayı atıyoruz
        }
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

        # --- 4. SAYAC ---
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

        # FAZ 5: Madde 20 — başarılı ürün için proxy performans kaydı
        self._update_proxy_perf(proxy_used, is_ban=False)

        return item

    def _drop(self, sebep, url, spider, reason="drop_hata", proxy=None):
        self.stats[reason] += 1
        # FAZ 5: Madde 20 — drop anında proxy ban kaydı
        if proxy and proxy != "Direct":
            self._update_proxy_perf(proxy, is_ban=True)
        raise DropItem(f"DROP ({sebep}): {url}")

    @staticmethod
    def _fiyat_temizle(price_str):
        s = re.sub(r"[^\d.,]", "", price_str)
        if not s: raise ValueError(f"Fiyat bos: {price_str}")
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
    def _sayi_temizle(raw, float_mi, varsayilan):
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

    def _update_proxy_perf(self, proxy: str, is_ban: bool):
        """FAZ 5: Madde 20 — Proxy başarı/ban sayacı."""
        if not proxy or proxy == "Direct":
            return
        simdi = datetime.now(timezone.utc)
        try:
            if is_ban:
                self.db["proxy_performance"].update_one(
                    {"proxy": proxy},
                    {
                        "$inc":         {"ban_count": 1},
                        "$set":         {"last_banned": simdi},
                        "$setOnInsert": {"first_seen": simdi, "success_count": 0, "retired": False}
                    },
                    upsert=True
                )
            else:
                self.db["proxy_performance"].update_one(
                    {"proxy": proxy},
                    {
                        "$inc":         {"success_count": 1},
                        "$set":         {"last_seen": simdi},
                        "$setOnInsert": {"first_seen": simdi, "ban_count": 0, "retired": False}
                    },
                    upsert=True
                )
        except Exception as e:
            pass  # proxy log hatası scraping'i durdurmamalı

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
        
        # FAZ 5: Bot bitti maili
        self._send_status_mail(
            subject="🔴 NeuraNovaV Bot Tamamlandı",
            baslik="Scraping Tamamlandı",
            renk="#1565c0",
            mesaj=f"Job ID: <b>{self.job_id}</b><br>"
                f"Toplam: <b>{self.islenen_toplam}</b> ürün<br>"
                f"Yeni: <b>{self.stats['yeni_urun']}</b> | "
                f"Güncelleme: <b>{self.stats['yeni_gun_kaydi']}</b> | "
                f"Drop: <b>{self.stats['drop_fiyatsiz'] + self.stats['drop_hata']}</b><br>"
                f"Süre: <b>{round(duration/60, 1)}</b> dakika"
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
        
    def _send_status_mail(self, subject, baslik, renk, mesaj):
        """Bot durum bildirimi maili gönderir."""
        try:
            import smtplib, os, json
            from email.mime.multipart import MIMEMultipart
            from email.mime.text import MIMEText
            from dotenv import load_dotenv
            load_dotenv()
            sender    = os.getenv("MAIL_SENDER", "")
            password  = os.getenv("MAIL_APP_PASS", "")
            recipient = None
            if os.path.exists("saved_mails.json"):
                with open("saved_mails.json") as f:
                    mails = json.load(f)
                    recipient = mails[0] if mails else None
            if not sender or not password or not recipient:
                return
            html = f"""
            <html><body style="font-family:Arial,sans-serif;padding:20px">
            <div style="max-width:500px;margin:auto;background:white;border-radius:12px;padding:24px;box-shadow:0 2px 8px #ccc">
                <h2 style="color:{renk}">{baslik}</h2>
                <p>{mesaj}</p>
                <p style="color:#888;font-size:13px">📊 Dashboard: <a href="http://localhost:8501" style="color:#6a0dad">http://localhost:8501</a></p>
                <p style="color:#aaa;font-size:12px">NeuraNovaV Otomatik Bildirim Sistemi</p>
            </div></body></html>"""
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"]    = f"NeuraNovaV Bot <{sender}>"
            msg["To"]      = recipient
            msg.attach(MIMEText(html, "html"))
            with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
                server.login(sender, password)
                server.sendmail(sender, recipient, msg.as_string())
            logging.getLogger("pipeline").info(f"[Pipeline] Durum maili gönderildi | {subject}")
        except Exception as e:
            pass  # mail hatası scraping'i durdurmamalı
        
    def _record_url_error(self, url: str, proxy: str, error_type: str):
        """FAZ 6: Fiyatsız/hatalı URL'leri failed_urls koleksiyonuna yazar."""
        simdi = datetime.now(timezone.utc)
        try:
            self.db["failed_urls"].update_one(
                {"url": url},
                {
                    "$set": {
                        "hata_tipi":  error_type,
                        "son_deneme": simdi,
                        "cozuldu":    False,
                    },
                    "$inc":      {"deneme_sayisi": 1},
                    "$addToSet": {"proxy_listesi": proxy},
                    "$push": {
                        "attempts": {
                            "$each": [{
                                "ts":         simdi,
                                "proxy":      proxy,
                                "error_type": error_type,
                            }],
                            "$slice": -20  # FIX: Sadece son 20 denemeyi tut, array şişmez
                        }
                    },
                    "$setOnInsert": {"ilk_hata": simdi}
                },
                upsert=True
            )
        except Exception as e:
            pass  # hata kaydı scraping'i durdurmamalı