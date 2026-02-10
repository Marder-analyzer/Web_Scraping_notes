import scrapy
import time
from ..items import EnsonhaberBotItem
from scrapy_playwright.page import PageMethod

class HaberlerSpider(scrapy.Spider):
    name = "haberler"
    allowed_domains = ["ensonhaber.com"]

    def __init__(self, *args, **kwargs):
        super(HaberlerSpider, self).__init__(*args, **kwargs)
        self.start_time = time.time()
        self.prep_start_time = 0
        self.scraping_start_time = 0
        self.scraped_count = 0

    def start_requests(self):
        # JavaScript döngüsü: Butona basar ve DOM'un güncellenmesini bekler
        self.prep_start_time = time.time()
        self.logger.info("--- EnsonHaberGundem SPIDER BAŞLADI ---")
        
        load_more_script = """
        (async () => {
            const limit = 10; // Test için 10, sonra 30 yapabilirsin
            for (let i = 0; i < limit; i++) {
                window.scrollTo(0, document.body.scrollHeight);
                await new Promise(r => setTimeout(r, 2000));
                
                const btn = document.querySelector('.btn-read-more') || document.querySelector('#loadMoreBtn');
                if (btn && btn.offsetParent !== null) {
                    btn.click();
                    await new Promise(r => setTimeout(r, 3000));
                } else {
                    break;
                }
            }
            return true;
        })()
        """

        yield scrapy.Request(
            url="https://www.ensonhaber.com/teknoloji",
            meta={
                "playwright": True,
                "playwright_page_methods": [
                    PageMethod("evaluate", load_more_script),
                    PageMethod("wait_for_timeout", 3000),
                ],
            },
            callback=self.parse,
            dont_filter=True 
        )
        

        
    def parse(self, response):
        self.scraping_start_time = time.time()
        prep_duration = self.scraping_start_time - self.prep_start_time

        self.logger.info(f"haber linkileri için çekme işlemi başladı")
        
        links = response.css('a[href*="/teknoloji/"]::attr(href)').getall()
        unique_links = set()
        
        self.logger.info(f"JavaScript ile hazırlık süresi: {prep_duration:.2f} saniye")
        
        
        for link in links:
            full_url = response.urljoin(link)
            # Kategori sayfasının kendisini ve hatalı yapıları filtrele
            if "/teknoloji/" in full_url and not full_url.endswith("/teknoloji"):
                # Sosyal medya paylaşım linklerini veya reklamları elemek için kısa kontrol
                if not any(x in full_url for x in ['facebook.com', 'twitter.com', 'whatsapp:']):
                    unique_links.add(full_url)

        self.logger.info(f"Toplam {len(unique_links)} adet benzersiz haber linki radara takıldı!")

        for link in unique_links:
            yield scrapy.Request(link, callback=self.parse_items, meta={"playwright": False})
            
    
    def parse_items(self, response):
        
        self.scraped_count += 1
        ensonhaberbotitem = EnsonhaberBotItem()
        
        
        # verileri çekiyoruz
        
        # type çekelim
        two_data = response.css('ol.breadcrumb li.breadcrumb-item a::text').getall()
        ensonhaberbotitem['news_type'] = two_data[1].strip() if len(two_data) > 1 else ""
        
        # ana başlığı çekme
        ensonhaberbotitem['name'] = response.css('div.news-header h1::text').get()
        
        self.logger.info(f"[{self.scraped_count}] İşleniyor: {ensonhaberbotitem['name'][:50]}...")
        
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
        ensonhaberbotitem['news_text'] = [p.xpath('string(.)').get().strip() for p in response.css('div[property="articleBody"] p.text')]
        
        # haberin çektiğimiz verinin linkini alalım her biri için
        ensonhaberbotitem['product_url'] = response.url
        
        # hangi siteden çektiğimzi kaydedelim
        ensonhaberbotitem['product_source'] = 'EnSonHaber'
        
        yield ensonhaberbotitem
        
        
    def closed(self, reason):
        total_duration = time.time() - self.start_time
        self.logger.info("--- SPIDER KAPATILDI ---")
        self.logger.info(f"Toplam İşlem Süresi: {total_duration:.2f} saniye.")
        self.logger.info(f"Toplam Çekilen Haber: {self.scraped_count}")
        self.logger.info(f"Ortalama Haber Başına Hız: {total_duration/max(1, self.scraped_count):.2f} saniye.")