import pytest
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from trendyol_bot.items import clean_text

# ─── clean_text testleri ───────────────────────────────────────

def test_clean_text_normal():
    assert clean_text("  Mavi Tişört  ") == "Mavi Tişört"

def test_clean_text_coklu_bosluk():
    assert clean_text("Mavi   Tişört") == "Mavi Tişört"

def test_clean_text_emoji_kaldirir():
    assert clean_text("Güzel ürün 🎉") == "Güzel ürün"

def test_clean_text_none_gelirse():
    assert clean_text(None) is None

def test_clean_text_bos_string():
    assert clean_text("") == ""