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
    base_categories = [
        
        # --- Kadın ---
        
        # --- Kadın Giyim ---
        "sr?wc=82&wg=1", # ana kadın giyim kategorisi
        "sr?wc=56", # kadın giyim elbise
        "sr?wc=73&wg=1", # kadın giyim tişört
        "sr?wc=75&wg=1", # kadın giyim gömlek
        "sr?wc=120&wg=1", # kadın giyim kot pantolon
        "sr?wc=1030", # kadın giyim kot ceket
        "sr?wc=70&wg=1", # kadın giyim pantolon
        "sr?wc=118&wg=1", # kadın giyim mont
        "sr?wc=1019&wg=1", # kadın giyim bluz
        "sr?wc=1030&wg=1", # kadın giyim ceket
        "sr?wc=69", # kadın giyim etek
        "sr?wc=1092&wg=1", # kadın giyim kazak
        "sr?wc=81&wg=1", # kadın giyim tesettür
        "sr?wc=80&wg=1", # kadın giyim büyük beden
        "sr?wc=79&wg=1", # kadın giyim trençkot
        "sr?wg=1&wc=1205", # kadın giyim yağmurluk
        "sr?wc=1179&wg=1", # kadın giyim sweatshirt
        "sr?wc=1075&wg=1", # kadın giyim kaban
        "sr?wc=1066&wg=1", # kadın giyim hırka
        "sr?wc=1130&wg=1", # kadın giyim palto
        
        # --- Kadın Ayakkabı ---
        "sr?wc=114&wg=1", # ana ayakkabı kategorisi
        "sr?wc=1172&wg=1", # kadın ayakkabı sneaker
        "sr?wc=1352&wg=1", # kadın ayakkabı günlük
        "sr?wc=111&wg=1", # kadın ayakkabı sandalet
        "sr?wc=1025&wg=1", # kadın ayakkabı bot
        "sr?wc=1037&wg=1", # kadın ayakkabı çizme
        "sr?wc=142587&wg=1", # kadın ayakkabı kar botu
        "sr?wc=1108&wg=1", # kadın ayakkabı loafer
        
      
        # --- kadın aksesuar ---
        
        "sr?wc=27&wg=1", # kadın aksesuar ana kategorisi
        "sr?wg=1&wc=34", # kadın aksesuar saat
        "sr?wc=1032&wg=1", # kadın aksesuar cüzdan
        "sr?wc=1003&wg=1", # kadın aksesuar atkı
        "sr?wc=1015&wg=1", # kadın aksesuar bere
        "sr?wg=1&wc=1046", # kadın aksesuar eldiven
        "sr?wc=31&wg=1", # kadın aksesuar şal
        
        # --- kadın ev&iç giyim ---
        
        "sr?wc=64&wg=1", # kadın iç giyim ana kategorisi
        "sr?wg=1&wc=101496", # kadın iç giyim pijama takımı
        "sr?wc=62&wg=1", # kadın iç giyim gecelik
        "sr?wc=63&wg=1", # kadın iç giyim sütyen
        "sr?wc=104536&wg=1", # kadın iç giyim iç giyim çamaşarı takımı
        "sr?wc=109067&wg=1", # kadın iç giyim fantazy buna bakılacak ekstra onaylamak lazım
        "sr?wc=1038&wg=1", # kadın iç giyim çorap
        "sr?wc=1100", # kadın iç giyim korse
        "sr?wc=1105", # kadın iç giyim kilot
        "sr?wc=74&wg=1", # kadın iç giyim bustiyer
        "sr?wc=1004&wg=1", # kadın iç giyim atlet body
        "sr?wc=1099&wg=1", # kadın iç giyim  kombinezon
        "sr?wc=60", # kadın iç giyim jartiyer bunada bakılacak görseller problem
        
        # --- kadın kozmetik ---
        
        "sr?wc=89", # kadın kozmetik ana kategorisi
        "sr?wc=86", # kadın kozmetik parfüm
        "sr?wc=1347", # kadın kozmetik göz makyajı
        "sr?wc=100", # kadın kozmetik makyaj
        "sr?wc=101396", # kadın kozmetik ağız bakımı
        "sr?wc=1204", # kadın kozmetik vücut bakımı
        "sr?wc=101409", # kadın kozmetik hijyenik ped
        "sr?wc=1156", # kadın kozmetik ruj
        "sr?wc=1050", # kadın kozmetik eyeliner
        "sr?wc=1348", # kadın kozmetik ten makyajı
        "sr?wc=101394", # kadın kozmetik manikür pedükür
        "sr?wc=1122", # kadın kozmetik yüz nemlendirici
        
        # --- kadın spor/outdoor ---
        
        "sr?wc=104593&wg=1", # kadın spor ana kategorisi
        "sr?wg=1&wc=101456", # kadın spor sweatshirt
        "sr?wg=1&wc=101459", # kadın spor tişört
        "sr?wc=1358&wg=1", # kadın spor spor sütyen
        "sr?wc=101460&wg=1", # kadın spor tayt
        "sr?wc=1049&wg=1", # kadın spor eşofman
        "sr?wc=109&wg=1", # kadın spor koşu ayakkabısı
        "sr?wc=1174", # kadın spor spor çanta
        "sr?wg=1&wc=1128", # kadın spor outdoor ayyakabı
        "sr?wc=104230", # kadın spor outdoor ekipmanlar 
        "sr?wc=104521&wg=1", # kadın spor sporcu aksesuarları
        "sr?wc=145855", # kadın spor kayak malzemeleri
        "sr?wc=104256", # kadın spor uyku tulumu
        "sr?wc=109295", # kadın spor mat
        "sr?wc=104251", # kadın spor dağcılık
        "sr?wc=101450&wg=1", # kadın spor spor ceket
        
        # --- erkek ---
        
        # --- erkek giyim ---
        "sr?wc=82&wg=2", # ana erkek giyim kategorisi
        "sr?wc=73&wg=2", # erkek giyim tişört
        "sr?wc=119&wg=2", # erkek giyim şort
        "sr?wc=75&wg=2", # erkek giyim gömlek
        "sr?wc=1049&wg=2", # erkek giyim eşofman
        "sr?wc=70&wg=2", # erkek giyim pantolon
        "sr?wc=1030&wg=2", # erkek giyim ceket
        "sr?wg=2&wc=120", # erkek giyim kot pantolon
        "sr?wc=1207&wg=2", # erkek giyim yelek
        "sr?wc=1092&wg=2", # erkek giyim kazak
        "sr?wc=118&wg=2", # erkek giyim mont
        "sr?wc=78&wg=2", # erkek giyim takım elbise  
        "sr?wc=1179&wg=2", # erkek giyim sweatshirt
        "sr?wc=1075&wg=2", # erkek giyim kaban
        "sr?wc=1066&wg=2", # erkek giyim hırka
        "sr?wc=79&wg=2", # erkek giyim trençkot
        "sr?wc=1130&wg=2", # erkek giyim palto
        "sr?wc=150566&wg=2", # erkek giyim blazer
        "sr?wc=1149&wg=2", # erkek giyim polar
        
        
        # --- erkek ayakkabı ---
        
        "sr?wc=114&wg=2", # ana erkek ayakkabı kategorisi
        "sr?wc=109&wg=2", # erkek ayakkabı spor ayyakabı
        "sr?wc=1352&wg=2", # erkek ayakkabı günlük ayyakabı
        "sr?wc=101429&wg=2", # erkek ayakkabı yürüyüş ayakkabısı
        "sr?wc=1172&wg=2", # erkek ayakkabı sneaker
        "sr?wc=101421&wg=2", # erkek ayakkabı klasik ayakkabı
        "sr?wg=2&wc=1025", # erkek ayakkabı bot
        "sr?wg=2&wc=142587", # erkek ayakkabı kar botu
        "sr?wc=1108&wg=2", # erkek ayakkabı loafer
        "sr?wc=101426&wg=2", # erkek ayakkabı koşu ayakkabısı
        "sr?wg=2&wc=1037", # erkek ayakkabı çizme
        
        
        # --- erkek çanta ---
        
        "sr?wc=117&wg=2", # ana erkek çanta kategorisi
        "sr?wc=1174&wg=2", # erkek çanta spor çanta
        "sr?wg=2&wc=1202", # erkek çanta valiz bavul
        "sr?wc=1152&wg=2", # erkek çanta postacı
        
        
        # --- erkek kişisel bakım  ---
        
        "sr?wc=89&wg=2", # erkek kişisel bakım ana kategorisi
        "sr?wc=86&wg=2", # erkek kişisel bakım parfüm
        "sr?wc=101404", # erkek kişisel bakım tıraş bıçarğı
        "sr?wc=1040&wg=2", # erkek kişisel bakım deodorant
        
        
        # --- erkek büyük beden ---
        
        "sr?wc=80&wg=2", # erkek büyük beden ana kategorisi
        "sr?wc=108857&wg=2", # erkek büyük beden sweatshirt
        "sr?wg=2&wc=102777", # erkek büyük beden tişört
        "sr?wc=108855&wg=2", # erkek büyük beden gömlek
        "sr?wc=102779&wg=2", # erkek büyük beden pantolon
        "sr?wc=108864&wg=2", # erkek büyük beden mont
        "sr?wc=108866&wg=2", # erkek büyük beden kazak
        "sr?wc=108865&wg=2", # erkek büyük beden hırka
        "sr?wg=2&wc=108863", # erkek büyük beden kaban
        "sr?wc=108862&wg=2", # erkek büyük beden eşofman altı
        
        
        # --- erkek saat/aksesuar ---
        
        "sr?wc=27&wg=2", # erkek aksesuar ana kategorisi
        "sr?wg=2&wc=105", # erkek aksesuar güneş gözlük
        "sr?wg=2&wc=1032", # erkek aksesuar cüzdan
        "sr?wg=2&wc=1093", # erkek aksesuar kemer
        "sr?wc=1353&wg=2", # erkek aksesuar kartlık
        "sr?wc=1101", # erkek aksesuar kravat
        "sr?wc=1026&wg=2", # erkek aksesuar boyunluk
        "sr?wg=2&wc=1003", # erkek aksesuar atkı
        "sr?wc=1015&wg=2", # erkek aksesuar bere  
        "sr?wg=2&wc=1046", # erkek aksesuar eldiven

        
        # --- erkek iç giyim ---
        
        "sr?wc=64&wg=2", # erkek iç giyim ana kategorisi
        "sr?wc=61&wg=2", # erkek iç giyim boxer
        "sr?wc=1143&wg=2", # erkek iç giyim pijama takımı
        "sr?wc=1004&wg=2", # erkek iç giyim atlet 
        "sr?wc=103713&wg=2", # erkek iç giyim içlik
        
        # --- erkek spor/outdoor ---
        
        "sr?wc=104593&wg=2", # erkek spor ana kategorisi
        "sr?wc=101459&wg=2", # erkek spor tişört
        "sr?wc=101456&wg=2", # erkek spor sweatshirt
        "sr?wc=1054", # erkek spor forma
        "sr?wc=109035&wg=2", # erkek spor spor çorap
        "sr?wc=101447&wg=2", # erkek spor spor giyim
        "sr?wc=1128&wg=2", # erkek spor outdoor ayyakabı
        "sr?wc=104533", # erkek spor scooter
        "sr?wc=104580", # erkek spor bisiklet
        "sr?wc=104238", # erkek spor dalış malzemeleri
        "sr?wc=1205&wg=2", # erkek spor rüzgarlık

        
        # --- erkek  elektronik ---
        
        "sr?wc=104024", # erkek elektronik ana kategorisi
        "sr?wc=103108", # erkek elektronik laptop
        "sr?wc=104044", # erkek elektronik oyun konsollar
        "sr?wc=110349", # erkek elektronik elektrikli bisiklet
        "sr?wc=108626", # erkek elektronik blutut kulaklık
        "sr?wc=106090", # erkek elektronik gaming pc
        "sr?wc=106333", # erkek elektronik oyuncu koltuğu
        "sr?wc=108931", # erkek elektronik drone
        
        
        # --- anne/bebek ---
        # --- anne/bebek bebek ---
        "sr?wc=104158", # anne/bebek bebek ana kategorisi
        "sr?wc=104159", # anne/bebek bebek hastane çıkışı
        "sr?wc=104566", # anne/bebek bebek body zıbın
        "sr?wc=73&wg=3&gag=2-1%2C1-1", # anne/bebek bebek tişört
        "sr?wc=1066&wg=3", # anne/bebek bebek hırka
        "sr?wc=105581", # anne/bebek bebek battaniye
        "sr?wc=103727", # anne/bebek bebek alt üst takım 
        "sr?wc=1015&wg=3", # anne/bebek bebek bere
        
        # --- anne/bebek kız çocuk ---
        "sr?wc=82&wg=3&gag=1-2", # anne/bebek kız çocuk ana kategorisi
        "sr?wc=56&wg=3", # anne/bebek kız çocuk elbise
        "sr?wc=1179&wg=3&gag=1-2", # anne/bebek kız çocuk sweatshirt
        "sr?wc=109&wg=3&gag=1-2", # anne/bebek kız çocuk spor ayakkabı
        "sr?wc=1049&wg=3&gag=1-2", # anne/bebek kız çocuk eşofman
        "sr?wc=64&wg=3&gag=1-2", # anne/bebek kız çocuk iç giyim
        "sr?wc=73&wg=3&gag=1-2", # anne/bebek kız çocuk tişört atlet
        "sr?wc=121&wg=3", # anne/bebek kız çocuk tayt
        "sr?wc=1352&wg=3&gag=1-2", # anne/bebek kız çocuk günlük ayakkabı
        "sr?wc=119&wg=3&gag=1-2", # anne/bebek kız çocuk şort
        "sr?wg=3&wc=118", # anne/bebek kız çocuk mont
        "sr?wc=1075&wg=3", # anne/bebek kız çocuk kaban
        "sr?wc=55&wg=3", # anne/bebek kız çocuk abiye elbise
        "sr?wc=1030&wg=3", # anne/bebek kız çocuk ceket
        "sr?wc=70&wg=3", # anne/bebek kız çocuk pantolon
        "sr?wc=1092&wg=3", # anne/bebek kız çocuk kazak
        "sr?wg=3&wc=1025", # anne/bebek kız çocuk bot
        "sr?wc=101499&wg=3", # anne/bebek kız çocuk şapka bere eldiven
        
        # --- anne/bebek erkek çocuk---
        "sr?wc=82&wg=3&gag=2-2", # anne/bebek erkek çocuk ana kategorisi
        "sr?wc=1179&wg=3&gag=2-2", # anne/bebek erkek çocuk sweatshirt
        "sr?wc=109&wg=3&gag=2-2", # anne/bebek erkek çocuk spor ayakkabı
        "sr?wc=1049&wg=3&gag=2-2", # anne/bebek erkek çocuk eşofman
        "sr?wc=64&wg=3&gag=2-2", # anne/bebek erkek çocuk iç giyim
        "sr?wc=73&wg=3&gag=2-2", # anne/bebek erkek çocuk tişört atlet
        "sr?wc=1352&wg=3&gag=2-2", # anne/bebek erkek çocuk günlük ayakkabı
        "sr?wc=119&wg=3&gag=2-2", # anne/bebek erkek çocuk şort 
        "sr?wg=3&wc=144727", # anne/bebek erkek çocuk krampon

        
        # --- anne/bebek bebek bakımı ---
        "sr?wc=101414", # anne/bebek bebek bakımı ana kategorisi
        "sr?wc=1363", # anne/bebek bebek bakımı bebek bezi
        "sr?wc=105562", # anne/bebek bebek bakımı şampuan
        "sr?wc=105561", # anne/bebek bebek bakımı sabun
        "sr?wc=109104", # anne/bebek bebek bakımı bebek deterjan
        "sr?wc=103769", #  anne/bebek bebek bakımı bebek losyonu
        "sr?wc=101411", # anne/bebek bebek bakımı ıslak mendil
        
        
        # --- anne/bebek oyuncak ---
        "sr?wc=90", # anne/bebek oyuncak ana kategorisi
        "sr?wc=145168", # anne/bebek oyuncak eğitici oyuncak
        "sr?wc=144039", # anne/bebek oyuncak oyuncak araba
        "sr?wc=103711", # anne/bebek oyuncak bebek
        "sr?wc=103692", # anne/bebek oyuncak okul öncesi oyuncak
        "sr?wc=103819", # anne/bebek oyuncak kumandalı oyuncak
        
        
        # --- anne/bebek  taşıma güvenlik ---
        "sr?wc=1355", # anne/bebek taşıma güvenlik ana kategorisi
        "sr?wc=103735", # anne/bebek taşıma güvenlik bebek arabası
        "sr?wc=103731", # anne/bebek taşıma güvenlik ana kucağı
        "sr?wc=103740", # anne/bebek taşıma güvenlik kanguru
        "sr?wc=103741", # anne/bebek taşıma güvenlik yürütceç
        "sr?wc=103738", # anne/bebek taşıma güvenlik oto koltuğu
        "sr?wc=104510", # anne/bebek taşıma güvenlik bebek salıncakları

        
        
        # --- anne/bebek bebek odası---
        "sr?wc=105325", # anne/bebek bebek odası ana kategorisi
        "sr?wc=104511", # anne/bebek bebek odası beşik
        "sr?wc=144368", # anne/bebek bebek odası bebek yatağı
        "sr?wc=105583", # anne/bebek bebek odası bebek nevresimleri
        "sr?wc=105489", # anne/bebek bebek odası bebek cibinlik
        "sr?wc=151225", # anne/bebek bebek odası oyuncak dolabı
        "sr?wc=103710", # anne/bebek bebek odası bebek oyun parkı
        
        # --- ev/mobilya ---
        
        # --- ev/Mobilya sofra mutfak ---
        "sr?wc=1354", # ev/mobilya ana kategorisi
        "sr?wc=1191", # ev/mobilya sofra mutfak TENCERE SETİ
        "sr?wc=1188", # ev/mobilya sofra mutfak TAVA 
        "sr?wc=101506", # ev/mobilya sofra mutfak düdüklü tencere
        "sr?wc=1208", # ev/mobilya sofra mutfak yemkek takımı
        "sr?wc=1078", # ev/mobilya sofra mutfak kahvaltı takımı
        "sr?wc=108047", # ev/mobilya sofra mutfak tabak
        "sr?wc=108824", # ev/mobilya sofra mutfak çatal kaşık bıçak seti
        "sr?wc=1164", # ev/mobilya sofra mutfak  saklama kabı
        "sr?wc=101502", # ev/mobilya sofra mutfak bardak
        "sr?wc=144008", # ev/mobilya sofra mutfak kahve fincanı
        
        
        # --- ev/Mobilya  ev gereçleri---
        "sr?wc=104216", # ev/mobilya ev gereçleri ana kategorisi
        "sr?wc=144364", # ev/mobilya ev gereçleri hurç
        "sr?wc=149629%2C163721%2C163720", # ev/mobilya ev gereçleri düzenleyiciler
        "sr?wc=104217", # ev/mobilya ev gereçleri askı
        "sr?wc=104219", # ev/mobilya ev gereçleri çamaşır sepeti
        "sr?wc=104168", # ev/mobilya ev gereçleri banyo düzenleyici
        "sr?wc=104210", # ev/mobilya ev gereçleri banyo setleri
        "sr?wc=104220", # ev/mobilya ev gereçleri ütü masası ve aksesuarları
        "sr?wc=144182", # ev/mobilya ev gereçleri makyaj takı organizatörü
        
        
        # --- ev/Mobilya aydınlatma ---
        "sr?wc=1365", # ev/mobilya aydınlatma ana kategorisi
        "sr?wc=1366", # ev/mobilya aydınlatma avize
        "sr?wc=103676", # ev/mobilya aydınlatma lambader
        "sr?wc=104130", # ev/mobilya aydınlatma masa gece lambası
        
        
        # --- ev/Mobilya  ev tekstil---
        "sr?wc=94", # ev/mobilya ev tekstil ana kategorisi
        "sr?wc=104444%2C104443%2C1123", # ev/mobilya ev tekstil nevresim takımı
        "sr?wc=1206%2C1211", # ev/mobilya ev tekstil yastık yorgan
        "sr?wc=102773%2C102774%2C998", # ev/mobilya ev tekstil çarşaf alez
        "sr?wc=1013%2C93", #  ev/mobilya ev tekstil yatak örtüsü battaniye
        "sr?wc=1200", # ev/mobilya ev tekstil uyku seti
        "sr?wc=106326", #   ev/mobilya ev tekstil koltuk örtüsü
        "sr?wc=1064%2C1024", # ev/mobilya ev tekstil havlu bornoz
        "sr?wc=109003", # ev/mobilya ev tekstil banyo paspası
        "sr?wc=1063%2C106327%2C101513%2C109118%2C105496", # ev/mobilya ev tekstil halı
        "sr?wc=1141", # ev/mobilya ev tekstil perde
        "sr?wc=109321", # ev/mobilya ev tekstil seccade
        
        # --- ev/Mobilya  ev dekerasyonu ---
        "sr?wc=95", # ev/mobilya ev dekorasyonu ana kategorisi
        "sr?wc=107995", # ev/mobilya ev dekorasyonu ayna
        "sr?wc=1185", # ev/mobilya ev dekorasyonu tablo
        "sr?wc=108963%2C1203", # ev/mobilya ev dekorasyonu dekaratif çiçek
        "sr?wc=104214", # ev/mobilya ev dekorasyonu kırlent
        "sr?wc=35", # ev/mobilya ev dekorasyonu duvaR saati
        "sr?wc=104154%2C105571", # ev/mobilya ev dekorasyonu oda kokusu mum
        
        
        # --- ev/Mobilya  mobilya ---
        "sr?wc=1119", # ev/mobilya mobilya ana kategorisi
        "sr?wc=104448", # ev/mobilya mobilya yatak odası
        "sr?wc=104474", # ev/mobilya mobilya bahçe mobilyası
        "sr?wc=104201", # ev/mobilya mobilya çalışma odası
        "sr?wc=104484", # ev/mobilya mobilya yemek odası
        "sr?wc=104489", # ev/mobilya mobilya oturma grupları
        "sr?wc=105465", # ev/mobilya mobilya genç odası
        "sr?wc=105457", # ev/mobilya mobilya koltuk takımı
        "sr?wc=104507", # ev/mobilya mobilya mutfak dolabı
        "sr?wc=109216", # ev/mobilya mobilya şifonyer
        "sr?wc=105328", # ev/mobilya mobilya dolap
        "sr?wc=108623", # ev/mobilya mobilya gardırop
        "sr?wc=104572", # ev/mobilya mobilya zigon
        
        
        # --- ev/Mobilya hobi ---
        "sr?wc=97", # ev/mobilya hobi ana kategorisi
        "sr?wc=108925", # ev/mobilya hobi hediye sepeti
        
        
        # --- ev/Mobilya otomobil motosiklet---
        "sr?wc=105777", # ev/mobilya otomobil motosiklet ana kategorisi
        "sr?wc=103483", # ev/mobilya otomobil motosiklet oto aksesuarları
        "sr?wc=104103", # ev/mobilya otomobil motosiklet oto paspası
        "sr?wc=103902", # ev/mobilya otomobil motosiklet oto lastik
        "sr?wc=103849", # ev/mobilya otomobil motosiklet kask
        "sr?wc=103868", # ev/mobilya otomobil motosiklet kol dayama kolçak
        "sr?wc=103873", # ev/mobilya otomobil motosiklet araç kokusu
        "sr?wc=103847", # ev/mobilya otomobil motosiklet eldiveni
        "sr?wc=103844", # ev/mobilya otomobil motosiklet botu
        "sr?wc=103833", # ev/mobilya otomobil motosiklet sepeti
        
        
        # --- ev/Mobilya  yapı market---
        "sr?wc=103720", # ev/mobilya yapı market ana kategorisi
        "sr?wc=105718", # ev/mobilya yapı market banyo yapı malzemeleri
        "sr?wc=103723", # ev/mobilya yapı market elektrik el aletleri
        "sr?wc=103725", # ev/mobilya yapı market hırdavat ürünleri 
        "sr?wc=103721", # ev/mobilya yapı market boya 
        "sr?wc=105661", # ev/mobilya yapı market matkap
        "sr?wc=103675", # ev/mobilya yapı market ambul
        "sr?wc=105660", # ev/mobilya yapı market vidalama
        
        # --- süpermarket  ---
        # --- süpermarket ev temizlik  ---
        "sr?wc=105478", # süpermarket ev temizlik ana kategorisi
        "sr?wc=103809", # süpermarket ev temizlik çamaşır yıkama
        "sr?wc=103801", # süpermarket ev temizlik bulaşık yıkama
        "sr?wc=109302", # süpermarket ev temizlik paspas mop
        "sr?wc=108713", # süpermarket ev temizlik çamaşır deterjanı
        "sr?wc=103803", # süpermarket ev temizlik bulaşık deterjanı
        "sr?wc=105571", # süpermarket ev temizlik oda kokusu 
        "sr?wc=104113", # süpermarket ev temizlik banyo temizliyicler
        "sr?wc=103814", # süpermarket ev temizlik yumuşatıcı
        "sr?wc=104188", # süpermarket ev temizlik tuvalet kağıdı
        "sr?wc=104185", # süpermarket ev temizlik kağıt havlu
        "sr?wc=103923", # süpermarket ev temizlik temizlik bezi

        
        # --- süpermarket kişisel bakım ---
        "sr?wc=87", # süpermarket kişisel bakım saç bakım
        "sr?wc=103107", # süpermarket kişisel banyo duş
        "sr?wc=85", # süpermarket kişisel bakım cilt bakım
        "sr?wc=1040", # süpermarket kişisel bakım deodorant
        "sr?wc=105516", # süpermarket kişisel bakım kadın hijyen
        "sr?wc=103106", # süpermarket kişisel bakım traş üürnleri
    
        # --- süpermarket  bebek bakım---
        "sr?wc=103763", # süpermarket bebek bakım süt artırıcı içecekler
        "sr?wc=105500", # süpermarket bebek bakım bebek ek besin
        "sr?wc=105560", # süpermarket bebek bakım bebek diş fırçası
        "sr?wc=103753", # süpermarket bebek bakım bebek mamaları
        "sr?wc=144838", # süpermarket bebek bakım bebek diş macunu
        "sr?wc=144855", # süpermarket bebek bakım bebek temizleme pamuğu
        "sr?wc=103772", # süpermarket bebek bakım bebek güneş kremi
        "sr?wc=108959", # süpermarket bebek  bakım bebek bakım seti
        "sr?wc=103774", # süpermarket bebek bakım bebek kolonyası
        "sr?wc=144836", # süpermarket bebek bakım bebek bakım örtüsü

        # --- süpermarket  gıda içecek ---
        "sr?wc=103946", # süpermarket gıda içecek ana kategorisi
        "sr?wc=104000", # süpermarket gıda içecek çay
        "sr?wc=109242", # süpermarket gıda içecek özel gıda
        "sr?wc=103961", # süpermarket gıda içecek kahvaltılık
        "sr?wc=103970", # süpermarket gıda içecek kuru gıda
        "sr?wc=104004", # süpermarket gıda içecek kahve
        "sr?wc=103978", # süpermarket gıda içecek makarna
        "sr?wc=103981", # süpermarket gıda içecek salça
        "sr?wc=103982", # süpermarket gıda içecek sıvı yağ
        "sr?wc=109358", # süpermarket gıda içecek un
        "sr?wc=103971", # süpermarket gıda içecek tuz baharat
        "sr?wc=103974", # süpermarket gıda içecek çorba
        "sr?wc=103964", # süpermarket gıda içecek gevrek
        "sr?wc=144224", # süpermarket gıda içecek yulaf
        "sr?wc=103976", # süpermarket gıda içecek konserve
        "sr?wc=145237", # süpermarket gıda içecek şeker
        "sr?wc=104008", # süpermarket gıda içecek süt
        "sr?wc=145280", # süpermarket gıda içecek pasta süslemeleri
        "sr?wc=144018", # süpermarket gıda içecek bitki çayı
        "sr?wc=109250", # süpermarket gıda içecek gazsız içecekler


    # --- süpermarket  atırştırmalık---
        "sr?wc=103947", # süpermarket atıştırmalık ana kategorisi
        "sr?wc=144189", # süpermarket atıştırmalık kuru meyve
        "sr?wc=103953", # süpermarket atıştırmalık kuru yemiş 
        "sr?wc=103949", # süpermarket atıştırmalık cips
        "sr?wc=103950", # süpermarket atıştırmalık çikolata
        "sr?wc=144188", # süpermarket atıştırmalık gofret
        "sr?wc=103948", # süpermarket atıştırmalık buskivi
        "sr?wc=109635", # süpermarket atıştırmalık kraker
        "sr?wc=103956", # süpermarket atıştırmalık şekerleme
        "sr?wc=103955", # süpermarket atıştırmalık sakız
        "sr?wc=110468", # süpermarket atıştırmalık protein bar
        "sr?wc=105095", # süpermarket atıştırmalık sağlıklı atırştırmalıklar
        "sr?wc=109626", # süpermarket atıştırmalık unlu mamuller
        "sr?wc=105470", # süpermarket atıştırmalık kek

    # --- süpermarket  petshop---
        "sr?wc=1142", # süpermarket petshop ana kategorisi
        "sr?wc=103588", # süpermarket petshop kedi maması
        "sr?wc=103584", # süpermarket petshop kedi kumu 
        "sr?wc=103620", # süpermarket petshop köpek maması
        "sr?wc=103596", # süpermarket petshop kedi vitamini
        "sr?wc=103631", # süpermarket petshop köpek tasması
        "sr?wc=103635", # süpermarket petshop kuş ürünleri
        "sr?wc=103564", # süpermarket petshop akvaryum ürünleri
        "sr?wc=103592", # süpermarket petshop kedi box ürünleri 
        "sr?wc=103590%2C103624&lc=103590%2C103624", # süpermarket petshop kedi oyuncakları ve köpek oyuncakları
        "sr?wc=103581", # süpermarket petshop kedi yaş mamaları
        "sr?wc=103589", # süpermarket petshop köpek yaş ödül mamaları
        "sr?wc=103622", # süpermarket petshop köpek ödül mamaları
        "sr?wc=105438", # süpermarket petshop kedi şampuanı
        "sr?wc=103587", # süpermarket petshop su ve mama kapları
        "sr?wc=103647", # süpermarket petshop kuş yemleri
        "sr?wc=103597", # süpermarket petshop kedi köpek yatakları
        "sr?wc=103588&attr=279%7C12308", #  süpermarket petshop yavru kedi maması
        "sr?wc=103568", # süpermarket petshop akvaryum balık yemi 
        "sr?wc=103595", # süpermarket petshop kedi tuvaleti
        "sr?wc=103575", # süpermarket petshop kedi fırça tarağı

    # --- kozmetik  ---
    # --- kozmetik  makyaj---
        "sr?wc=103594", # kozmetik makyaj ana kategorisi
        "sr?wc=1346", # kozmetik makyaj dudak makyajı
        "sr?wc=104019", # kozmetik makyaj makyaj setleri
        "sr?wc=1124", # kozmetik makyaj oje aseton
        "sr?wc=1053", # kozmetik makyaj fondoten
        "sr?wc=1042", # kozmetik makyaj dudak kalemi
        "sr?wc=1114", # kozmetik makyaj maskara
        "sr?wc=1060", # kozmetik makyaj göz kalemi
        "sr?wc=1085", # kozmetik makyaj kapatıcılar
        "sr?wc=999", # kozmetik makyaj allık
        "sr?wc=104017", # kozmetik makyaj highlighter
        "sr?wc=108823", # kozmetik makyaj bb cc krem
        "sr?wc=104018", # kozmetik makyaj kontür paletler
        "sr?wc=1153", # kozmetik makyaj pudra
        "sr?wc=104071", # kozmetik makyaj takma tırnak

    # --- kozmetik   cilt bakımı ---
        "sr?wc=104014", # süpermarket cilt bakım yüz temizleme
        "sr?wc=1212", # süpermarket cilt bakım yüz maskesi
        "sr?wc=101380", # süpermarket cilt bakım göz bakımı
        "sr?wc=143835", # süpermarket cilt bakım güneş koruyucu
        "sr?wc=101381", # süpermarket cilt bakım cilt serumu
        "sr?wc=104064", # süpermarket cilt bakım el ayak bakımı
        "sr?wc=1196", # süpermarket cilt bakım tonikler
        "sr?wc=143996", # süpermarket cilt bakım peeling ürünleri
        "sr?wc=143763", # süpermarket cilt bakım el kremleri
        "sr?wc=109607", # süpermarket cilt bakım makyaj temizleyiciler
        "sr?wc=101386", # süpermarket cilt bakım vücut spreyleri
        

    # --- kozmetik  parfüm deadorant ---
        "sr?wc=103717", # kozmetik parfüm deodorant ana kategorisi
        "sr?wc=101385", # kozmetik parfüm deodorant parfüm setleri


    # --- kozmetik  saç bakımı  ---
        "sr?wc=1180", # kozmetik  saç bakımı şampuan
        "sr?wc=101390", # kozmetik  saç bakımı saç şekillendirici
        "sr?wc=1162", # kozmetik  saç bakımı saç serumu maskesi
        "sr?wc=1159", # kozmetik  saç bakımı saç boyası 
        "sr?wc=108967", # kozmetik  saç bakımı kuru şampuan 
        "sr?wc=104066", # kozmetik  saç bakımı  saç köpüğü 
        "sr?wc=101388", # kozmetik  saç bakımı saç kremi 
        "sr?wc=104067", # kozmetik  saç bakımı spreyi 
        "sr?wc=144787", # kozmetik  saç bakımı renk açıcı 
        "sr?wc=144697", # kozmetik  saç bakımı makası
        "sr?wc=1195", # kozmetik  saç bakımı toka 
        "sr?wc=144699", # kozmetik  saç bakımı saç vitamini 
        "sr?wc=144698", # kozmetik  saç bakımı saç toniği


    # --- kozmetik kişisel bakım   ---
        "sr?wc=104068", #  kozmetik kişisel bakım  ana katagorisi
        "sr?wc=101401", # kozmetik kişisel bakım duj jelleri 
        "sr?wc=143766", # kozmetik kişisel bakım pamuk 
        "sr?wc=105497", # kozmetik kişisel bakım ağız bakım suyu 
        "sr?wc=101397", # kozmetik kişisel bakım diş fırçası 
        "sr?wc=101398", # kozmetik kişisel bakım diş macunu 
        "sr?wc=104021", # kozmetik kişisel bakım diş ipi 
        "sr?wc=109362", # kozmetik kişisel bakım kaş makası
        "sr?wc=108942", # kozmetik kişisel bakım banyo lifi
        "sr?wc=104022", # kozmetik kişisel bakım diş beyazlatıcı

        
        # --- kozmetik makyaj aksesuarları   ---
        "sr?wc=1252", # kozmetik makyaj aksesuarları ana katagorisi
        "sr?wc=1253", # kozmetik makyaj aksesuarları makyaj fırçaları
        "sr?wc=109114", # kozmetik makyaj aksesuarları makyaj süngerleri
        "sr?wc=109361", # kozmetik makyaj aksesuarları cımbız
        "sr?wc=109115", # kozmetik makyaj aksesuarları kirpik kıvırıcı
        
        
        # --- kozmetik epilasyon tıraş  ---
        "sr?wc=105782", # kozmetik epilasyon tıraş ana katagorisi
        "sr?wc=106112", # kozmetik epilasyon tıraş ağda
        "sr?wc=104074", # kozmetik epilasyon tıraş epilatör
        "sr?wc=101405", # kozmetik epilasyon tıraş köpüğü 
        "sr?wc=104061", # kozmetik epilasyon tıraş tüy dökücü krem
        
        
        # --- kozmetik genel bakım  ---
        "sr?wc=101408", # kozmetik genel bakım cinsel sağlık 
        "sr?wc=104013", # kozmetik genel bakım bakım yağları
        "sr?wc=148181", # kozmetik genel bakım  sıvı sabun
        "sr?wc=109093", # kozmetik genel bakım el dezenfenktanı
        
        # --- ayyakabı çanta   ---
        
        # --- ayyakabı çanta  kadın ayyakkabı  ---
        "sr?wc=107&wg=1", # ayyakabı çanta  kadın ayyakkabı  topuklu
        "sr?wc=110&wg=1", # ayyakabı çanta  kadın ayyakkabı terlik
        "sr?wc=113&wg=1", # ayyakabı çanta  kadın ayyakkabı babet
        "sr?wc=106", # ayyakabı çanta  kadın ayyakkabı dolgu topuklu ayyakkabı
        "sr?wc=1132&wg=1", # ayyakabı çanta  kadın ayyakkabı panduf
        
        # --- ayyakabı çanta erkek ayyakkabı   ---
        "sr?wc=144727", # ayyakabı çanta erkek ayyakkabı krampon
        "sr?wc=1057", # ayyakabı çanta erkek ayyakkabı halı saha ayyakabısı
        "sr?wc=111&wg=2", # ayyakabı çanta erkek ayyakkabı sandalaet
        "sr?wc=101422", # ayyakabı çanta erkek ayyakkabı basketbol ayakkabısı
        "sr?wc=110&wg=2", # ayyakabı çanta erkek ayyakkabı  terlik 
        "sr?wc=104208&wg=2", # ayyakabı çanta erkek ayyakkabı ev terliği 
        "sr?wg=2&wc=103687", # ayyakabı çanta erkek ayyakkabı deniz ayyakkabısı

        
        # --- ayyakabı çanta çocuk çanta  ---
        "sr?wc=117&wg=3", # ayyakabı çanta çocuk çanta ana catogory
        "sr?wc=115&wg=3 ", # ayyakabı çanta çocuk çanta sırt çanta
        "sr?wc=104204&wg=3", # ayyakabı çanta çocuk çanta okul çanta
        "sr?wc=104040&wg=3", # ayyakabı çanta çocuk çanta beslenme çantası 
        "sr?wc=104144&wg=3", # ayyakabı çanta çocuk çanta bel çantası 
        "sr?wc=1152&wg=3", # ayyakabı çanta çocuk çanta postacı çantası
        
        
        # --- ayyakabı çanta   erkek aksesuar ---
        "sr?wg=2&wc=34", # ayyakabı çanta   erkek aksesuar saat
        "sr?wg=2&wc=1181", # ayyakabı çanta   erkek aksesuar şapka
        "sr?wc=101&wg=2", # ayyakabı çanta   erkek aksesuar bileklik 
        "sr?wc=1133", # ayyakabı çanta   erkek aksesuar papyon 
        
        # --- ayyakabı çanta kadın aksesuar  ---
        "sr?wc=28&wg=1", # ayyakabı çanta kadın aksesuar takı 
        "sr?wc=1181&wg=1", # ayyakabı çanta kadın aksesuar şapka
        "sr?wc=105", # ayyakabı çanta kadın aksesuar güneş gözlüğü
        "sr?wc=101434&wg=1", # ayyakabı çanta kadın aksesuar saç aksesuarı 
        "sr?wg=1&wc=1093", # ayyakabı çanta kadın aksesuar kemer
        "sr?wc=103548", # ayyakabı çanta kadın aksesuar gümüş kolye 

        
        # --- ayyakabı çanta kadın çanta  ---
        "sr?wc=117&wg=1", # ayyakabı çanta kadın çanta ana catogory 
        "sr?wc=101465&wg=1", # ayyakabı çanta kadın çanta omuza çanta 
        "sr?wc=115&wg=1", # ayyakabı çanta kadın çanta sırt çanta 
        "sr?wc=1174&wg=1", # ayyakabı çanta kadın çanta spor çanta 
        "sr?wg=1&wc=104144", # ayyakabı çanta kadın çanta bel çanta 
        "sr?wc=104145&wg=1", # ayyakabı çanta kadın çanta el çanta 
        "sr?wc=1151&wg=1", # ayyakabı çanta kadın çanta portföy
        "sr?wc=1087&wg=1", # ayyakabı çanta kadın çanta kartlık
        "sr?wc=103082&wg=1", # ayyakabı çanta kadın çanta abiye çanta
        "sr?wc=1152&wg=1", # ayyakabı çanta kadın çanta postacı çanta 
        "sr?wc=1147&wg=1", # ayyakabı çanta kadın çanta plaj çanta 
        "sr?wg=1&wc=1107", # ayyakabı çanta kadın çanta laptop çantası 
        "sr?wc=117", # ayyakabı çanta kadın çanta kapitone çanta 
        "sr?wc=1110", # ayyakabı çanta kadın çanta makyaj çanta
        "sr?wg=1&wc=1202", # ayyakabı çanta kadın çanta valiz bavul 

        
        # --- ayyakabı çanta erkek çanta  --- 
        "sr?wc=115&wg=2", # ayyakabı çanta erkek çanta sırt çantası 
        "sr?wg=2&wc=1107", # ayyakabı çanta erkek çanta laptop çantası
        "sr?wc=104144&wg=2", # ayyakabı çanta erkek çanta bel çantası 
        "sr?wc=101465&wg=2", # ayyakabı çanta erkek çanta omuz çantası 
        "sr?wg=2&wc=1151", # ayyakabı çanta erkek çanta portföy çanta
        "sr?wc=145612", # ayyakabı çanta erkek çanta  olta çantası 
        "sr?wc=104204&wg=2", # ayyakabı çanta erkek çanta okul çantası 
        "sr?wc=104145&wg=2", # ayyakabı çanta erkek çanta  el çantası 
        
        # --- Elektronik ---
        
        # --- elektronik küçük ev aletleri ---
        "sr?wc=1104", # elektronik küçük ev aletleri ana catagory 
        "sr?wc=108939", # elektronik küçük ev aletleri  süpürge
        "sr?wc=109453", # elektronik küçük ev aletleri  robot süpürge 
        "sr?wc=109454", # elektronik küçük ev aletleri dikey süpürge 
        "sr?wc=1201", # elektronik küçük ev aletleri ütü
        "sr?wc=1079", # elektronik küçük ev aletleri kahve makinesi
        "sr?wc=108890", # elektronik küçük ev aletleri  çay makinesi 
        "sr?wc=103677", # elektronik küçük ev aletleri blender seti
        "sr?wc=1197", # elektronik küçük ev aletleri tost makinesi
        "sr?wc=101508", # elektronik küçük ev aletleri su ısıtıcı ketil
        "sr?wc=1055", # elektronik küçük ev aletleri airfray
        
        
        #--- elektronik giyilebilir teknoloji ---
        "sr?wc=144430", # elektronik giyilebilir teknoloji ana catagory
        "sr?wc=1240", # elektronik giyilebilir teknoloji akıllı saat
        "sr?wc=103111", # elektronik giyilebilir teknoloji akıllı bileklik
        "sr?wc=104039", # elektronik giyilebilir teknoloji vr gözlük

        
        # --- elektronik telefon ---
        "sr?wc=104025", #  elektronik telefon ana catagory
        "sr?wc=103498", #  elektronik telefon cep telefonu
        "sr?wc=164461", #  elektronik telefon androit cep telefonu 
        "sr?wc=164462", #  elektronik telefon iphoen cep telefonu
        "sr?wc=104026", #  elektronik telefon telefon kılıfları
        "sr?wc=103112", #  elektronik telefon  şarj cihazları
        "sr?wc=103113", #  elektronik telefon powerbank
        "sr?wc=104033", #  elektronik telefon araç içi telefon tutucu
        "sr?wc=92", #  elektronik telefon kulaklıklar
        
        # --- elektronik foto ---
        "sr?wc=104037", # elektronik foto ana catagory
        "sr?wc=104245", # elektronik foto aksiyon kamera
        "sr?wc=104042", # elektronik foto fotoğraf makinesi
        "sr?wc=104043", # elektronik foto video kamera
        "sr?wc=103782", # elektronik foto hafıza kartı

        
        # --- elektronik tv görüntü ses---
        "sr?wc=104035", # elektronik tv görüntü ses ana catagory
        "sr?wc=104156", # elektronik tv görüntü ses televizyon
        "sr?wc=110304", # elektronik tv görüntü ses kumanda
        "sr?wc=143233", # elektronik tv görüntü ses saund bar
        "sr?wc=104157", # elektronik tv görüntü ses projeksion
        "sr?wc=103669", # elektronik tv görüntü ses mediaplayer
        "sr?wc=1067", # elektronik tv görüntü ses hoparlör
        "sr?wc=109343", # elektronik tv görüntü ses uydu alıcısı
        "sr?wc=150104", # elektronik tv görüntü ses hdmi kablo
        "sr?wc=103672", # elektronik tv görüntü ses kablo adaptör
        "sr?wc=110303", # elektronik tv görüntü ses tv ekran koruyucu
        "sr?wc=110306", # elektronik tv görüntü ses tv askı aparatı

        
        # --- elektronik beyaz eşya --- 
        "sr?wc=103613", # elektronik beyaz eşya ana catagory
        "sr?wc=103623", # elektronik beyaz eşya buzdolabı
        "sr?wc=103625", # elektronik beyaz eşya çamaşır bakinesi
        "sr?wc=103621", # elektronik beyaz eşya bulaşık makinesi
        "sr?wc=103636", # elektronik beyaz eşya kurutma makinesi
        "sr?wc=103629", # elektronik beyaz eşya derin dondurucu
        "sr?wc=103615", # elektronik beyaz eşya ankastre setler 
        "sr?wc=104081", # elektronik beyaz eşya kombi
        "sr?wc=103681", # elektronik beyaz eşya mikrodalga
        "sr?wc=103616", # elektronik beyaz eşya aspiratör
        "sr?wc=103682", # elektronik beyaz eşya mini fırın 
        "sr?wc=103627", # elektronik beyaz eşya ankastre davlumbaz
        
        # --- elektronik bilgisayar tablet ---
        "sr?wc=103665%2C108656", # elektronik bilgisayar tablet ana catagory
        "sr?wc=108656", # elektronik bilgisayar tablet bilgisayar
        "sr?wc=103665", # elektronik bilgisayar tablet tablet
        "sr?wc=103662", # elektronik bilgisayar tablet bilgisayar bileşenleri
        "sr?wc=103668", # elektronik bilgisayar tablet monitör
        "sr?wc=104116", # elektronik bilgisayar tablet yazıcı tarayıcı
        "sr?wc=103661", # elektronik bilgisayar tablet ağ modem 
        "sr?wc=103671", # elektronik bilgisayar tablet klavye
        "sr?wc=108664", # elektronik bilgisayar tablet mause
        "sr?wc=108710", # elektronik bilgisayar tablet grafik tablet
        "sr?wc=103784", # elektronik bilgisayar tablet ssd
        "sr?wc=108545", # elektronik bilgisayar tablet ram
        "sr?wc=108443", # elektronik bilgisayar tablet ekran kartı
        "sr?wc=165427", # elektronik bilgisayar tablet çocuk çizim tableti
        
        # --- teknoloji kişisel bakım aletleri ---
        "sr?wc=103109", # teknoloji kişisel bakım aletleri ana catagory
        "sr?wc=1160", # teknoloji kişisel bakım aletleri saç düzleştirici 
        "sr?wc=1163", # teknoloji kişisel bakım aletleri saç maşası
        "sr?wc=1161", # teknoloji kişisel bakım aletleri saç kurutma makinesi
        "sr?wc=102377", # teknoloji kişisel bakım aletleri tıraş makinesi
        "sr?wc=1012", # teknoloji kişisel bakım aletleri tartı

        
        
        # --- elektronik aksesuarlar ---
        "sr?wc=104568", # elektronik aksesuarlar bilgisayar aksesuarı
        "sr?wc=1190", # elektronik aksesuarlar telefon aksesuarı

        # --- spor outdoor ---
        # --- spor outdoor top ---
        "sr?wc=109389", # spor outdoor top basketbol
        "sr?wc=109372", # spor outdoor top futboool

        
        # --- spor outdoor evde spor aletleri---
        "sr?wc=104192", # spor outdoor evde spor aletleri ana catagory
        "sr?wc=109294", # spor outdoor evde spor aletleri lastik 
        "sr?wc=145850", # spor outdoor evde spor aletleri el yayı
        "sr?wc=104286", # spor outdoor evde spor aletleri çalışma istasyonları
        "sr?wc=104287", # spor outdoor evde spor aletleri dambıl seti
        "sr?wc=104285", # spor outdoor evde spor aletleri barfiks barı
        "sr?wc=104283", # spor outdoor evde spor aletleri eldiven
        "sr?wc=104276", # spor outdoor evde spor aletleri kondisyon bisiklet
        "sr?wc=104277", # spor outdoor evde spor aletleri yürüme bandı
        "sr?wc=109292", # pilates topu 
        "sr?wc=104288", # kürek çekme aleti
        "sr?wc=145667", # boks bandajı

        
        # --- spor outdoor spor malzemeleri ---
        "sr?wc=104539", # spor outdoor spor malzemeleri deniz plaj
        "sr?wc=1091", # spor outdoor spor malzemeleri kaykay
        "sr?wc=1138", # spor outdoor spor malzemeleri paten
        "sr?wc=104250", # spor outdoor spor malzemeleri kamp malzemeleri
        "sr?wc=104268", # spor outdoor spor malzemeleri dağcılık tırmanış
        "sr?wc=145901", # spor outdoor spor malzemeleri su sporu malzemeleri
        "sr?wc=104231", # spor outdoor spor malzemeleri balıkçı malzemeleri
        "sr?wc=145769", # spor outdoor spor malzemeleri tenis 
        "sr?wc=145746", # spor outdoor spor malzemeleri okçuluk 
        "sr?wc=104254", # spor outdoor spor malzemeleri çadır
        "sr?wc=145893", # spor outdoor spor malzemeleri su matarası

        
        # --- spor outdoor bisiklet---
        "sr?wc=104581", # spor outdoor bisiklet malzemeleri
        "sr?wc=145636", # spor outdoor bisiklet kaskları
        "sr?wc=145634", # spor outdoor bisiklet gözlükleri
        
        # --- spor outdoor besinleri---
        "sr?wc=105131", # spor outdoor besinleri ana katagory 
        "sr?wc=104165", # spor outdoor besinleri protein tozu 
        "sr?wc=104160", # spor outdoor besinleri amino asit 
        "sr?wc=104161", # spor outdoor besinleri karbonhidrat 
        "sr?wc=104163", # spor outdoor besinleri l karnitin 
        "sr?wc=105094", # spor outdoor besinleri güç performans
        "sr?wc=105085", # spor outdoor besinleri gıda takviyesi vitaminler 
        "sr?wc=104162", # spor outdoor besinleri kreatin 
        "sr?wc=104225", # spor outdoor besinleri shaker
        
        # --- kitap kırtasiye ---
        # --- kitap kırtasiye parti malzemeleri ---
        "sr?wc=1136", # kitap kırtasiye parti malzemeleri ana catagory 
        "sr?wc=108919", # kitap kırtasiye parti malzemeleri le dışık 
        "sr?wc=108700", # kitap kırtasiye parti malzemeleri düğün kına 
        "sr?wc=108923", # kitap kırtasiye parti malzemeleri yılbaşı süsü 
        "sr?wc=108922", # kitap kırtasiye parti malzemeleri yılbaşı ağacı
        "sr?wc=108696", # kitap kırtasiye parti malzemeleri balon 

        
        # --- kitap kırtasiye hobi malzemelerti ---
        "sr?wc=104142", # kitap kırtasiye hobi malzemelerti ana catagory
        "sr?wc=109695", # kitap kırtasiye hobi malzemelerti örgü ipi 
        "sr?wc=109702", # kitap kırtasiye hobi malzemelerti boncuk 
        "sr?wc=109111", # kitap kırtasiye hobi malzemelerti kumaş 
        "sr?wc=109692", # kitap kırtasiye hobi malzemelerti nakış kiti 
        "sr?wc=109693", # kitap kırtasiye hobi malzemelerti  örgü kiti 

        # --- kitap kırtasiye çakmak ürünleri ---
        "sr?wc=144491", # kitap kırtasiye çakmak ürünleri ana catagory
        "sr?wc=143894", # kitap kırtasiye çakmak ürünleri  benzinli çakmak
        "sr?wc=143895", # kitap kırtasiye çakmak ürünleri klasik çakmak 

        # --- kitap kırtasiye müzik aletleri ---
        "sr?wc=1357", # kitap kırtasiye müzik aletleri ana catagory
        "sr?wc=1144", #  kitap kırtasiye müzik aletleri gramafon 
        "sr?wc=108730", # kitap kırtasiye müzik aletleri gitar
        "sr?wc=1148", # kitap kırtasiye müzik aletleri plak
        "sr?wc=109223", # kitap kırtasiye müzik aletleri piyano 
        "sr?wc=109403", # kitap kırtasiye müzik aletleri org 

        # --- kitap kırtasiye hediyelik ürünler ---
        "sr?wc=110312", # kitap kırtasiye hediyelik ürünler  ana catagory
        "sr?wc=106338", # kitap kırtasiye hediyelik ürünler  konseptlik hedyeler
        "sr?wc=104570", # kitap kırtasiye hediyelik ürünler figür
        "sr?wc=110313", # kitap kırtasiye hediyelik ürünler  hediye kutusu
        "sr?wc=108924", # kitap kırtasiye hediyelik ürünler kar küresi
        "sr?wc=110316", # kitap kırtasiye hediyelik ürünler paket malzemesi
        
        # ---kitap kırtasiye e kitap okuyucu ---
        "sr?wc=104372", #

        # ---kitap kırtasiye e DİN MİTOLOJİ ---
        "sr?wc=104375", #
        
        # ---kitap kırtasiye e kişisel gelişim ---
        "sr?wc=104342", #
        
        # ---kitap kırtasiye e hobi sanat akademi ---
        "sr?wc=142658", #
        
        # --- kitap kırtasiye oyun gurupları ---
        "sr?wc=108703", # kitap kırtasiye oyun gurupları ana catagory 
        "sr?wc=109305", # kitap kırtasiye oyun gurupları puzle
        "sr?wc=108706", # kitap kırtasiye oyun gurupları okey takımı 
        "sr?wc=108705", # kitap kırtasiye oyun gurupları satranç 
        "sr?wc=104399", # kitap kırtasiye oyun gurupları maket

        # --- kitap kırtasiye kırtasiye ---
        "sr?wc=104125", # kitap kırtasiye kırtasiye ana catagory
        "sr?wc=1233", # kitap kırtasiye kırtasiye defter
        "sr?wc=109121", # kitap kırtasiye kırtasiye ajanada
        "sr?wc=104138", # kitap kırtasiye kırtasiye etiket
        "sr?wc=103714", # kitap kırtasiye kırtasiye suluk matara
        "sr?wc=106544", # kitap kırtasiye kırtasiye yazı tahtası
        "sr?wc=106545", # kitap kırtasiye kırtasiye pano
        "sr?wc=104139", # kitap kırtasiye kırtasiye silgi
        "sr?wc=109366", # kitap kırtasiye kırtasiye makas
        "sr?wc=104141", # kitap kırtasiye kırtasiye yapıştırıcı

        
        # --- kitap kırtasişye yabancı dil kitaplar ---
        "sr?wc=104320",
        
        # --- kitap kırtasişye yabancı çizgi ropman dergi ---
        "sr?wc=104393",
        
        
        # --- kitap kırtasiye ofis ---
        "sr?wc=104424", # kitap kırtasiye ofis 
        "sr?wc=1080", # kitap kırtasiye ofis kalem
        "sr?wc=104356", # kitap kırtasiye ofis sınava hazırlık

        # --- kitap kırtasiye boya sanatsal malzemeler  ---
        "sr?wc=103788%2C103798%2C104126", # ana katagory 

        
        
        



    ]
    price_ranges = [
        "0-300", 
        "300-500", 
        "500-800", 
        "800-1200", 
        "1200-2000", 
        "2000-5000",
        "5000-10000",
        "10000-100000",
        "100000-500000"
    ]
    
    categories = []
    for cat in base_categories:
        for prc in price_ranges:
            categories.append(f"{cat}&prc={prc}")
    
        
    #linkleri çekmek için ilk ayarlamaları yapacağız. JavaScript ile çalışan bir site olduğu için Playwright kullanarak sayfanın tam olarak yüklenmesini sağlayacağız.
    def start_requests(self):
        self.logger.info(f"Toplam {len(self.categories)} kategori için işlem başlatılıyor.")
        for category in self.categories:
            # pi=1 (1. sayfa) parametresi ile başlıyoruz
            url = f"https://www.trendyol.com/{category}&pi=1"
            self.logger.debug(f"URL istek gönderildi: {url}")
            yield scrapy.Request(
                url=url,
                headers={
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
                },
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
                next_url = f"https://www.trendyol.com/{category_name}&pi={next_page}"
                
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