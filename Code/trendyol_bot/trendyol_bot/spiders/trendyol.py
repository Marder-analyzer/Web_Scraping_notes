import scrapy
from scrapy_playwright.page import PageMethod
from scrapy.loader import ItemLoader
import time
from ..items import TrendyolBotItem
import json
import re
class TrendyolSpider(scrapy.Spider):
    name = "trendyol"
    allowed_domains = ["trendyol.com"]
    start_urls = ["https://trendyol.com"]
    
    # Selectorları merkezleştireceğiz
    
    SELECTORS = {
        "category": "ul.breadcrumb-list li.product-detail-breadcrumbs-item a::text",
        
        "title": [
            "h1.product-title",  
            "h1[data-testid='product-title']",
            "h1.pr-new-br span.prdct-desc-cntnr-name::text",
            "h1::text"
        ],
        
        "evaluation": [
            "div.envoy div.product-details-other-details div.reviews-summary-rating-detail span.reviews-summary-average-rating::text",
            "div.product-details-other-details div.variant-pdp span.reviews-summary-average-rating::text",
        ],
        
        "evaluation_len": [
            "div.product-details-other-details a.reviews-summary-reviews-detail span.b::text",
            "div.product-details-other-details div.variant-pdp a.reviews-summary-reviews-detail span.b::text",
        ],
        
        "price": [
            "div.prc-box-dsc::text",
            "div.prc-dsc::text",
            "span.prc-slg::text",
            "div.product-price-container span.discounted::text",
            "div.campaign-price-content span::text",
            "div.campaign-price-content p.old-price::text",
            "div.price-wrapper div.price-container span.discounted::text",
            "div.price-wrapper div.ty-plus-price-original-price::text",
            "div.price-wrapper span.discounted::text",
            "div.price-wrapper div.price-view span.original::text",
        ],
        
        "images": "img[data-testid='image']::attr(src)",
        
        "explanation": [
            "div.product-info-content *::text",          # Ürün Bilgileri (Madde madde olan yer)
            "div.content-description-container *::text", # Ürün Açıklaması (Detaylı metin)
            "div.detail-desc-container *::text"          # Eski tip açıklama yapısı
        ]
        
    }


    def __init__(self, name = None, **kwargs):
        super(TrendyolSpider,self).__init__(name, **kwargs)
        # çekilen link sayısını ve süreyi takip etmek için değişkenler
        self.start_time = time.time()
        self.scraped_count = 0
        self.logger.info(f"Trendyol Spider başlatıldı. Başlangıç zamanı: {time.ctime(self.start_time)}")
    
    #categorileri ayarlama birden fazla çekicez her biri için
    categories = [
        "elbise-x-c56"
        #ve diğer kategoriler eklenebilir
    ]
    
        
    #linkleri çekmek için ilk ayarlamaları yapacağız. JavaScript ile çalışan bir site olduğu için Playwright kullanarak sayfanın tam olarak yüklenmesini sağlayacağız.
    def start_requests(self):
        self.logger.info(f"Toplam {len(self.categories)} kategori için işlem başlatılıyor.")
        for category in self.categories:
            # pi=1 (1. sayfa) parametresi ile başlıyoruz
            url = f"https://www.trendyol.com/{category}?pi=1"
            self.logger.debug(f"URL istek gönderildi: {url}")
            yield scrapy.Request(
                url=url,
                meta={
                    "category_name": category, # Kategori adını diğer fonksiyona taşıyoruz
                    "page_number": 1           # Sayfa numarasını takip ediyoruz
                },
                callback=self.parse,
                dont_filter=True,
                errback=self.handle_error
            )
    
    # bütün linkleri çekme işlemi ve dağıtma işlemini yaptığımız yer.
    def parse(self, response):
        category_name = response.meta.get("category_name")
        current_page = response.meta.get("page_number", 1)
        
        self.logger.info(f"Kategori sayfası yüklendi: {response.url}")
        
        # Ürün linklerini topla
        links = response.css("a.product-card::attr(href)").getall()
        
        # Eğer sayfada ürün varsa:
        if links:
            self.logger.info(f"Sayfa {current_page}'de {len(links)} adet link bulundu ve işleniyor.")
            
            # 1. Bulunan ürünlerin detay sayfalarına git
            for link in links:
                full_url = response.urljoin(link)
                yield scrapy.Request(
                    url=full_url,
                    callback=self.parse_items,
                    # Detay sayfalarında playwright kullanmıyoruz
                    errback=self.handle_error
                )
            
            # 2. BİR SONRAKİ SAYFAYA GEÇİŞ YAP (Akıllı Sayfalama)
            next_page = current_page + 1
            MAX_SAYFA_LIMITI = 2 # 200 sayfa = 4800 ürün
            
            if next_page <= MAX_SAYFA_LIMITI:
                next_url = f"https://www.trendyol.com/{category_name}?pi={next_page}"
                
                yield scrapy.Request(
                    url=next_url,
                    meta={
                        "category_name": category_name,
                        "page_number": next_page
                    },
                    callback=self.parse,
                    errback=self.handle_error
                )
            else:
                self.logger.info(f"GÜVENLİK FRENİ: Maksimum sayfa limitine ({MAX_SAYFA_LIMITI}) ulaşıldı. Sonraki sayfaya geçiş durduruldu.")
                
        # Eğer sayfada hiç ürün yoksa (Kategorinin sonuna geldiysek):
        else:
            self.logger.info(f"Sayfa {current_page} boş. {category_name} kategorisinin sonuna gelindi!")
    # linke gittiğimizde ürünlerin verilerini çektiğimiz yer
    # Urun verilerini cektigimiz ana fonksiyon
    def parse_items(self, response):
        # bütün herşeyi bu boş loader üzerinden yapacağız. Bu sayede verileri temizleme ve düzenleme işlemlerini daha kolay yapabiliriz.
        loader = ItemLoader(item=TrendyolBotItem(), response=response)
        loader.add_value("url", response.url)

        # JSON-LD verisini cek
        json_data = self._get_product_json(response)
        
        if json_data:
            # JSON-LD varsa kategori ve diger verileri yukle
            self._load_categories(loader, response, json_data)
            self._load_from_json(loader, json_data)
        else:
            # JSON-LD yoksa HTML'den cekmeye calis
            self.logger.warning(f"JSON-LD bulunamadi, HTML fallback kullaniliyor: {response.url}")
            self._load_categories(loader, response, None)
            
        self._load_from_html(loader, response)
        
        self.scraped_count += 1
        yield loader.load_item()

    # JSON-LD verisini çekmek için yardımcı fonksiyon. Bu fonksiyon, sayfadaki tüm script tag'lerini kontrol eder ve Product tipindeki JSON-LD verisini bulur.
    def _get_product_json(self, response):
        scripts = response.xpath('//script[@type="application/ld+json"]/text()').getall()
        for script in scripts:
            try:
                data = json.loads(script)
                # Bazı sayfalar liste döner, ilkini al
                if isinstance(data, list): data = data[0]
                
                if isinstance(data, dict) and data.get('@type') == 'Product':
                    return data
            except:
                continue
        return None

    # category özgü yapıldı saçma çıktılar tekrar eden çıktıları burada hallettik
    def _load_categories(self, loader, response, json_data):
        raw_categories = response.css(self.SELECTORS["category"]).getall()
        
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

    # JSON-LD verisi varsa buradan çekmeye çalışırız. Bu genellikle daha temiz ve düzenli veri sağlar.
    def _load_from_json(self, loader, data):
        
        # title
        if data.get("name"):
            loader.add_value("title", data.get("name"))
        
        # price
        offers = data.get("offers", {})
        if isinstance(offers, dict) and offers.get("price"):
            loader.add_value("price", str(offers.get("price")))
        
        # image
        img_data = data.get("image")
        if img_data:
            if isinstance(img_data, list):
                clean_images = [
                    img.get('contentUrl') if isinstance(img, dict) else img 
                    for img in img_data
                ]
                loader.add_value("images", clean_images)
            elif isinstance(img_data, dict):
                loader.add_value("images", img_data.get('contentUrl'))
            else:
                loader.add_value("images", img_data)
        
        # description
        if data.get("description"):
            loader.add_value("explanation", data.get("description"))
        
        # evaluation
        agg_rating = data.get("aggregateRating", {})
        if isinstance(agg_rating, dict) and agg_rating.get("ratingValue"):
            loader.add_value("evaluation", str(agg_rating.get("ratingValue")))
            
        # evaluation_len
        if isinstance(agg_rating, dict) and agg_rating.get("ratingCount"):
            loader.add_value("evaluation_len", str(agg_rating.get("ratingCount")))
            
        # ATTRIBUTES
        additional_properties = data.get("additionalProperty")
        
        if additional_properties and isinstance(additional_properties, list):
            features_dict = {}
            for prop in additional_properties:
                # Her bir özelliğin "name" (anahtar) ve "value" (değer) kısımlarını alıyoruz
                if isinstance(prop, dict) and prop.get("name") and prop.get("value"):
                    key = str(prop.get("name")).strip()
                    val = str(prop.get("value")).strip()
                    features_dict[key] = val
            
            if features_dict:
                loader.add_value("attributes", features_dict)
                self.logger.info(f"JSON-LD'den özellikler bulundu: {len(features_dict)} adet")
                    
    # JSON-LD verisi yoksa veya eksikse, HTML üzerinden çekmeye çalışırız. Bu genellikle daha karmaşık ve düzensiz olabilir, bu yüzden öncelikli olarak JSON-LD'yi tercih ederiz.
    def _load_from_html(self, loader, response):
        self.logger.warning(f"JSON-LD eksik, CSS Fallback devrede: {loader.context['response'].url}")
        
        # title ---
        title_selectors = self.SELECTORS.get("title")
        title_found = False
        if isinstance(title_selectors, list):
            for selector in title_selectors:
                # XPath ile tüm text node'ları al
                if '::text' not in selector:
                    title_texts = response.css(selector + ' ::text').getall()
                else:
                    title_texts = response.css(selector).getall()
                
                if title_texts:
                    # Tüm text'leri birleştir ve temizle
                    full_title = ' '.join([t.strip() for t in title_texts if t.strip()])
                    # Tırnakları temizle
                    full_title = full_title.replace('"', '').replace("'", "").strip()
                    if full_title:
                        loader.add_value("title", full_title)
                        self.logger.info(f"Title bulundu: {selector} -> {full_title[:50]}...")
                        break
                    
        if not title_found:
            loader.add_value("title", "-1")
            self.logger.warning("Title bulunamadı, varsayılan -1 atandı.")              
        
        # PRICE
        price_selectors = self.SELECTORS.get("price")
        price_found = False
        if isinstance(price_selectors, list):
            for selector in price_selectors:
                price_values = response.css(selector).getall()
                if price_values:
                    loader.add_value("price", price_values)
                    self.logger.info(f"Price bulundu: {selector}")
                    break
        else:
            loader.add_css("price", price_selectors)
            if loader.get_output_value("price"):
                price_found = True
                
        if not price_found:
            loader.add_value("price", "-1")
            self.logger.warning(f"Fiyat bulunamadı, varsayılan -1 atandı: {response.url}")
        
        
        # EVALUATION
        if not loader.get_output_value("evaluation"):
            rating_match = re.search(r'"averageRating"\s*:\s*([\d.]+)', response.text) or \
                           re.search(r'"ratingValue"\s*:\s*"?([\d.]+)"?', response.text)
            
            if rating_match:
                loader.add_value("evaluation", rating_match.group(1))
                self.logger.info(f"Regex ile Puan bulundu: {rating_match.group(1)}")
            else:
                loader.add_value("evaluation", "-1")
                
        # --- DEĞERLENDİRME SAYISI (EVALUATION_LEN) - REGEX ---
        if not loader.get_output_value("evaluation_len"):
            count_match = re.search(r'"totalRatingCount"\s*:\s*(\d+)', response.text) or \
                          re.search(r'"ratingCount"\s*:\s*"?(\d+)"?', response.text) or \
                          re.search(r'"reviewCount"\s*:\s*"?(\d+)"?', response.text)
            
            if count_match:
                loader.add_value("evaluation_len", count_match.group(1))
                self.logger.info(f"Regex ile Değerlendirme Sayısı bulundu: {count_match.group(1)}")
            else:
                loader.add_value("evaluation_len", "-1")
        
        # --- IMAGES ---
        images_selectors = self.SELECTORS.get("images")
        images_found = False

        if isinstance(images_selectors, list):
            for selector in images_selectors:
                # getall() ile galerideki tüm resim linklerini topluyoruz
                img_values = response.css(selector).getall()
                if img_values:
                    # Boş olmayan ve geçerli linkleri temizleyerek alıyoruz
                    clean_imgs = [img.strip() for img in img_values if img.strip()]
                    if clean_imgs:
                        loader.add_value("images", clean_imgs)
                        self.logger.info(f"Images bulundu: {selector} ({len(clean_imgs)} adet)")
                        images_found = True
                        break
        else:
            # Tek bir selector tanımlıysa direkt ekle
            loader.add_css("images", images_selectors)
            if loader.get_output_value("images"):
                images_found = True

        # ---Hiç görsel bulunamazsa -1 ata ---
        if not images_found:
            loader.add_value("images", "-1")
            self.logger.warning(f"Görsel hiçbir selector ile bulunamadı: {response.url}")
            
        # --- EXPLANATION ---
        explanation_selectors = self.SELECTORS.get("explanation")
        explanation_found = False
        
        if isinstance(explanation_selectors, list):
            for selector in explanation_selectors:
                expl_values = response.css(selector).getall()
                if expl_values:
                    clean_expl = ' '.join([text.strip() for text in expl_values if text.strip()])
                    if clean_expl:
                        loader.add_value("explanation", clean_expl)
                        self.logger.info(f"Explanation bulundu: {selector}")
                        explanation_found = True
                        break

        if not explanation_found:
            loader.add_value("explanation", "-1")
            self.logger.info("Explanation bulunamadı veya boş geldi, -1 atandı.")
            
        # --- ATTRIBUTES (DİNAMİK ÜRÜN ÖZELLİKLERİ) ---
        if not loader.get_output_value("attributes"):
            features_dict = {}
            
            # DOM'daki her bir özellik satırını (attribute-item) buluyoruz
            attribute_blocks = response.css("div.attributes div.attribute-item")
            
            # Her bir satırın içine girip name ve value değerlerini çekiyoruz
            for block in attribute_blocks:
                key = block.css("div.name::text").get()
                val = block.css("div.value::text").get()
                
                # İkisi de boş değilse sözlüğümüze (dictionary) ekliyoruz
                if key and val:
                    features_dict[key.strip()] = val.strip()
                    
            # Sözlük dolduysa item'a ekle, boşsa -1 veya uyarı ata
            if features_dict:
                loader.add_value("attributes", features_dict)
                self.logger.info(f"Dinamik özellikler bulundu: {len(features_dict)} adet")
            else:
                loader.add_value("attributes", {"Bilgi": "-1"})
                self.logger.warning("Özellik tablosu bulunamadı veya boş.")
         
    def handle_error(self, failure):
        self.logger.error(f"Istek basarisiz oldu! URL: {failure.request.url}")
        self.logger.error(f"Hata detayi: {repr(failure)}")
    
    def closed(self, reason):
        duration = time.time() - self.start_time
        self.logger.info("-" * 50)
        self.logger.info(f"FINAL RAPORU")
        self.logger.info(f"Sure: {duration:.2f} saniye ({duration/60:.2f} dakika)")
        self.logger.info(f"Toplam Urun: {self.scraped_count}")
        if duration > 0:
            self.logger.info(f"Hiz: {self.scraped_count / (duration/60):.2f} urun/dakika")
        self.logger.info(f"Kapanis Sebebi: {reason}")
        self.logger.info("-" * 50)