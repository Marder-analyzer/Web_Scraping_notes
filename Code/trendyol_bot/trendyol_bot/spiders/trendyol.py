import scrapy
from scrapy.loader import ItemLoader
import time
import json
import re
import pymongo
from datetime import datetime, timezone

from urllib.parse import urlparse, parse_qs, urlencode, urlunparse
from scrapy.spidermiddlewares.httperror import HttpError
from twisted.internet.error import DNSLookupError, TimeoutError, TCPTimedOutError, ConnectionRefusedError


from ..items import TrendyolBotItem
from .kategoriler import base_categories   # kategoriler.py'den geldi
from .fiyatlar import price_ranges         # fiyatlar.py'den geldi
from .selector import SELECTORS            # selector.py'den geldi
class TrendyolSpider(scrapy.Spider):
    name = "trendyol"
    allowed_domains = ["trendyol.com"]
    
    # URL'de tutulması gereken kritik parametreler (Fiyat ve Satıcıyı belirler)
    KEEP_PARAMS = {"boutiqueId", "merchantId", "productInfoModalEnabled"}
    MAX_SAYFA_LIMITI = 9999999
    
    categories = [
        f"{cat}&prc={prc}"
        for cat in base_categories
        for prc in price_ranges
    ]

    # --- REGEX PRE-COMPILATION (CPU TASARRUFU İÇİN) ---
    # Döngü içinde tekrar tekrar derlenmemesi için sınıf seviyesinde bir kere derliyoruz.
    REGEX_RATING_AVG = re.compile(r'"averageRating"\s*:\s*([\d.]+)')
    REGEX_RATING_VAL = re.compile(r'"ratingValue"\s*:\s*"?([\d.]+)"?')
    REGEX_RATING_COUNT_1 = re.compile(r'"totalRatingCount"\s*:\s*(\d+)')
    REGEX_RATING_COUNT_2 = re.compile(r'"ratingCount"\s*:\s*"?(\d+)"?')
    REGEX_RATING_COUNT_3 = re.compile(r'"reviewCount"\s*:\s*"?(\d+)"?')
    # Fiyat yakalamak için yeni regex'ler (window.__INITIAL_STATE__ içinden)
    REGEX_PRICE_INITIAL = re.compile(r'"sellingPrice"\s*:\s*\{"value"\s*:\s*([\d.]+)')
    REGEX_PRICE_DISCOUNT = re.compile(r'"discountedPrice"\s*:\s*\{"value"\s*:\s*([\d.]+)')

    def __init__(self, name = None, **kwargs):
        super(TrendyolSpider,self).__init__(name, **kwargs)
        # çekilen link sayısını ve süreyi takip etmek için değişkenler
        self.start_time = time.time()
        self.scraped_count = 0
        self._mongo_client = pymongo.MongoClient("mongodb://localhost:27017/")
        self._db = self._mongo_client["neuranovav_db"]
        self._failed_col = self._db["failed_urls"]
        self._cmd_col = self._db["bot_commands"]
        self._visited_col = self._db["visited_pages"]
        self._visited_col.create_index("key", unique=True, background=True)
        self._visited_col.create_index("page", background=True)
        self._throttle_sayac = 0  
        self._ram_sayac = 0
        self._ziyaret_cache = {"sayfa": -1, "kategoriler": set()}
        self._datetime = datetime
        self._timezone = timezone
        
        # En son job_id'yi al
        try:
            latest_job = self._db.jobs.find_one(sort=[("start_time", pymongo.DESCENDING)])
            self.job_id = latest_job["job_id"] if latest_job else None
        except:
            self.job_id = None
        
        self.logger.info(f"[Spider] Basladi | kombinasyon={len(self.categories)} | limit={self.MAX_SAYFA_LIMITI}")

    @classmethod
    def clean_url(cls, url):
        """URL'deki gereksiz takip parametrelerini siler, sadece kritik olanları tutar."""
        parsed = urlparse(url)
        params = parse_qs(parsed.query, keep_blank_values=True)
        filtered = {k: v for k, v in params.items() if k in cls.KEEP_PARAMS}
        clean = parsed._replace(query=urlencode(filtered, doseq=True))
        return urlunparse(clean)
    
    @staticmethod
    def _headers():
        # DİKKAT: "User-Agent" buradan silindi! 
        # Artık bu işi middlewares.py içindeki RandomUserAgentMiddleware dinamik olarak yapacak.
        return {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
            "Accept-Language": "tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7",
            "Cache-Control": "max-age=0",
            "Referer": "https://www.trendyol.com/",
            "Origin": "https://www.trendyol.com",
            "Sec-Ch-Ua": '"Chromium";v="122", "Not(A:Brand";v="24", "Google Chrome";v="122"',
            "Sec-Ch-Ua-Mobile": "?0",
            "Sec-Ch-Ua-Platform": '"Windows"',
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
            "Upgrade-Insecure-Requests": "1"
        }
    
    @staticmethod
    def _page_key(category: str, page: int) -> str:
        safe = re.sub(r'[.$]', '_', category)
        return f"{safe}__{page}"

    def _is_visited(self, category: str, page: int) -> bool:
        key = self._page_key(category, page)
        return self._visited_col.count_documents({"key": key, "status": "done"}, limit=1) > 0

    def _mark_visited(self, category: str, page: int, urun_sayisi: int = 0):
        key = self._page_key(category, page)
        try:
            self._visited_col.update_one(
                {"key": key},
                {"$set": {
                    "category": category,
                    "page": page,
                    "status": "done",
                    "urun_sayisi": urun_sayisi,
                    "ts": datetime.now(timezone.utc),
                }},
                upsert=True
            )
        except Exception as e:
            self.logger.warning(f"[Spider] visited_pages yazma hatasi: {e}")

    def _tamamlanan_max_sayfa(self) -> int:
        biten = self._visited_col.count_documents({"page": 1, "status": "done"})
        toplam = len(self.categories)
        if toplam == 0:
            return 0
        # Sayfa 1'in %95'i bitmemişse oradan devam et
        if biten < toplam * 0.95:
            return 0  # baslangic_sayfa = 1
        # Sayfa 1 tamamen bitti, en yüksek tamamlanan sayfayı bul
        for sayfa in range(2, 10001):
            biten = self._visited_col.count_documents({"page": sayfa, "status": "done"})
            if biten < toplam * 0.95:
                return sayfa - 1
        return 0
        
    #linkleri çekmek için ilk ayarlamaları yapacağız. JavaScript ile çalışan bir site olduğu için Playwright kullanarak sayfanın tam olarak yüklenmesini sağlayacağız.
    def start_requests(self):
        
        # === 1. TOPLAM HEDEFİ HESAPLA VE DB'YE YAZ ===
        try:
            toplam_kombinasyon = len(self.categories)
            
            # Her arama linkinden ortalama kaç ürün kazıyacağını tahmin ediyoruz.
            # Şimdilik 1 tam sayfa (24 ürün) olarak baz alıyoruz. İstediğin gibi değiştirebilirsin.
            try:
                pipeline = [
                    {"$group": {
                        "_id": None,
                        
                        "toplam_urun": {"$sum": {"$ifNull": ["$urun_sayisi", 0]}},
                        "toplam_sayfa": {"$sum": 1},
                        
                        "bos_sayfa": {"$sum": {"$cond": [{"$in": ["$urun_sayisi", [0, None]]}, 1, 0]}}
                    }}
                ]
                sonuc = list(self._visited_col.aggregate(pipeline))
                if sonuc and sonuc[0]["toplam_sayfa"] > 50:  # Yeterli veri varsa gerçek ortalamayı kullan
                    s = sonuc[0]
                    dolu_sayfa = s["toplam_sayfa"] - s["bos_sayfa"]
                    gercek_ort = s["toplam_urun"] / dolu_sayfa if dolu_sayfa > 0 else 0
                    bos_oran   = s["bos_sayfa"] / s["toplam_sayfa"]
                    dolu_kombinasyon = toplam_kombinasyon * (1 - bos_oran)
                    tahmini_urun_hedefi = int(dolu_kombinasyon * gercek_ort)
                else:
                    tahmini_urun_hedefi = toplam_kombinasyon * 24  # Yeterli veri yoksa varsayılan
            except:
                tahmini_urun_hedefi = toplam_kombinasyon * 24 
            
            
            # En son başlatılan oturumu (Job) bul ve tahmini ürün hedefini kaydet
            latest_job = self._db.jobs.find_one(sort=[("start_time", pymongo.DESCENDING)])

            if latest_job:
                self._db.jobs.update_one(
                    {"_id": latest_job["_id"]},
                    {"$set": {"total_target_urls": tahmini_urun_hedefi}}
                )
        except Exception as e:
            self.logger.warning(f"Hedef hesaplanamadı/yazılamadı: {e}")
        
        max_biten_sayfa = self._tamamlanan_max_sayfa()
        baslangic_sayfa = max_biten_sayfa + 1
        self.logger.info(
            f"[Spider] Devam noktasi | max_biten_sayfa={max_biten_sayfa} | baslangic_sayfa={baslangic_sayfa}"
        )
        istek_sayisi = 0
        atlanan_sayisi = 0
        
        # Başlangıç sayfası için ziyaret cache'ini tek sorguda yükle
        self._ziyaret_cache = {
            "sayfa": baslangic_sayfa,
            "kategoriler": set(
                doc["category"]
                for doc in self._visited_col.find(
                    {"page": baslangic_sayfa, "status": "done"},
                    {"category": 1, "_id": 0}
                )
            )
        }
        
        for category in self.categories:
            page = baslangic_sayfa
            if category in self._ziyaret_cache["kategoriler"]:

                atlanan_sayisi += 1
                continue
            url = f"https://www.trendyol.com/{category}&pi={page}"
            yield scrapy.Request(
                url=url,
                headers=self._headers(),
                meta={"category_name": category, "page_number": page},
                callback=self.parse,
                dont_filter=False,
                errback=self.handle_error
            )
            istek_sayisi += 1

        self.logger.info(
            f"[Spider] Istekler uretildi | gonderilen={istek_sayisi} | atlanan={atlanan_sayisi}"
        )
    
    # bütün linkleri çekme işlemi ve dağıtma işlemini yaptığımız yer.
    def parse(self, response):
        
        self._throttle_sayac += 1
        if self._throttle_sayac % 50 == 0:
            try:
                # Önce pay limitini oku
                shares = self._cmd_col.find_one({"bot_id": "ram_shares"})
                scrapy_limit = shares.get("scrapy_limit", 80) if shares else 80

                # Mevcut proje RAM yüzdesini hesapla
                sanal = __import__('psutil').virtual_memory()
                proje_ram = 0
                for proc in __import__('psutil').process_iter(['name', 'cmdline', 'memory_info']):
                    try:
                        name = (proc.info.get('name') or "").lower()
                        cmd  = " ".join(proc.info.get('cmdline') or []).lower()
                        if ("python" in name and any(x in cmd for x in ["scrapy","bot_manager","playwright","streamlit"])) or \
                        (("chrome" in name or "chromium" in name) and "--headless" in cmd) or \
                        "mongod" in name:
                            proje_ram += proc.info['memory_info'].rss
                    except: pass

                proje_yuzde = (proje_ram / sanal.total) * 100

                # Limite göre concurrent ayarla
                if   proje_yuzde > scrapy_limit:              hedef = 2
                elif proje_yuzde > scrapy_limit * 0.90:       hedef = 4
                elif proje_yuzde > scrapy_limit * 0.75:       hedef = 8
                else: hedef = self.crawler.settings.getint('CONCURRENT_REQUESTS', 16)


                self.crawler.engine.slot.concurrency = hedef

            except:
                pass
        
        category_name = response.meta.get("category_name")
        if not category_name:
            self.logger.warning(f"[Spider] category_name eksik, atlanıyor | {response.url}")
            return
        current_page = response.meta.get("page_number", 1)
        

        
        links = response.css("a.product-card::attr(href)").getall()
        
        if not links:
            self.logger.info(f"==> [SAYFA {current_page}] Bitti (link yok) | {category_name}")
            self._mark_visited(category_name, current_page, urun_sayisi=0)

            return

        self.logger.info(f"==> [SAYFA {current_page}] Tamamlandi | {len(links)} Urun Havuza Atildi | {category_name}")

        
        for link in links:
            # 301 Redirect yememek için /pd/ (Product Detail) takısını manuel ekliyoruz
            if "-p-" in link and "/pd/" not in link:
                link = link.replace(link.split("-p-")[0], "/pd" + link.split("-p-")[0], 1)
                
            full_url = response.urljoin(link)
            cleaned_url = self.clean_url(full_url)
            
            yield scrapy.Request(
                url=cleaned_url,
                headers=self._headers(),
                meta={"page_number": current_page},
                callback=self.parse_items,
                errback=self.handle_error
            )
        self._mark_visited(category_name, current_page, urun_sayisi=len(links))


        next_page = current_page + 1
        
        if next_page <= self.MAX_SAYFA_LIMITI:
            next_url = f"https://www.trendyol.com/{category_name}&pi={next_page}"
            yield scrapy.Request(
                url=next_url,
                headers=self._headers(),
                meta={"category_name": category_name, "page_number": next_page},
                callback=self.parse,
                errback=self.handle_error
            )
        else:
            self.logger.warning(f"[Spider] GÜVENLİK FRENİ: limit={self.MAX_SAYFA_LIMITI} asildi.")

    # linke gittiğimizde ürünlerin verilerini çektiğimiz yer
    # Urun verilerini cektigimiz ana fonksiyon
    def parse_items(self, response):
        self.current_page = response.meta.get("page_number", 1)
        # MongoDB'ye current_page yaz
        try:
            self._db.jobs.update_one(
                {"job_id": self.job_id},
                {"$set": {"current_page": self.current_page}}
            )
        except:
            pass
        loader = ItemLoader(item=TrendyolBotItem(), response=response)
        loader.add_value("url", response.url)

        json_data = self._get_product_json(response)
        
        if json_data:
            self._load_categories(loader, response, json_data)
            self._load_from_json(loader, json_data)
            
            # JSON'dan gelen eksik alanları HTML'den tamamla
            self._load_eksik_alanlar(loader, response) 
        else:
            self.logger.warning(f"[Spider] JSON-LD yok, HTML fallback | {response.url}")
            self._load_categories(loader, response, None)
            self._load_from_html(loader, response)
        
        self.scraped_count += 1
        loader.add_value("proxy_used", response.meta.get("proxy", "Direct"))
        yield loader.load_item()

    # JSON-LD verisini çekmek için yardımcı fonksiyon. Bu fonksiyon, sayfadaki tüm script tag'lerini kontrol eder ve Product tipindeki JSON-LD verisini bulur.
    def _get_product_json(self, response):
        scripts = response.xpath('//script[@type="application/ld+json"]/text()').getall()
        for script in scripts:
            try:
                data = json.loads(script)
                if isinstance(data, list): data = data[0]
                if isinstance(data, dict) and data.get('@type') == 'Product':
                    return data
            except (json.JSONDecodeError, TypeError, KeyError):
                # Daha spesifik hata yakalama (Geniş exception'dan kaçındık)
                continue
        return None

    # category özgü yapıldı saçma çıktılar tekrar eden çıktıları burada hallettik
    def _load_categories(self, loader, response, json_data):
        raw_categories = []
        if json_data:
            breadcrumb = json_data.get("breadcrumb", {})
            items = breadcrumb.get("itemListElement", []) if breadcrumb else []
            if items:
                
                raw_categories = []
                for el in sorted(items, key=lambda x: x.get("position", 0)):
                    try:
                        item = el.get("item", {})
                        if not isinstance(item, dict):
                            continue
                        name = item.get("name", "").strip()
                        if name and name != "Trendyol":
                            raw_categories.append(name)
                    except:
                        continue
                
        if not raw_categories and json_data and json_data.get("category"):
            cat_data = json_data.get("category")
            raw_categories = cat_data if isinstance(cat_data, list) else [cat_data]
        if raw_categories:
            clean_categories = []
            seen = set()
            for cat in raw_categories:
                stripped_cat = cat.strip()
                if stripped_cat and stripped_cat.lower() not in seen:
                    clean_categories.append(stripped_cat)
                    seen.add(stripped_cat.lower())
            final_categories = clean_categories[:4]
            if final_categories:
                loader.add_value("category", " > ".join(final_categories))
                return
        # YENİ FALLBACK: category_name meta'dan al (URL'deki kategori)
        category_name = response.meta.get("category_name", "")
        if category_name:
            loader.add_value("category", category_name)

    # JSON-LD verisi varsa buradan çekmeye çalışırız. Bu genellikle daha temiz ve düzenli veri sağlar.
    def _load_from_json(self, loader, data):
        
        if data.get("name"): loader.add_value("title", data.get("name"))
        
        offers = data.get("offers", {})
        if isinstance(offers, dict) and offers.get("price"):
            loader.add_value("price", str(offers.get("price")))
        
        img_data = data.get("image")
        if img_data:
            if isinstance(img_data, list):
                clean_images = [img.get('contentUrl') if isinstance(img, dict) else img for img in img_data]
                loader.add_value("images", clean_images)
            elif isinstance(img_data, dict):
                loader.add_value("images", img_data.get('contentUrl'))
            else:
                loader.add_value("images", img_data)
        
        if data.get("description"): loader.add_value("explanation", data.get("description"))
        
        agg_rating = data.get("aggregateRating", {})
        if isinstance(agg_rating, dict):
            if agg_rating.get("ratingValue"): loader.add_value("evaluation", str(agg_rating.get("ratingValue")))
            if agg_rating.get("ratingCount"): loader.add_value("evaluation_len", str(agg_rating.get("ratingCount")))
            
        additional_properties = data.get("additionalProperty")
        if additional_properties and isinstance(additional_properties, list):
            features_dict = {}
            for prop in additional_properties:
                if isinstance(prop, dict) and prop.get("name") and prop.get("value"):
                    key = str(prop.get("name")).strip()
                    val = str(prop.get("value")).strip()
                    features_dict[key] = val
            if features_dict:
                loader.add_value("attributes", features_dict)

    def _load_eksik_alanlar(self, loader, response):
        # NOT: Fallback mantığı Pipeline'da veya son item üretilirken çözüleceği için
        # buraya sadece JSON'da kesinlikle olmayanları çekme mantığı bırakıldı.

        # --- YENİ ZIRHLI FİYAT KONTROLÜ (GİZLİ JS İÇİNDEN) ---
        if not loader.get_collected_values('price'):
            price_match = self.REGEX_PRICE_DISCOUNT.search(response.text) or self.REGEX_PRICE_INITIAL.search(response.text)
            if price_match:
                loader.add_value("price", price_match.group(1))
                self.logger.debug(f"[Spider] Fiyat JS'ten kurtarildi | {response.url}")

        # HTML'den Regex ile hızlı tarama (Pre-compiled regex kullanıyoruz)
        eval_match = self.REGEX_RATING_AVG.search(response.text) or self.REGEX_RATING_VAL.search(response.text)
        if eval_match:
            loader.add_value("evaluation", eval_match.group(1))

        count_match = self.REGEX_RATING_COUNT_1.search(response.text) or \
                      self.REGEX_RATING_COUNT_2.search(response.text) or \
                      self.REGEX_RATING_COUNT_3.search(response.text)
        if count_match:
            loader.add_value("evaluation_len", count_match.group(1))

        # Attributes fallback
        features_dict = {}
        attribute_blocks = response.css("div.attributes div.attribute-item")
        for block in attribute_blocks:
            key = block.css("div.name::text").get()
            val = block.css("div.value::text").get()
            if key and val:
                features_dict[key.strip()] = val.strip()
        if features_dict:
            loader.add_value("attributes", features_dict)
                    
    # JSON-LD verisi yoksa veya eksikse, HTML üzerinden çekmeye çalışırız. Bu genellikle daha karmaşık ve düzensiz olabilir, bu yüzden öncelikli olarak JSON-LD'yi tercih ederiz.
    def _load_from_html(self, loader, response):
        title_selectors = SELECTORS.get("title")
        if isinstance(title_selectors, list):
            for selector in title_selectors:
                title_texts = response.css(selector + ' ::text').getall() if '::text' not in selector else response.css(selector).getall()
                if title_texts:
                    full_title = ' '.join([t.strip() for t in title_texts if t.strip()]).replace('"', '').replace("'", "").strip()
                    if full_title:
                        loader.add_value("title", full_title)
                        break

        if not loader.get_collected_values('price'):
            price_selectors = SELECTORS.get("price")
            if isinstance(price_selectors, list):
                for selector in price_selectors:
                    price_values = response.css(selector).getall()
                    if price_values:
                        # Gelen "1.250,99 TL" gibi karmaşık veriyi saf sayıya (1250.99) çeviriyoruz
                        clean_prices = [p.replace('TL', '').replace('.', '').replace(',', '.').strip() for p in price_values if p.strip()]
                        if clean_prices:
                            loader.add_value("price", clean_prices[0]) # Sadece ilk bulduğunu al
                            break
            else:
                price_val = response.css(price_selectors).get()
                if price_val:
                    clean_price = price_val.replace('TL', '').replace('.', '').replace(',', '.').strip()
                    loader.add_value("price", clean_price)

        eval_match = self.REGEX_RATING_AVG.search(response.text) or self.REGEX_RATING_VAL.search(response.text)
        if eval_match: loader.add_value("evaluation", eval_match.group(1))

        count_match = self.REGEX_RATING_COUNT_1.search(response.text) or \
                      self.REGEX_RATING_COUNT_2.search(response.text) or \
                      self.REGEX_RATING_COUNT_3.search(response.text)
        if count_match: loader.add_value("evaluation_len", count_match.group(1))

        images_selectors = SELECTORS.get("images")
        if isinstance(images_selectors, list):
            for selector in images_selectors:
                img_values = response.css(selector).getall()
                if img_values:
                    clean_imgs = [img.strip() for img in img_values if img.strip()]
                    if clean_imgs:
                        loader.add_value("images", clean_imgs)
                        break
        else:
            loader.add_css("images", images_selectors)

        explanation_selectors = SELECTORS.get("explanation")
        if isinstance(explanation_selectors, list):
            for selector in explanation_selectors:
                expl_values = response.css(selector).getall()
                if expl_values:
                    clean_expl = ' '.join([text.strip() for text in expl_values if text.strip()])
                    if clean_expl:
                        loader.add_value("explanation", clean_expl)
                        break

        features_dict = {}
        attribute_blocks = response.css("div.attributes div.attribute-item")
        for block in attribute_blocks:
            key = block.css("div.name::text").get()
            val = block.css("div.value::text").get()
            if key and val:
                features_dict[key.strip()] = val.strip()
        if features_dict: loader.add_value("attributes", features_dict)
         
    def handle_error(self, failure):
        # --- GELİŞMİŞ LOGLAMA ---
        # Hata türüne göre nokta atışı tespit yapıyoruz
        request_url = failure.request.url
        
        # URL tipini belirle: liste sayfası mı, ürün sayfası mı?
        if "pi=" in request_url:
            sayfa_turu = "liste"
        elif "/pd/" in request_url or "-p-" in request_url:
            sayfa_turu = "urun"
        else:
            sayfa_turu = "diger"
        
        hata_tipi = None
        
        if failure.check(HttpError):
            response = failure.value.response
            self.logger.error(f"[Spider] HTTP {response.status} | {request_url}")
            if response.status == 404:
                if "pi=" in request_url:  # Liste sayfasıysa ziyaret edildi say
                    meta = failure.request.meta
                    self._mark_visited(
                        meta.get("category_name", request_url),
                        meta.get("page_number", 1),
                        urun_sayisi=0
                    )
                return
            elif response.status == 403:
                hata_tipi = "HTTP_403"
            elif response.status == 429:
                hata_tipi = "HTTP_429"
                
        elif failure.check(DNSLookupError):
            self.logger.error(f"[Spider] DNS hatasi | {request_url}")
            hata_tipi = "DNS_Error"
        elif failure.check(TimeoutError, TCPTimedOutError, ConnectionRefusedError):
            self.logger.error(f"[Spider] Timeout | {request_url}")
            hata_tipi = "Timeout"
        else:
            self.logger.error(f"[Spider] Bilinmeyen hata | {request_url} | {repr(failure)}")
            hata_tipi = "UnknownError"
        
        # Sadece liste ve ürün sayfalarını kaydet, "diger" kaydetme
        if hata_tipi and sayfa_turu in ("liste", "urun"):
            try:
                simdi = self._datetime.now(self._timezone.utc)
                self._failed_col.update_one(
                    {"url": request_url},
                    {
                        "$set": {
                            "hata_tipi": hata_tipi,
                            "sayfa_turu": sayfa_turu,
                            "cozuldu": False,
                            "son_deneme": simdi,
                        },
                        "$inc": {"deneme_sayisi": 1},
                        "$setOnInsert": {"ilk_hata": simdi}
                    },
                    upsert=True
                )
            except Exception as e:
                self.logger.warning(f"[Spider] Hata kaydedilemedi: {e}")
            
    def closed(self, reason):
        duration = time.time() - self.start_time
        self.logger.info(
            f"[Spider] Kapandi | sebep={reason} | "
            f"sure={duration:.1f}s ({duration/60:.1f}dk) | "
            f"cekilen={self.scraped_count}"
        )
        try:
            self._mongo_client.close()
        except:
            pass