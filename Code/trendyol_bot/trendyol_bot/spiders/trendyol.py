import scrapy
from scrapy_playwright.page import PageMethod
import time

class TrendyolSpider(scrapy.Spider):
    name = "trendyol"
    allowed_domains = ["trendyol.com"]
    start_urls = ["https://trendyol.com"]

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
        # async ile sürekli işlem yapıalcak
        
        # while veya for dongüsü yapabiliriz
        
        # scrol en aşağıya değil biraz üstüne kadar yapacağız en altta yazılar var ve oraya kadar scroll yaparsak o yazılar gelmez. O yüzden biraz üstüne kadar scroll yapacağız.
        
        #buton olmadı için scrolla yüklendiği için break yapsısı kurulmalı
        
        

    # bütün linkleri çekme işlemi ve dağıtma işlemini yaptığımız yer.
    def parse(self, response):
        
    # linke gittiğimizde ürünlerin verilerini çektiğimiz yer
    def parse_items(self, response):
    
    # spiderin kapanışında toplam çekilen link sayısını ve süreyi loglamak için kullanacağız.  
    def closed(self, reason):
        