# Define your item pipelines here
#
# Don't forget to add your pipeline to the ITEM_PIPELINES setting
# See: https://docs.scrapy.org/en/latest/topics/item-pipeline.html


# useful for handling different item types with a single interface
from itemadapter import ItemAdapter
from openpyxl import Workbook
from .items import HaberItem
import os


class HaberPipeline:
    def process_item(self, item, spider):
        return item

class ExcelWritePipline:
    def open_spider(self, spider):
        self.filename = 'haberler_listesi.xlsx'
        self.workbook = Workbook()
        self.sheet = self.workbook.active
        self.sheet.title = "Haberler"
        
        
        self.sheet.append([
            "Haber Türü", 
            "Başlık", 
            "Tarih", 
            "Etiketler", 
            "Görsel URL", 
            "Haber Metni", 
            "Haber URL"
        ])
        
      
        self.workbook.save(self.filename)
        spider.logger.info("Excel dosyası oluşturuldu ve başlıklar atıldı.")
        
    def process_item(self, item, spider):
        
        tags = item.get('tag', [])
        if isinstance(tags, list):
            tags = ", ".join(tags)
        
        
        news_text = item.get('news_text', "")
        if isinstance(news_text, list):
            
            news_text = " ".join(news_text)
            
        
        news_type = item.get('news_type', "")
        name = item.get('name', "")
        history = item.get('history', "")
        img_url = item.get('img_url', "")
        product_url = item.get('product_url', "")

       
        self.sheet.append([
            news_type,
            name,
            history,
            tags,
            img_url,
            news_text, 
            product_url
        ])
        
    
        try:
            self.workbook.save(self.filename)
        except PermissionError:
           
            spider.logger.error("DİKKAT: Excel dosyası açık olduğu için kayıt yapılamadı! Kapatıp tekrar deneyin.")
        except Exception as e:
            spider.logger.error(f"Beklenmedik bir kaydetme hatası oluştu: {e}")
            
        return item
    
    def close_spider(self, spider):
        try:
            self.workbook.save(self.filename)
            spider.logger.info(f"Tarama bitti. Dosya başarıyla kaydedildi: {self.filename}")
        except:
            pass