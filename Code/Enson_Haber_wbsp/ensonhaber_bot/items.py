# Define here the models for your scraped items
#
# See documentation in:
# https://docs.scrapy.org/en/latest/topics/items.html

import scrapy


class EnsonhaberBotItem(scrapy.Item):
    news_type = scrapy.Field()
    name = scrapy.Field()
    subheading = scrapy.Field()
    data_owner = scrapy.Field()
    data_owner_img_url = scrapy.Field()
    history = scrapy.Field()
    main_img_url = scrapy.Field()
    sub_img_url = scrapy.Field()
    news_text = scrapy.Field()
    product_url = scrapy.Field()
    product_source = scrapy.Field()
