import pytest
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from unittest.mock import MagicMock, patch
from trendyol_bot.pipelines import TrendyolBotPipeline

@pytest.fixture
def pipeline():
    p = TrendyolBotPipeline.__new__(TrendyolBotPipeline)
    p.stats = {"drop_fiyatsiz": 0, "drop_hata": 0}
    return p

# ─── _fiyat_temizle testleri ──────────────────────────────────

def test_fiyat_normal(pipeline):
    assert pipeline._fiyat_temizle("199.99") == 199.99

def test_fiyat_turkce_format(pipeline):
    assert pipeline._fiyat_temizle("1.250,99") == 1250.99

def test_fiyat_tl_ile(pipeline):
    assert pipeline._fiyat_temizle("299,00 TL") == 299.0

def test_fiyat_bos_raise(pipeline):
    with pytest.raises(ValueError):
        pipeline._fiyat_temizle("")

def test_fiyat_gecersiz_raise(pipeline):
    with pytest.raises(ValueError):
        pipeline._fiyat_temizle("abc")

# ─── _sayi_temizle testleri ───────────────────────────────────

def test_sayi_float(pipeline):
    assert pipeline._sayi_temizle("4.8", float_mi=True, varsayilan=-1) == 4.8

def test_sayi_int(pipeline):
    assert pipeline._sayi_temizle("1250", float_mi=False, varsayilan=-1) == 1250

def test_sayi_bos(pipeline):
    assert pipeline._sayi_temizle("-1", float_mi=True, varsayilan=-1) == -1

def test_sayi_none(pipeline):
    assert pipeline._sayi_temizle("", float_mi=False, varsayilan=-1) == -1

def test_sayi_tr_format(pipeline):
    assert pipeline._sayi_temizle("4,7", float_mi=True, varsayilan=-1) == 4.7