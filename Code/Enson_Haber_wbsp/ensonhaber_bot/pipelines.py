# Define your item pipelines here
#
# Don't forget to add your pipeline to the ITEM_PIPELINES setting
# See: https://docs.scrapy.org/en/latest/topics/item-pipeline.html


# useful for handling different item types with a single interface
from itemadapter import ItemAdapter
from scrapy.exceptions import DropItem
import pandas as pd
from datetime import datetime
import logging

class EnsonhaberBotPipeline:
    def __init__(self):
        self.items = []
        self.seen_urls = set()
        
    def process_item(self, item, spider):
        # Başlık veya link yoksa veriyi kaydetme
        if not item.get('name') or not item.get('product_url'):
            raise DropItem(f"Eksik veri atlandı: {item.get('product_url')}")

        # Aynı linke sahip haberleri eler
        if item['product_url'] in self.seen_urls:
            raise DropItem(f"Aynı haber haber atlandı: {item['name']}")
        
        self.seen_urls.add(item['product_url'])

        # Cleaning
        # Liste halindeki haber metinlerini temiz bir paragrafa dönüştürür
        if isinstance(item.get('news_text'), list):
            # Boş paragrafları eler ve \xa0 (non-breaking space) karakterlerini temizler
            clean_text_list = [p.replace('\xa0', ' ').strip() for p in item['news_text'] if p.strip()]
            item['news_text'] = " ".join(clean_text_list)

        # Görsel linklerini , ile kaydetme ayırma
        if isinstance(item.get('sub_img_url'), list):
            item['sub_img_url'] = ", ".join(item['sub_img_url'])

        # Temizlenen item'ı Excel'e yazılacak listeye ekle
        self.items.append(dict(item))
        return item

    def close_spider(self, spider):
        
        if self.items:
            spider.logger.info(f"Excel raporu hazırlanıyor... (Satır sayısı: {len(self.items)})")
            
            df = pd.DataFrame(self.items)
            
            # Sütunları daha düzenli bir sıraya koyalım
            cols = [
                'news_type', 'name', 'subheading', 'data_owner', 
                'data_owner_img_url', 'history', 'main_img_url', 
                'sub_img_url', 'news_text', 'product_url', 'product_source'
            ]
            df = df.reindex(columns=[c for c in cols if c in df.columns])
            
            # Dosya ismine tarih ve saat ekleyerek karışıklığı önleriz
            timestamp = datetime.now().strftime("%Y%m%d_%H%M")
            filename = f"Ensonhaber_teknoloji_Raporu_{timestamp}.xlsx"
            
            df.to_excel(filename, index=False)
            spider.logger.info(f"BAŞARI: Veriler '{filename}' dosyasına kaydedildi.")
        else:
            spider.logger.warning("Hiç veri çekilemediği için Excel oluşturulmadı.")
