import scrapy
import pymongo
import json
import re
from scrapy.loader import ItemLoader
from ..items import TrendyolBotItem
from .selector import SELECTORS

class FiyatGuncelleSpider(scrapy.Spider):
    name = "fiyat_guncelle"
    
    REGEX_RATING_AVG = re.compile(r'"averageRating"\s*:\s*([\d.]+)')
    REGEX_RATING_VAL = re.compile(r'"ratingValue"\s*:\s*"?([\d.]+)"?')
    REGEX_RATING_COUNT_1 = re.compile(r'"totalRatingCount"\s*:\s*(\d+)')
    REGEX_RATING_COUNT_2 = re.compile(r'"ratingCount"\s*:\s*"?(\d+)"?')
    REGEX_RATING_COUNT_3 = re.compile(r'"reviewCount"\s*:\s*"?(\d+)"?')

    def _headers(self):
        return {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
            "Accept-Language": "tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7",
            "Cache-Control": "max-age=0",
            "Sec-Ch-Ua": '"Chromium";v="122", "Not(A:Brand";v="24", "Google Chrome";v="122"',
            "Sec-Ch-Ua-Mobile": "?0",
            "Sec-Ch-Ua-Platform": '"Windows"',
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
            "Upgrade-Insecure-Requests": "1"
        }

    def start_requests(self):
        # 1. MongoDB'ye güvenli bağlantı (try...finally ile)
        client = pymongo.MongoClient("mongodb://localhost:27017/")
        try:
            db = client["neuranovav_db"]
            # Sadece URL'leri çekiyoruz
            cursor = db.products.find({}, {"url": 1})
            urls = [doc["url"] for doc in cursor if "url" in doc]
        finally:
            # Spider aniden çökse bile bağlantı kesinlikle kapanacak
            client.close()
        
        self.logger.info(f"🚀 FİYAT GÜNCELLEME BAŞLIYOR: MongoDB'den {len(urls)} adet kayıtlı ürün çekildi.")
        
        # 2. Nokta atışı ürün linklerine istek atıyoruz
        for url in urls:
            yield scrapy.Request(
                url=url,
                headers=self._headers(),
                callback=self.parse_price,
                dont_filter=True  # DB'de zaten unique index olduğu için duplicate gelmeyecek, dont_filter güvenli.
            )

    def parse_price(self, response):
        loader = ItemLoader(item=TrendyolBotItem(), response=response)
        loader.add_value("url", response.url)
        
        # --- JSON-LD HIZLI TARAMA ---
        json_data = None
        scripts = response.xpath('//script[@type="application/ld+json"]/text()').getall()
        for script in scripts:
            try:
                data = json.loads(script)
                if isinstance(data, list): data = data[0]
                if isinstance(data, dict) and data.get('@type') == 'Product':
                    json_data = data
                    break
            except:
                continue

        if json_data:
            offers = json_data.get("offers", {})
            if isinstance(offers, dict) and offers.get("price"):
                loader.add_value("price", str(offers.get("price")))
            
            agg_rating = json_data.get("aggregateRating", {})
            if isinstance(agg_rating, dict):
                if agg_rating.get("ratingValue"): loader.add_value("evaluation", str(agg_rating.get("ratingValue")))
                if agg_rating.get("ratingCount"): loader.add_value("evaluation_len", str(agg_rating.get("ratingCount")))
        
        # --- JSON'DA YOKSA HTML'DEN AL (FALLBACK) ---
        if not loader.get_collected_values("price"):
            price_selectors = SELECTORS.get("price")
            if isinstance(price_selectors, list):
                for selector in price_selectors:
                    price_values = response.css(selector).getall()
                    if price_values:
                        loader.add_value("price", price_values)
                        break
            else:
                loader.add_css("price", price_selectors)

        if not loader.get_collected_values("evaluation"):
            eval_match = self.REGEX_RATING_AVG.search(response.text) or self.REGEX_RATING_VAL.search(response.text)
            if eval_match: loader.add_value("evaluation", eval_match.group(1))

            count_match = self.REGEX_RATING_COUNT_1.search(response.text) or \
                          self.REGEX_RATING_COUNT_2.search(response.text) or \
                          self.REGEX_RATING_COUNT_3.search(response.text)
            if count_match: loader.add_value("evaluation_len", count_match.group(1))

        # Dikkat: Title, Category veya Images bilerek çekilmiyor! 
        # Böylece veri boyutunu küçük tutuyor ve hızı maksimize ediyoruz.
        yield loader.load_item()