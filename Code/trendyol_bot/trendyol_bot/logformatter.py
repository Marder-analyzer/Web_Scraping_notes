from scrapy.logformatter import LogFormatter
import logging


class QuietLogFormatter(LogFormatter):
    def dropped(self, item, exception, response, spider):
        # Ürün sözlüğünü terminale basma, sadece kısa "DROP" mesajını göster
        return {
            'level': logging.WARNING,
            'msg': "DROP: %(exception)s | URL: %(url)s",
            'args': {
                'exception': exception,
                'url': item.get('url', '?')
            }
        }