# Define here the models for your scraped items
#
# See documentation in:
# https://docs.scrapy.org/en/latest/topics/items.html

import scrapy
from itemloaders.processors import TakeFirst, Join, MapCompose

def clean_text(value):
    """Gelen metinlerin başındaki ve sonundaki gereksiz boşlukları siler"""
    if value:
        return str(value).strip()
    return value


class TrendyolBotItem(scrapy.Item):
    
    url = scrapy.Field(output_processor=TakeFirst())
    category = scrapy.Field(output_processor=TakeFirst())
    
    title = scrapy.Field(
        input_processor=MapCompose(clean_text),
        output_processor=TakeFirst()
    )
    
    price = scrapy.Field(
        input_processor=MapCompose(clean_text),
        output_processor=TakeFirst()
    )
    
    images = scrapy.Field()
    
    explanation = scrapy.Field(
        input_processor=MapCompose(clean_text),
        output_processor=TakeFirst()
    )
    evaluation = scrapy.Field(
        input_processor=MapCompose(clean_text),
        output_processor=TakeFirst()
    )
    evaluation_len = scrapy.Field(
        input_processor=MapCompose(clean_text),
        output_processor=TakeFirst()
    )
    
    attributes = scrapy.Field(output_processor=TakeFirst())
