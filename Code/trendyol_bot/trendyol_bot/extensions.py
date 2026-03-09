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
        self.crawler    = crawler
        self.interval   = 900
        self._sleeping  = False
        self._mongo_col = None

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
        return ext

    # ─────────────────────────────────────────────────────────────────────────
    # Scrapy sinyalleri
    # ─────────────────────────────────────────────────────────────────────────

    def spider_opened(self, spider):
        import logging
        logging.getLogger('scrapy.core.downloader.tls').setLevel(logging.ERROR)
        try:
            client = pymongo.MongoClient(MONGO_URI, serverSelectionTimeoutMS=3000)
            self._mongo_col = client[MONGO_DB]["jobs"]
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
            "source": None, "trash": 0, "source_reachable": False
        }

        for url in PROXY_SOURCES:
            try:
                req  = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
                resp = urllib.request.urlopen(req, timeout=10)
                data = resp.read().decode("utf-8")
                result["source_reachable"] = True

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

                if proxies:
                    tr_list      = [p for p in proxies if _is_tr(p)]
                    foreign_list = [p for p in proxies if not _is_tr(p)]

                    result.update({
                        "all":     proxies,
                        "tr":      tr_list,
                        "foreign": foreign_list,
                        "source":  url.split("/")[3],
                        "trash":   trash,
                    })

                    log.info(
                        f"kaynak OK | {result['source']} | "
                        f"toplam: {len(proxies)} | "
                        f"TR: {len(tr_list)} | "
                        f"yabancı: {len(foreign_list)} | "
                        f"çöp: {trash}"
                    )
                    return result

            except Exception as e:
                log.warning(f"kaynak başarısız | {url.split('/')[3]} | {e}")

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

                    break

        except Exception as e:
            log.warning(f"enjeksiyon hatası | {e}")

        # Madde 4: proxies.txt güncelle — banlılar hariç
        try:
            if mw_ref is not None:
                active_proxies = list(mw_ref.proxies.proxies.keys())
            else:
                active_proxies = ordered

            with open("proxies.txt", "w", encoding="utf-8") as f:
                f.write("\n".join(active_proxies) + "\n")
        except Exception as e:
            log.warning(f"proxies.txt yazılamadı | {e}")

        log.info(
            f"güncelleme tamam | "
            f"+{added} yeni | "
            f"-{banned_removed} banlı silindi | "
            f"TR: {len(result['tr'])} | "
            f"çöp: {result['trash']}"
        )

        # Madde 5: jobs koleksiyonuna kısa log
        self._log_to_mongo(result, added, banned_removed)

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
        reactor.callLater(SLEEP_ON_EMPTY, self._trigger_update)

    def _log_to_mongo(self, result: dict, added: int, banned_removed: int):
        """Madde 5: jobs koleksiyonuna proxy log notu (yeni koleksiyon açılmaz)."""
        if self._mongo_col is None:
            return
        try:
            self._mongo_col.update_one(
                {"type": "proxy_log"},
                {"$push": {"updates": {
                    "ts":               datetime.now(timezone.utc),
                    "kaynak":           result.get("source", "bilinmiyor"),
                    "kaynak_erisim":    result.get("source_reachable", False),
                    "toplam_cekilen":   len(result["all"]),
                    "tr_adet":          len(result["tr"]),
                    "yabanci_adet":     len(result["foreign"]),
                    "cop_adet":         result["trash"],
                    "yeni_eklenen":     added,
                    "banlanan_silinen": banned_removed,
                }}},
                upsert=True
            )
        except Exception as e:
            log.warning(f"mongo log hatası | {e}")