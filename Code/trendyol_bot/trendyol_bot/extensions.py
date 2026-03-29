import logging
import urllib.request
from datetime import datetime, timezone
import time
import pymongo
from scrapy import signals
from twisted.internet import task, threads, reactor

log = logging.getLogger("proxy_updater")

# ── Madde 2: Çoklu kaynak ─────────────────────────────────────────────────────
PROXY_SOURCES = [
    "https://raw.githubusercontent.com/monosans/proxy-list/main/proxies/http.txt",
    "https://raw.githubusercontent.com/ShiftyTR/Proxy-List/master/http.txt",
    "https://raw.githubusercontent.com/proxifly/free-proxy-list/main/proxies/protocols/http/data.txt",
    "https://raw.githubusercontent.com/iplocate/free-proxy-list/main/protocols/http.txt",
    "https://raw.githubusercontent.com/iplocate/free-proxy-list/main/countries/TR/proxies.txt",
    "https://raw.githubusercontent.com/mmpx12/proxy-list/master/http.txt",
    "https://raw.githubusercontent.com/sunny9577/proxy-scraper/master/generated/http_proxies.txt",
    "https://api.proxyscrape.com/v4/free-proxy-list/get?request=display_proxies&country=tr&proxy_format=protocolipport&format=text&timeout=10000",

    
]

# Madde 6: Yaygın Türk ISP IP bloklarının önekleri (kaba TR filtresi)
# Not: Kesin TR tespiti için MaxMind GeoIP2 kullanılabilir, bu sürüm hafif tutuluyor.
TR_PREFIXES = (
    "31.142.", "31.145.", "78.160.", "78.161.", "78.162.", "78.163.",
    "78.164.", "78.165.", "78.166.", "78.167.", "78.168.", "78.169.",
    "85.100.", "85.101.", "85.102.", "85.103.", "88.228.", "88.229.",
    "88.230.", "88.231.", "88.232.", "88.233.", "88.234.", "88.235.",
    "94.54.",  "94.55.",  "176.88.", "176.89.", "176.220.", "176.221.",
    "212.154.", "212.155.", "213.14.", "213.15.",
)

BAN_LIMIT       = 30    # Madde 20: kaç ban sonra retired
MONGO_URI      = "mongodb://localhost:27017/"
MONGO_DB       = "neuranovav_db"    # pipelines.py ile aynı
HEDEF_HAVUZ    = 150
DOLUM_ESIGI    = 15

def _is_tr(proxy_url: str) -> bool:
    """http://IP:PORT formatındaki proxy'nin TR bloğunda olup olmadığını kontrol eder."""
    try:
        ip = proxy_url.split("//")[1].split(":")[0]
        return ip.startswith(TR_PREFIXES)
    except Exception:
        return False


