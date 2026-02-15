# Define here the models for your scraped items
#
# See documentation in:
# https://docs.scrapy.org/en/latest/topics/items.html

import scrapy


class TrendyolBotItem(scrapy.Item):
    url = scrapy.Field(output_processor=TakeFirst())
    category = scrapy.Field()
    title = scrapy.Field(output_processor=TakeFirst())   
    evolation = scrapy.Field(output_processor=TakeFirst())
    price = scrapy.Field(output_processor=TakeFirst())
    images = scrapy.Field()
    explanation = scrapy.Field(output_processor=TakeFirst())
    
    
