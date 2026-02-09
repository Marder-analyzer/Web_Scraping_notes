import scrapy
from ..items import EnsonhaberBotItem
from scrapy_playwright.page import PageMethod

class HaberlerSpider(scrapy.Spider):
    name = "haberler"
    allowed_domains = ["ensonhaber.com"]

    def start_requests(self):
        yield scrapy.Request(
            url="https://www.ensonhaber.com/magazin",
            meta={
                "playwright": True,
                "playwright_page_methods": [
                    # 1. Sayfanın altına kaydır (Butonun yüklenmesi için)
                    PageMethod("evaluate", "window.scrollTo(0, document.body.scrollHeight)"),
                    # 2. 'Daha Fazla Yükle' butonuna tıkla hatalı bura bakılacak
                    PageMethod("click", "#loadMoreBtn"),
                    # 3. Yeni haberlerin HTML'e eklenmesi için bekle (2 saniye)
                    PageMethod("wait_for_timeout", 2000),
                ],
            },
            callback=self.parse,
        )
        
    def parse(self, response):
        
        # sayfadaki tüm haberlein ufak kısımlarından içeriğine girecek linklerin hepsini alma gezme
        
        container = response.css('div.container')
        haber_linkleri = container.css('div.row div.news-card a::attr(href)').getall()

        # bu linklerin hepsini döngüde parse_items fonksiyonuna sokuyoruz
        
        for link in haber_linkleri:

            # tam url alma
            tam_link = response.urljoin(link)
            yield scrapy.Request(tam_link, callback=self.parse_items)
    
    def parse_items(self, response):
        
        
        ensonhaberbotitem = EnsonhaberBotItem()
        
        
        # verileri çekiyoruz
        
        # type çekelim
        two_data = response.css('ol.breadcrumb li.breadcrumb-item a::text').getall()
        ensonhaberbotitem['news_type'] = two_data[1].strip() if len(two_data) > 1 else ""
        
        # ana başlığı çekme
        ensonhaberbotitem['name'] = response.css('div.news-header h1::text').get()
        
        # alt başlıgı çekme
        ensonhaberbotitem['subheading'] = response.css('div.news-header h2::text').get()
        
        # şimdi haber kaynağının adını alalım
        ensonhaberbotitem['data_owner'] = response.xpath('//div[contains(@class, "source")]/text()[normalize-space()]').get().strip()
 
        # haber kaynağı logosu url 
        ensonhaberbotitem['data_owner_img_url'] = response.css('div.content-meta div.source span.icon img::attr(src)').get()
        
        # yayınlanma tarihini alalım
        ensonhaberbotitem['history'] = response.css('div.content-meta div.date span.published span::text').get()
        
        # en üsteki ana fotoğrafı çekelim
        ensonhaberbotitem['main_img_url'] = response.css('div.content div.main-image img::attr(src)').get()
       
        # diğer alt görselleri çekelim
        ensonhaberbotitem['sub_img_url'] = [sub.strip() for sub in response.css('div.news-body div.content p img::attr(src)').getall()]
       
        # metinleri çekelim
        ensonhaberbotitem['news_text'] = [p.xpath('string(.)').get().strip() for p in response.css('div[property="articleBody"] p.text')s]
        
        # haberin çektiğimiz verinin linkini alalım her biri için
        ensonhaberbotitem['product_url'] = response.url
        
        # hangi siteden çektiğimzi kaydedelim
        ensonhaberbotitem['product_source'] = 'EnSonHaber'
        
        yield ensonhaberbotitem
        