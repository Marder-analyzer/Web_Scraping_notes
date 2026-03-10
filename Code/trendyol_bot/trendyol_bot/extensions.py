import logging
import urllib.request
from datetime import datetime, timezone

import pymongo
from scrapy import signals
from twisted.internet import task, threads, reactor

log = logging.getLogger("proxy_updater")

# ── Madde 2: Çoklu kaynak ─────────────────────────────────────────────────────
PROXY_SOURCES = [
    "https://raw.githubusercontent.com/monosans/proxy-list/main/proxies/http.txt",
    "https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/http.txt",
    "https://raw.githubusercontent.com/ShiftyTR/Proxy-List/master/http.txt",
    "https://raw.githubusercontent.com/ShiftyTR/Proxy-List/master/https.txt",
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

SLEEP_ON_EMPTY = 600      # Madde 7: havuz boşalınca uyku süresi (10 dk = 600 sn)
BAN_LIMIT       = 10    # Madde 20: kaç ban sonra retired
MONGO_URI      = "mongodb://localhost:27017/"
MONGO_DB       = "neuranovav_db"    # pipelines.py ile aynı


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
        self.crawler = crawler
        self.interval = 900
        self._sleeping = False
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
        ext = cls(crawler)
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
        self.task.start(self.interval, now=True)  # başlangıçta hemen çek
        log.info(
            f"proxy güncelleyici aktif | "
            f"{len(PROXY_SOURCES)} kaynak | "
            f"her {self.interval // 60} dk"
        )

    def spider_closed(self, spider):
        if hasattr(self, "task") and self.task.running:
            self.task.stop()

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
        """
        Scrapy nesnelerine kesinlikle dokunmaz.
        Dönüş: {all, tr, foreign, source, trash, source_reachable}
        """
        result = {
            "all": [], "tr": [], "foreign": [],
            "source": None, "trash": 0, "source_reachable": False, "source_attempts": []
        }

        for url in PROXY_SOURCES:
            source_name = url.split("/")[3]
            attempt     = {"kaynak": source_name, "erisim_ok": False,
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
                    parts = line.split(":")
                    if len(parts) == 2 and parts[1].isdigit():
                        proxies.append(f"http://{line}")
                    else:
                        trash += 1
                        
                tr_list      = [p for p in proxies if _is_tr(p)]
                foreign_list = [p for p in proxies if not _is_tr(p)]

                attempt.update({
                    "erisim_ok": True,
                    "toplam":    len(proxies),
                    "tr":        len(tr_list),
                    "yabanci":   len(foreign_list),
                    "cop":       trash,
                })
                result["source_attempts"].append(attempt)

                if proxies:
                    result.update({
                        "all":              proxies,
                        "tr":               tr_list,
                        "foreign":          foreign_list,
                        "source":           source_name,
                        "trash":            trash,
                        "source_reachable": True,
                    })
                    log.info(
                        f"kaynak OK | {source_name} | "
                        f"toplam: {len(proxies)} | TR: {len(tr_list)} | "
                        f"yabancı: {len(foreign_list)} | çöp: {trash}"
                    )
                    return result

            except Exception as e:
                attempt["hata"] = str(e)
                result["source_attempts"].append(attempt)
                log.warning(f"kaynak başarısız | {source_name} | {e}")

        log.error("tüm proxy kaynakları erişilemez!")
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
        added          = 0
        banned_removed = 0
        mw_ref         = None

        try:
            for mw in self.crawler.engine.downloader.middleware.middlewares:
                if mw.__class__.__name__ == "RotatingProxyMiddleware":
                    mw_ref = mw
                    from rotating_proxies.expire import ProxyState

                    # Madde 3: sadece yeni proxy ekle
                    for p in ordered:
                        if p not in mw.proxies.proxies:
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

        self._log_source_status(result)

        if self._sleeping:
            self._sleeping = False
            log.info("uyku modundan çıkıldı, proxy havuzu doldu")

    def _enter_sleep_mode(self):
        """
        Madde 7: Proxy kaynakları boş veya erişilemez.
        Kendi IP'ye GEÇİLMEZ. 10 dakika bekle, tekrar dene.
        """
        self._sleeping = True
        log.warning(
            f"proxy havuzu boş | "
            f"GÜVENL MOD: kendi IP kullanılmıyor | "
            f"{SLEEP_ON_EMPTY // 60} dk sonra tekrar denenecek"
        )
        self._send_proxy_alert()
        reactor.callLater(SLEEP_ON_EMPTY, self._trigger_update)

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
                "yeni_eklenen": result.get("yeni_eklenen", 0),  # enjeksiyon sonrası güncellenir
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
            if result and result.get("ban_count", 0) >= BAN_LIMIT:
                self._db["proxy_performance"].update_one(
                    {"proxy": proxy},
                    {"$set": {"retired": True}}
                )
                log.info(f"proxy emekliye ayrıldı | {proxy} | {BAN_LIMIT} ban")
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
        """FAZ 5+6: 403/429 HTTP hatalarını yakalar, proxy banlar + URL hata kaydı."""
        if response.status in [403, 429]:
            proxy = request.meta.get("proxy")
            if proxy:
                self._record_ban(proxy)
            error_type = f"HTTP_{response.status}"
            self._record_url_error(response.url, proxy or "Direct", error_type)

    def handle_failure(self, failure, spider):
        """FAZ 5+6: Timeout/bağlantı hatalarını yakalar, proxy banlar + URL hata kaydı."""
        request = failure.request
        proxy   = request.meta.get("proxy")
        if proxy:
            self._record_ban(proxy)
        error_type = failure.type.__name__ if failure.type else "UnknownError"
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
                            "ts":         simdi,
                            "proxy":      proxy,
                            "error_type": error_type,
                        }
                    },
                    "$setOnInsert": {"ilk_hata": simdi}
                },
                upsert=True
            )
        except Exception as e:
            log.warning(f"URL hata kaydı yazılamadı | {e}")