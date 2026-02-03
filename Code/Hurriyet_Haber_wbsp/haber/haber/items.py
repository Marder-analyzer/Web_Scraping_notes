# Define here the models for your scraped items
#
# See documentation in:
# https://docs.scrapy.org/en/latest/topics/items.html

import scrapy


class HaberItem(scrapy.Item):
    news_type = scrapy.Field()
    name = scrapy.Field()
    history = scrapy.Field()
    tag = scrapy.Field()
    img_url = scrapy.Field()
    news_text = scrapy.Field()
    product_url = scrapy.Field()
    
    
