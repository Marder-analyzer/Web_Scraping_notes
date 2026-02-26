# Define your item pipelines here
#
# Don't forget to add your pipeline to the ITEM_PIPELINES setting
# See: https://docs.scrapy.org/en/latest/topics/item-pipeline.html


# useful for handling different item types with a single interface
from itemadapter import ItemAdapter
import re

class TrendyolBotPipeline:
    def process_item(self, item, spider):
        # 1. FİYAT (PRICE) TEMİZLİĞİ VE DÖNÜŞTÜRME
        
        price_raw = item.get('price', '-1')
        if isinstance(price_raw, list):
            price_raw = price_raw[0] if price_raw else '-1'
            
        price_str = str(price_raw).strip()
        
        if price_str in ['-1', '', 'Yok', 'None']:
            item['price'] = -1
        else:
            try:
                clean_price = price_str.upper().replace('TL', '').strip()
                if ',' in clean_price:
                    clean_price = clean_price.replace('.', '').replace(',', '.')
                item['price'] = float(clean_price)
                
            except Exception as e:
                spider.logger.error(f"Fiyat donusturulemedi: {price_str} Hata: {e}")
                item['price'] = price_str

            
            
        # 2. DEĞERLENDİRME PUANI (EVALUATION) TEMİZLİĞİ
        
        eval_raw = item.get('evaluation', '-1')
        if isinstance(eval_raw, list):
            eval_raw = eval_raw[0] if eval_raw else '-1'
            item['evaluation'] = eval_raw
            
        eval_str = str(eval_raw).strip()
        
        if eval_str in ['-1', '', 'Yok', 'None', '0.0', '0']:
            item['evaluation'] = -1
        else:
            try:
                item['evaluation'] = round(float(eval_str.replace(',', '.')), 1)
            except Exception as e:
                spider.logger.warning(f"Evaluation donusturulemedi, eski hali birakildi: {eval_str}")
                item['evaluation'] = eval_str
            
            
        # 3. DEĞERLENDİRME SAYISI (EVALUATION_LEN) TEMİZLİĞİ

        eval_len_raw = item.get('evaluation_len', '-1')
        if isinstance(eval_len_raw, list):
            eval_len_raw = eval_len_raw[0] if eval_len_raw else '-1'
            item['evaluation_len'] = eval_len_raw
            
        eval_len_str = str(eval_len_raw).strip()
        
        if eval_len_str in ['-1', '', 'Yok', 'None', '0']:
            item['evaluation_len'] = -1
        else:
            try:
                clean_len_str = eval_len_str.replace('.', '')
                numbers = re.findall(r'\d+', clean_len_str)
                if numbers:
                    item['evaluation_len'] = int(numbers[0])
                else:
                    item['evaluation_len'] = -1
                    
            except Exception as e:
                spider.logger.warning(f"Evaluation Len donusturulemedi, eski hali birakildi: {eval_len_str}")
                item['evaluation_len'] = eval_len_str

        return item
