import scrapy
from ..items import HaberItem


class ProductSpider(scrapy.Spider):
    name = "product"
    allowed_domains = ["hurriyet.com.tr"]
    start_urls = ["https://www.hurriyet.com.tr/gundem/"]

    def parse(self, response):
        container = response.css('div#content')
        
        items_div_tags = container.css('a.category__list__item--cover')
        
        if not items_div_tags:
            self.logger.warning("Bu sayfada hiç haber bulunamadı.")
            
            return
        
       
        for a_tag in items_div_tags:
            product_url = response.urljoin(a_tag.attrib.get('href'))
            yield scrapy.Request(product_url, callback=self.parse_items)
            
       
        
        try:
            if "?p=" in response.url:
                current_page_str = response.url.split("?p=")[1]
                current_page = int(current_page_str)
                next_page = current_page + 1
            else:
                next_page = 2

            next_page_url = f"https://www.hurriyet.com.tr/gundem/?p={next_page}"
            
            self.logger.info(f"-----------------> SIRADAKİ SAYFAYA GEÇİLİYOR: Sayfa {next_page}")
            yield scrapy.Request(next_page_url, callback=self.parse)
            
        except Exception as e:
            self.logger.error(f"Sayfalama hesaplanırken hata oluştu: {e}")
                
    def parse_items(self, response):
       
        if "/galeri-" in response.url:
            self.logger.info(f"Galeri sayfası atlanıyor: {response.url}")
            return
        
        haberItem = HaberItem()
        
        
        bc = response.css('div.container a.breadcrumb__link::text').getall()
        haberItem['news_type'] = bc[1].strip() if len(bc) > 1 else ""
        
        name = response.css('h1.news-detail-title::text').get()
        haberItem['name'] = name.strip() if name else ""
        
        date_list = response.css('span.news-date::text').get()
        if date_list:
            haberItem['history'] = " ".join(date_list.split()[2:])
        else:
            haberItem['history'] = ""
        
        haberItem['tag'] = [tag.strip() for tag in response.css('div.container div.col-md-17 a.news-tags__link::text').getall()]
        
        haberItem['img_url'] = response.css('div.news-media img::attr(src)').get()
        
        haberItem['news_text'] = [tt.strip() for tt in response.css('div.news-content p::text').getall()]
        
        haberItem['product_url'] = response.url
        yield haberItem
