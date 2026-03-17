import pytest
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from trendyol_bot.spiders.trendyol import TrendyolSpider

# ─── clean_url testleri ───────────────────────────────────────

def test_clean_url_gereksiz_params_silinir():
    url = "https://www.trendyol.com/pd/test?boutiqueId=61&merchantId=123&pi=1&page=2"
    result = TrendyolSpider.clean_url(url)
    assert "boutiqueId=61" in result
    assert "merchantId=123" in result
    assert "pi=1" not in result
    assert "page=2" not in result

def test_clean_url_temiz_url_degismez():
    url = "https://www.trendyol.com/pd/test?boutiqueId=61&merchantId=123"
    result = TrendyolSpider.clean_url(url)
    assert "boutiqueId=61" in result
    assert "merchantId=123" in result

def test_clean_url_parametresiz():
    url = "https://www.trendyol.com/pd/test"
    result = TrendyolSpider.clean_url(url)
    assert result == url