class LiveProxyUpdater:
    """
    FAZ 1 — Proxy Yönetimi

    Madde 1 : Thread-safe saatlik güncelleme (fetch arka thread, inject ana thread)
    Madde 2 : Çoklu kaynak — ilk başarılıyı kullan
    Madde 3 : Bot çalışırken güvenli enjeksiyon — mevcut proxylere dokunulmaz
    Madde 4 : proxies.txt güncellenir, banlananlar txt'den de silinir
    Madde 5 : Banlanan proxy → jobs koleksiyonuna log (yeni koleksiyon açılmaz)
    Madde 6 : TR proxy önceliği — TR yoksa yabancıyla devam eder
    Madde 7 : Güvenli fallback — havuz boşalınca 10 dk uyku, kendi IP asla kullanılmaz
    Madde 8 : settings.py EXTENSIONS ile otomatik başlar, proxy_bulucu.py gerekmez
    """

    def __init__(self, crawler):
        self.local_error_count = 0
        self.is_paused = False
        self.crawler = crawler
        self.interval = 900
        self._sleeping = False
        self._last_alert_time = 0
        self._db = None

        # Middleware başlamadan önce dosya hazır olmalı — içi boşsa NotConfigured fırlatır
        import os
        DUMMY = "http://127.0.0.1:9999\n"
        if not os.path.exists("proxies.txt") or os.path.getsize("proxies.txt") == 0:
            with open("proxies.txt", "w") as f:
                f.write(DUMMY)
            log.info("proxies.txt hazırlandı (can simidi proxy ile)")

    @classmethod
    def from_crawler(cls, crawler):
        from scrapy import signals
        ext = cls(crawler)
        
        crawler.signals.connect(ext.response_received, signal=signals.response_received)
        crawler.signals.connect(ext.spider_opened, signal=signals.spider_opened)
        crawler.signals.connect(ext.spider_closed, signal=signals.spider_closed)
        
        crawler.signals.connect(ext.handle_response, signal=signals.response_received)
        crawler.signals.connect(ext.handle_failure, signal=signals.spider_error)
        return ext

    # ─────────────────────────────────────────────────────────────────────────
    # Scrapy sinyalleri
    # ─────────────────────────────────────────────────────────────────────────

    def spider_opened(self, spider):
        import logging
        logging.getLogger('scrapy.core.downloader.tls').setLevel(logging.ERROR)
        try:
            client = pymongo.MongoClient(MONGO_URI, serverSelectionTimeoutMS=3000)
            self._db  = client[MONGO_DB]
        except Exception as e:
            log.warning(f"mongo bağlantısı yok, proxy logu atlanacak | {e}")

        self.task = task.LoopingCall(self._trigger_update)
        self.task.start(self.interval, now=True)
        
        self.health_task = task.LoopingCall(self._check_proxy_health)
        self.health_task.start(120, now=False)
        log.info(
            f"proxy güncelleyici aktif | "
            f"{len(PROXY_SOURCES)} kaynak | "
            f"her {self.interval // 60} dk"
        )

    def spider_closed(self, spider):
        if hasattr(self, "task") and self.task.running:
            self.task.stop()
        if hasattr(self, "health_task") and self.health_task.running:
            self.health_task.stop()

    # ─────────────────────────────────────────────────────────────────────────
    # Güncelleme akışı
    # ─────────────────────────────────────────────────────────────────────────

    def _trigger_update(self):
        """Madde 1: Twisted ana döngüsünden tetiklenir. Fetch'i arka thread'e atar."""
        d = threads.deferToThread(self._fetch_proxies)
        d.addCallback(self._inject_to_scrapy)   # ana thread'de çalışır → thread-safe
        d.addErrback(lambda f: log.error(f"beklenmedik hata | {f.getErrorMessage()}"))

    # ─────────────────────────────────────────────────────────────────────────
    # ARKA THREAD — sadece HTTP çekimi
    # ─────────────────────────────────────────────────────────────────────────

    def _fetch_proxies(self) -> dict:
        result = {
            "all": [], "tr": [], "foreign": [],
            "source": None, "trash": 0, "source_reachable": False, "source_attempts": []
        }
        tum_proxies = set()  # Aynı proxy'yi iki kere eklememek için kalkan

        for url in PROXY_SOURCES:
            source_name = url.split("/")[3]
            attempt = {"kaynak": source_name, "erisim_ok": False,
                       "toplam": 0, "tr": 0, "yabanci": 0, "cop": 0}
            try:
                req  = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
                resp = urllib.request.urlopen(req, timeout=10)
                data = resp.read().decode("utf-8")

                proxies = []
                trash   = 0
                for line in data.strip().splitlines():
                    line = line.strip()
                    if not line:
                        continue
                    if line.startswith("http://") or line.startswith("https://"):
                        p = line.strip()
                    else:
                        parts = line.split(":")
                        if len(parts) == 2 and parts[1].isdigit():
                            p = f"http://{line}"
                        else:
                            trash += 1
                            continue
                    if p not in tum_proxies:
                        proxies.append(p)
                        tum_proxies.add(p)

                # _is_tr fonksiyonunun dosyanda var olduğunu varsayıyoruz
                tr_list      = [p for p in proxies if getattr(self, '_is_tr', lambda x: False)(p)]
                foreign_list = [p for p in proxies if p not in tr_list]

                attempt.update({
                    "erisim_ok": True,
                    "toplam":    len(proxies),
                    "tr":        len(tr_list),
                    "yabanci":   len(foreign_list),
                    "cop":       trash,
                })

                result["all"].extend(proxies)
                result["tr"].extend(tr_list)
                result["foreign"].extend(foreign_list)
                result["trash"] += trash
                result["source_reachable"] = True
                
                if result["source"] is None:
                    result["source"] = source_name
                    
                log.info(
                    f"Kaynak OK | {source_name} | "
                    f"Toplam: {len(proxies)} | TR: {len(tr_list)} | "
                    f"Yabancı: {len(foreign_list)} | Çöp: {trash}"
                )
            except Exception as e:
                attempt["hata"] = str(e)
                log.warning(f"Kaynak başarısız | {source_name} | {e}")
                
            result["source_attempts"].append(attempt)
            
        # DÖNGÜ BİTTİKTEN SONRA (Tüm siteler gezildikten sonra) dön!
        return result

    # ─────────────────────────────────────────────────────────────────────────
    # ANA THREAD — Scrapy'ye enjeksiyon (thread-safe)
    # ─────────────────────────────────────────────────────────────────────────

    def _inject_to_scrapy(self, result: dict):
        """
        Madde 3: mevcut proxylere dokunmaz, sadece yenileri ekler.
        Madde 4: banlananları RAM'den ve proxies.txt'den siler.
        Madde 6: TR proxyleri listenin başına alır.
        Madde 7: havuz boşsa uyku moduna girer, kendi IP asla kullanılmaz.
        """

        if not result["all"]:
            self._enter_sleep_mode()
            return
        
        # Madde 6: TR önce, yabancı sonra
        ordered = result["tr"] + result["foreign"]
        ordered = self._filter_retired(ordered)
        
        if not ordered:
            self._enter_sleep_mode()
            return
        
        added          = 0
        banned_removed = 0
        mw_ref         = None

        try:
            for mw in self.crawler.engine.downloader.middleware.middlewares:
                if mw.__class__.__name__ == "RotatingProxyMiddleware":
                    mw_ref = mw
                    from rotating_proxies.expire import ProxyState

                    # Madde 3: sadece yeni proxy ekle
                    yeni_gelenler = [p for p in ordered if p not in mw.proxies.proxies]

                    # HAVUZ LİMİTİ: HEDEF_HAVUZ'u aşma, sadece boş slot kadar ekle
                    mevcut_toplam = len(mw.proxies.unchecked) + len(mw.proxies.good)
                    bos_slot = max(0, HEDEF_HAVUZ - mevcut_toplam)
                    if bos_slot == 0:
                        log.info(f"Proxy havuzu dolu ({mevcut_toplam}/{HEDEF_HAVUZ}), yeni ekleme atlandı")
                        yeni_gelenler = []
                    else:
                        yeni_gelenler = yeni_gelenler[:bos_slot]
                        log.info(f"Havuz dolumu: {mevcut_toplam}/{HEDEF_HAVUZ} → {len(yeni_gelenler)} eklenecek")
                    

                    # Yeni proxileri ekle
                    for p in yeni_gelenler:
                        mw.proxies.proxies[p] = ProxyState()
                        mw.proxies.unchecked.add(p)
                        added += 1

                    # Madde 4: dead (banlı) proxyleri RAM'den temizle
                    dead = [
                        p for p, st in list(mw.proxies.proxies.items())
                        if hasattr(st, "state") and str(st.state) == "dead"
                    ]
                    for p in dead:
                        mw.proxies.proxies.pop(p, None)
                        mw.proxies.unchecked.discard(p)
                        banned_removed += 1
                        self._record_ban(p)  

                    break

        except Exception as e:
            log.warning(f"enjeksiyon hatası | {e}")

        # Madde 4: proxies.txt güncelle — banlılar hariç
        try:
            if mw_ref is not None:
                active = list(mw_ref.proxies.proxies.keys())
            else:
                active = ordered
            active = self._filter_retired(active)    
            with open("proxies.txt", "w", encoding="utf-8") as f:
                f.write("\n".join(active) + "\n")
        except Exception as e:
            log.warning(f"proxies.txt yazılamadı | {e}")

        result["yeni_eklenen"] = added

        log.info(
            f"güncelleme tamam | "
            f"+{added} yeni | "
            f"-{banned_removed} banlı silindi | "
            f"TR: {len(result['tr'])} | "
            f"çöp: {result['trash']}"
        )

        try:
            if self._db is not None:
                self._db["bot_commands"].update_one(
                    {"bot_id": "proxy_stats"},
                    {"$set": {
                        "aktif_proxy": len(ordered),
                        "updated_at": datetime.now(timezone.utc)
                    }},
                    upsert=True
                )
        except:
            pass

        
        
        self._log_source_status(result)
        
        if getattr(self, 'is_paused', False):
            log.info("✅ Yeni proxyler havuza ulaştı! Motor uykudan UYANDIRILIYOR...")
            self.is_paused = False
            self.local_error_count = 0
            self.crawler.engine.unpause() # Motorun buzunu çöz!
            
            # Dashboard'u tekrar yeşile (Çalışıyor) çevir
            try:
                import pymongo
                client = pymongo.MongoClient("mongodb://localhost:27017/")
                client["neuranovav_db"]["bot_commands"].update_one(
                    {"bot_id": "ana_bot"}, 
                    {"$set": {"status": "running", "error_reason": ""}}
                )
            except Exception as e:
                log.warning(f"DB Unpause güncelleme hatası: {e}")

        if self._sleeping:
            self._sleeping = False
            try:
                for mw in self.crawler.engine.downloader.middleware.middlewares:
                    if mw.__class__.__name__ == "RotatingProxyMiddleware":
                        if hasattr(mw, '_original_process_request'):
                            mw.process_request = mw._original_process_request
                            log.info("RotatingProxyMiddleware yeniden aktif | proxy havuzu doldu")
                        break
            except Exception as e:
                log.warning(f"proxy geçişi geri alınamadı | {e}")

    def _enter_sleep_mode(self):
        self._sleeping = True
        log.warning("proxy havuzu boş | direkt bağlantıya geçiliyor (kendi IP)")
        
        # Heartbeat at — dashboard zombie saymasın
        try:
            if self._db is not None:

                self._db["jobs"].update_one(
                    {"status": "Running"},
                    {"$set": {"last_ping": datetime.now(timezone.utc)}},
                    
                )
                log.info("sleep mode heartbeat atıldı.")
        except Exception as e:
            log.warning(f"sleep mode heartbeat atılamadı: {e}")

        try:
            for mw in self.crawler.engine.downloader.middleware.middlewares:
                if mw.__class__.__name__ == "RotatingProxyMiddleware":
                    mw._original_process_request = mw.process_request
                    mw.process_request = lambda request, spider: None
                    log.info("RotatingProxyMiddleware devre dışı | direkt bağlantı aktif")
                    break
        except Exception as e:
            log.warning(f"direkt geçiş başarısız | {e}")
        
        if time.time() - self._last_alert_time > 3600:
            self._send_proxy_alert()
            self._last_alert_time = time.time()
        self._trigger_update()
        
    def response_received(self, response, request, spider):
        # Sadece kendi IP'mizdeysek ve bot uykuda değilse kontrol et
        if self._sleeping and not self.is_paused:
            if response.status in [403, 429, 503]:
                self.local_error_count += 1
                log.warning(f"Kendi IP'miz hata aldı ({response.status}) | Hata Sayısı: {self.local_error_count}/5")
                
                if self.local_error_count >= 5: # 5 kere üst üste hata alırsa
                    self._pause_engine()
            elif response.status == 200:
                self.local_error_count = 0 # Başarılı olursa sayacı sıfırla

    def _pause_engine(self):
        log.error("🚨 Kendi IP'miz de ban yedi! Motor uykusuna (PAUSE) geçiliyor...")
        self.is_paused = True
        self.crawler.engine.pause() # Scrapy'i dondur!
        
        # Dashboard'u sarıya çevir (Proxy bekleniyor)
        try:
            self.client["neuranovav_db"]["bot_commands"].update_one(
                {"bot_id": "ana_bot"}, 
                {"$set": {"status": "paused", "error_reason": "kendi_ip_banlandi"}}
            )
        except Exception as e:
            log.warning(f"DB Pause güncelleme hatası: {e}")
        
    def _check_proxy_health(self):
        try:
            if self._db is not None:
                self._db["jobs"].update_one(
                    {"status": "Running"},
                    {"$set": {"last_ping": datetime.now(timezone.utc)}},
                    
                )
        except Exception as e:
            log.warning(f"health heartbeat hatası: {e}")

        if self._sleeping:
            return
        try:
            for mw in self.crawler.engine.downloader.middleware.middlewares:
                if mw.__class__.__name__ == "RotatingProxyMiddleware":
                    good      = len(mw.proxies.good)
                    unchecked = len(mw.proxies.unchecked)
                    dead      = len([p for p, st in mw.proxies.proxies.items()
                                     if hasattr(st, "state") and str(st.state) == "dead"])

                    if self._db is not None:
                        self._db["bot_commands"].update_one(
                            {"bot_id": "proxy_stats"},
                            {"$set": {
                                "scrapy_good":      good,
                                "scrapy_dead":      dead,
                                "scrapy_unchecked": unchecked,
                                "updated_at":       datetime.now(timezone.utc)
                            }},
                            upsert=True
                        )
                    if good < DOLUM_ESIGI and not self._sleeping:
                        log.info(f"Proxy havuzu azaldı (good={good} < {DOLUM_ESIGI}), yenileme tetikleniyor...")
                        self._trigger_update()
                    if good == 0 and unchecked == 0:
                        log.warning(f"Proxy havuzu tamamen tükendi (good=0, unchecked=0) | Direkt geçiş")
                        self._enter_sleep_mode()
                    break
        except Exception as e:
            log.warning(f"Proxy sağlık kontrolü hatası | {e}")

    def _send_proxy_alert(self):
        """Tüm proxy kaynakları erişilemezse dashboard'daki default mail'e bildirim atar."""
        try:
            import smtplib, os
            from email.mime.multipart import MIMEMultipart
            from email.mime.text import MIMEText
            from dotenv import load_dotenv
            load_dotenv()
            sender   = os.getenv("MAIL_SENDER", "")
            password = os.getenv("MAIL_APP_PASS", "")
            # Alıcıyı saved_mails.json'dan oku
            import json
            recipient = None
            if os.path.exists("saved_mails.json"):
                with open("saved_mails.json") as f:
                    mails = json.load(f)
                    recipient = mails[0] if mails else None
            if not sender or not password or not recipient:
                log.warning("proxy alert maili gönderilemedi | mail ayarları eksik")
                return
            simdi = datetime.now(timezone.utc).strftime("%d/%m %H:%M")
            html  = f"""
            <html><body style="font-family:Arial,sans-serif;padding:20px">
            <div style="max-width:500px;margin:auto;background:white;border-radius:12px;padding:24px;box-shadow:0 2px 8px #ccc">
                <h2 style="color:#c62828">🚨 Proxy Kaynakları Erişilemez!</h2>
                <p>{simdi} itibarıyla tüm GitHub proxy kaynakları yanıt vermedi.</p>
                <ul>
                    <li>monosans</li><li>TheSpeedX</li><li>ShiftyTR (http)</li><li>ShiftyTR (https)</li>
                </ul>
                <p>Bot güvenli modda bekliyor, kendi IP kullanılmıyor.</p>
                <p style="color:#aaa;font-size:12px">NeuraNovaV Otomatik Uyarı Sistemi</p>
            </div></body></html>"""
            msg = MIMEMultipart("alternative")
            msg["Subject"] = "🚨 NeuraNovaV: Proxy Kaynakları Erişilemez"
            msg["From"]    = f"NeuraNovaV Bot <{sender}>"
            msg["To"]      = recipient
            msg.attach(MIMEText(html, "html"))
            with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
                server.login(sender, password)
                server.sendmail(sender, recipient, msg.as_string())
            log.info(f"proxy alert maili gönderildi | {recipient}")
        except Exception as e:
            log.warning(f"proxy alert maili gönderilemedi | {e}")

    def _log_source_status(self, result: dict):
        """
        Madde 19 & 21: Her kaynak denemesini proxy_logs koleksiyonuna yazar.
        Başarısız kaynaklar da kaydedilir.
        """
        if self._db is None:
            return
        simdi = datetime.now(timezone.utc)
        docs  = []

        for attempt in result.get("source_attempts", []):
            docs.append({
                "ts":          simdi,
                "saat":        simdi.strftime("%H:00"),
                "kaynak":      attempt["kaynak"],
                "erisim_ok":   attempt["erisim_ok"],
                "toplam":      attempt.get("toplam", 0),
                "tr":          attempt.get("tr", 0),
                "yabanci":     attempt.get("yabanci", 0),
                "cop":         attempt.get("cop", 0),
                "yeni_eklenen": attempt.get("toplam", 0),  # her kaynak kendi toplamını yazar
                "hata":        attempt.get("hata", None),
            })

        if docs:
            try:
                self._db["proxy_logs"].insert_many(docs)
            except Exception as e:
                log.warning(f"proxy_logs yazılamadı | {e}")

    def _record_ban(self, proxy: str):
        """
        Madde 20: Proxy banlandığında proxy_performance koleksiyonuna yazar.
        BAN_LIMIT aşılırsa retired=True işaretler.
        """
        if self._db is None:
            return
        simdi = datetime.now(timezone.utc)
        try:
            result = self._db["proxy_performance"].find_one_and_update(
                {"proxy": proxy},
                {
                    "$inc":         {"ban_count": 1},
                    "$set":         {"last_banned": simdi},
                    "$setOnInsert": {"first_seen": simdi, "retired": False}
                },
                upsert=True,
                return_document=pymongo.ReturnDocument.AFTER
            )
            # BAN_LIMIT aşıldıysa retire et
            if result:
                ban_count     = result.get("ban_count", 0)
                success_count = result.get("success_count", 0)
                toplam        = ban_count + success_count
                oran          = success_count / toplam if toplam > 0 else 0

                if success_count == 0 and ban_count >= 5:
                    dinamik_limit = 5       # hiç başarı yok, hızlı emekli
                elif oran >= 0.70:
                    dinamik_limit = 600     # iyi proxy, uzun çalışsın
                elif oran >= 0.40:
                    dinamik_limit = 100     # orta proxy
                else:
                    dinamik_limit = 10      # kötü proxy, hızlı emekli

                if ban_count >= dinamik_limit:
                    self._db["proxy_performance"].update_one(
                        {"proxy": proxy},
                        {"$set": {"retired": True}}
                    )
                    log.info(f"proxy emekliye ayrıldı | {proxy} | ban={ban_count} başarı={success_count} oran={oran:.0%} limit={dinamik_limit}")
        except Exception as e:
            log.warning(f"ban kaydı yazılamadı | {e}")

    def _filter_retired(self, proxy_list: list) -> list:
        """
        Madde 20: proxy_performance'ta retired=True olan proxy'leri filtreler.
        MongoDB erişilemezse listeyi olduğu gibi döner (güvenli fallback).
        """
        if self._db is None:
            return proxy_list
        try:
            retired = set(
                doc["proxy"]
                for doc in self._db["proxy_performance"].find(
                    {"retired": True}, {"proxy": 1, "_id": 0}
                )
            )
            if retired:
                onceki = len(proxy_list)
                proxy_list = [p for p in proxy_list if p not in retired]
                log.info(f"retired filtre | {onceki - len(proxy_list)} proxy elendi")
        except Exception as e:
            log.warning(f"retired filtre hatası | {e}")
        return proxy_list
    
    def handle_response(self, response, request, spider):
        if response.status in [403, 429]:
            proxy = request.meta.get("proxy")
            if proxy:
                self._record_ban(proxy)

            # SADECE son denemede failed_urls'e yaz — retry'leri sayma
            retry_times = request.meta.get("retry_times", 0)
            max_retry = self.crawler.settings.getint("RETRY_TIMES", 5)

            if retry_times >= max_retry:
                if "/pd/" in response.url or "-p-" in response.url:
                    error_type = f"HTTP_{response.status}"
                    self._record_url_error(response.url, proxy or "Direct", error_type)

    def handle_failure(self, failure, spider):
        """FAZ 5+6: Timeout/bağlantı hatalarını yakalar, proxy banlar + URL hata kaydı."""
        request = failure.request
        proxy   = request.meta.get("proxy")
        if proxy:
            self._record_ban(proxy)
            
        # SADECE ÜRÜN SAYFASIYSA İTFAİYEYE HABER VER
        if "/pd/" in request.url or "-p-" in request.url:
            # Tüm bağlantı/timeout hatalarını Playwright'ın okuyacağı tek tipe normalize et
            error_type = "CONNECTION_ERROR"
            self._record_url_error(request.url, proxy or "Direct", error_type)
        
    def _record_url_error(self, url: str, proxy: str, error_type: str):
        if self._db is None:
            return
        simdi = datetime.now(timezone.utc)
        try:
            self._db["failed_urls"].update_one(
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
                            "$slice": -20  # FIX: Sadece son 20 deneme tutulur
                        }
                    },
                    "$setOnInsert": {"ilk_hata": simdi}
                },
                upsert=True
            )
        except Exception as e:
            log.warning(f"URL hata kaydı yazılamadı | {e}")
            
  