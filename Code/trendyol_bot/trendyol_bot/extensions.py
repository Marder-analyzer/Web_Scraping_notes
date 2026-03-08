import os
import logging
import urllib.request
from twisted.internet import task
from scrapy import signals

class LiveProxyUpdater:
    def __init__(self, crawler):
        self.crawler = crawler
        self.logger = logging.getLogger(__name__)
        self.interval = 3600
        self.proxy_url = "https://raw.githubusercontent.com/monosans/proxy-list/main/proxies/http.txt"

    @classmethod
    def from_crawler(cls, crawler):
        ext = cls(crawler)
        # Bot açıldığında ve kapandığında eklentimizi tetiklemesi için bağlıyoruz
        crawler.signals.connect(ext.spider_opened, signal=signals.spider_opened)
        crawler.signals.connect(ext.spider_closed, signal=signals.spider_closed)
        return ext

    def spider_opened(self, spider):
        # Arka planda asenkron çalışacak bir saatli bomba (LoopingCall) kuruyoruz
        self.task = task.LoopingCall(self.update_proxies)
        self.task.start(self.interval, now=False)
        self.logger.info(f"Oto-Proxy Güncelleyici Aktif! Her {self.interval} saniyede bir yeni mermi basılacak.")

    def spider_closed(self, spider):
        if self.task.running:
            self.task.stop()

    def update_proxies(self):
        self.logger.info("Zamanlanmış Görev: Canlı proxy havuzu güncelleniyor...")
        try:
            # 1. Yeni proxyleri indir
            req = urllib.request.Request(self.proxy_url, headers={'User-Agent': 'Mozilla/5.0'})
            response = urllib.request.urlopen(req, timeout=10)
            data = response.read().decode('utf-8')
            
            # Gelen listeyi temizle ve http:// ekle
            new_proxies = [f"http://{p.strip()}" for p in data.strip().split('\n') if p.strip()]
            
            # --- YENİ EKLENEN KISIM: SENİN FİKRİN! ---
            # İndirdiğimiz bu taze listeyi hem RAM'e basacağız hem de dosyaya yedekleyeceğiz!
            with open("proxies.txt", "w", encoding="utf-8") as f:
                for p in new_proxies:
                    f.write(p + "\n")
            # ----------------------------------------
            
            # 2. Çalışan Scrapy botunun hafızasına sız ve RotatingProxyMiddleware'i bul
            for mw in self.crawler.engine.downloader.middleware.middlewares:
                if mw.__class__.__name__ == 'RotatingProxyMiddleware':
                    from rotating_proxies.expire import ProxyState
                    
                    added_count = 0
                    # 3. Sadece havuzda OLMAYAN yepyeni IP'leri sisteme şırınga et
                    for p in new_proxies:
                        if p not in mw.proxies.proxies:
                            mw.proxies.proxies[p] = ProxyState()
                            mw.proxies.unchecked.add(p)
                            added_count += 1
                            
                    self.logger.info(f"Sisteme {added_count} adet YENİ proxy enjekte edildi! (Aynı zamanda proxies.txt güncellendi)")
                    break
                    
        except Exception as e:
            self.logger.error(f"Oto-Proxy Güncelleme Hatası: {e}")