# Define here the models for your scraped items
#
# See documentation in:
# https://docs.scrapy.org/en/latest/topics/items.html

import scrapy
from itemloaders.processors import TakeFirst, Join, MapCompose


class TrendyolBotItem(scrapy.Item):
    url = scrapy.Field(output_processor=TakeFirst())
    category = scrapy.Field(output_processor=TakeFirst())
    title = scrapy.Field(output_processor=TakeFirst())   
    evaluation = scrapy.Field(output_processor=TakeFirst()) # Değerlendirme puanı
    evaluation_len = scrapy.Field(output_processor=TakeFirst()) # Değerlendirme sayısı
    price = scrapy.Field(output_processor=TakeFirst())
    images = scrapy.Field(output_processor=Join(", ")) 
       
    explanation = scrapy.Field( #
        input_processor=MapCompose(str.strip), # Boşlukları temizler
        output_processor=Join("\n")            # Paragraflar arasına satır başı koyarak birleştirir
    )
    
    
