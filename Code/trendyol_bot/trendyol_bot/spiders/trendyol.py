import scrapy
from scrapy_playwright.page import PageMethod
import time

class TrendyolSpider(scrapy.Spider):
    name = "trendyol"
    allowed_domains = ["trendyol.com"]
    start_urls = ["https://trendyol.com"]

    def __init__(self, name = None, **kwargs):
        super(TrendyolSpider,self).__init__(name, **kwargs)
        # çekilen link sayısını ve süreyi takip etmek için değişkenler
        self.start_time = time.time()
        self.scraped_count = 0
    
    #categorileri ayarlama birden fazla çekicez her biri için
    categories = [
        "elbise-x-c56"
        #ve diğer kategoriler eklenebilir
    ]
    
    #scroll işlemi için JavaScript kodu. Bu kod, sayfanın sonuna kadar kaydırır ve yeni ürünlerin yüklenmesini sağlar. Limit parametresi, kaç kez kaydırma yapılacağını belirler.
    # trendyolun yapısı gereği bekleme ve scrol en alt değil belli px eksiği aşağıya kaydırıyoruz
    
    load_more_script = """
    async (limit = 20) => {
        let lastHeight = document.body.scrollHeight;
        let count = 0;
        
        while (count < limit) {
            
            window.scrollTo(0, document.body.scrollHeight - 1000);
            await new Promise(r => setTimeout(r, 2000)); // Yüklenmesi için bekle
            
            let newHeight = document.body.scrollHeight;
            
            if (newHeight === lastHeight) break;
            
            lastHeight = newHeight;
            count++;
        }
        return true;
    }
    """
    
    #linkleri çekmek için ilk ayarlamaları yapacağız. JavaScript ile çalışan bir site olduğu için Playwright kullanarak sayfanın tam olarak yüklenmesini sağlayacağız.
    def start_requests(self):
        self.logger.info("--- Trendyol SPIDER BAŞLADI ---")
        # her kategori için ayrı ayrı istek atacağız
        for category in self.categories:
            url = f"https://www.trendyol.com/{category}"
            yield scrapy.Request(
                url=url,
                meta={
                    "playwright": True,
                    "playwright_include_page": True,
                    "playwright_page_methods": [
                        # 1. Sayfa yüklendiğinde çerezleri reddet/kabul et bence gerekli
                        PageMethod("click", "button#onetrust-accept-btn-handler", timeout=5000),
                        # 2. Akıllı scroll scriptini çalıştır (limit = load_more_script içinde belirlendi)
                        PageMethod("evaluate", self.load_more_script),
                        # 3. bekleme süresi önemli en altta gittiğinde yıkalıyamassa sonsuz döngüye girer veride gelmez
                        PageMethod("wait_for_timeout", 2000),
                    ],
                },
                callback=self.parse,
                dont_filter=True 
            )
        
        

    # bütün linkleri çekme işlemi ve dağıtma işlemini yaptığımız yer.
    def parse(self, response):
        self.logger.info(f"Kategori sayfasında Link çekme işlemi başladı: {response.url}")
        # Burada 'product-card' linklerini toplayacağız
        # Yani her ürünün detay sayfasına giden linkler
        links = response.css("a.product-card::attr(href)").getall()
        
        self.logger.info(f"Kategori sayfasında {len(links)} adet link bulundu.")
        
        for link in links:
            full_url = response.urljoin(link)
            # Her bir ürün linkine gidiyoruz
            yield scrapy.Request(
                url=full_url,
                callback=self.parse_items,
                meta={"playwright": False} # Detay sayfasına giderken tarayıcı gereksiz işlem yükü
            
            
    # linke gittiğimizde ürünlerin verilerini çektiğimiz yer
    def parse_items(self, response):
    
    # spiderin kapanışında toplam çekilen link sayısını ve süreyi loglamak için kullanacağız.  
    def closed(self, reason):
        