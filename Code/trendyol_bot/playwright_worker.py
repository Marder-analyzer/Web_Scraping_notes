import sys
import os
# Bunlar en üstte olsun
sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')

import time
import pymongo
import re
import argparse
from datetime import datetime, timezone
from playwright.sync_api import sync_playwright
import gc

# --- MONGODB BAĞLANTISI ---
MONGO_URI = "mongodb://localhost:27017/"
MONGO_DB = "neuranovav_db"

client = pymongo.MongoClient(MONGO_URI)
db = client[MONGO_DB]
failed_col = db["failed_urls"]
products_col = db["products"]
prices_col = db["price_history"]

def update_pw_stats(job_id,gorev_adi, denenen, basarili):
    
    if not job_id:
        print("⚠️ RAPOR İPTAL: job_id verilmediği için veritabanına yazılamadı!")
        return
        
    simdi = datetime.now(timezone.utc)
    print(f"📊 [Rapor Gönderiliyor] Job ID: {job_id} | Görev: {gorev_adi} | Denenen: {denenen} | Başarılı: {basarili}")
    
    try:
        res = db.jobs.update_one(
            {"job_id": job_id},
            {
                "$inc": {
                    f"pw_{gorev_adi}_denenen": denenen,
                    f"pw_{gorev_adi}_basarili": basarili
                },
                "$set": {
                    "pw_last_ping": simdi
                }
            }
        )
        print(f"✅ [Veritabanı Yanıtı] Eşleşen Kayıt: {res.matched_count} | Güncellenen: {res.modified_count}")
    except Exception as e:
        print(f"⚠️ Rapor veritabanına yazılamadı: {e}")

def get_product_data_with_playwright(context, url):
    """Playwright ile ekrandan tüm verileri (Fiyat, Resimler, Özellikler vb.) eksiksiz söker."""
    page = context.new_page()
    try:
        page.goto(url, wait_until="load", timeout=30000)
        page.wait_for_timeout(2000) 
        
        sayfa_basligi = page.title()
        
        if "Robot" in sayfa_basligi or "Doğrulama" in sayfa_basligi:
            return None, "Captcha"
        if "Bulunamadı" in sayfa_basligi or "Tükendi" in sayfa_basligi:
            return None, "Tükendi"

        html_data = page.evaluate('''() => {
            let titleEl = document.querySelector('h1.pr-new-br span') || document.querySelector('h1');
            let title = titleEl ? titleEl.innerText.trim() : '';

            let priceEl = document.querySelector('.prc-dsc') || document.querySelector('.product-price-container') || document.querySelector('.prc-slg') || document.querySelector('.price');
            let priceText = priceEl ? priceEl.innerText.trim() : '';

            let catEls = document.querySelectorAll('a.product-detail-breadcrumbs-item');
            let category = Array.from(catEls).map(e => e.innerText.trim()).join(' > ');

            let imgEls = document.querySelectorAll('.product-image-container img, img[data-testid="image"]');
            let images = Array.from(imgEls).map(img => img.src).filter(src => src && !src.includes('data:image'));
            images = [...new Set(images)]; 

            let evalEl = document.querySelector('.reviews-summary-average-rating');
            let evaluation = evalEl ? evalEl.innerText.trim() : '-1';

            let evalLenEl = document.querySelector('a.reviews-summary-reviews-detail span.b') || document.querySelector('div.product-details-other-details a.reviews-summary-reviews-detail span.b');
            let evaluation_len = evalLenEl ? evalLenEl.innerText.replace(/[^0-9]/g, '') : '-1';

            let expEl = document.querySelector('div.product-info-content') || document.querySelector('div.content-description-container') || document.querySelector('div.detail-desc-container');
            let explanation = expEl ? expEl.innerText.replace(/\\s+/g, ' ').trim() : '';

            let attributes = {};
            document.querySelectorAll('div.attributes div.attribute-item').forEach(el => {
                let keyEl = el.querySelector('div.name');
                let valEl = el.querySelector('div.value');
                if(keyEl && valEl) {
                    attributes[keyEl.innerText.trim()] = valEl.innerText.trim();
                }
            });

            return {title, priceText, category, images, evaluation, evaluation_len, explanation, attributes};
        }''')

        if html_data['priceText']:
            fiyat_eslesmeleri = re.findall(r'(\d+(?:[.,]\d+)?)\s*TL', html_data['priceText'], re.IGNORECASE)
            if fiyat_eslesmeleri:
                saf_fiyat_metni = fiyat_eslesmeleri[-1]
                price_clean = float(saf_fiyat_metni.replace(".", "").replace(",", "."))
                
                eval_val = float(html_data['evaluation']) if html_data['evaluation'] != '-1' else -1
                eval_len_val = int(html_data['evaluation_len']) if html_data['evaluation_len'] != '-1' and html_data['evaluation_len'] != '' else -1
                final_title = html_data['title'] if html_data['title'] else sayfa_basligi.split("- Fiyatı")[0].strip()
                
                return {
                    "title": final_title, "category": html_data['category'] if html_data['category'] else "Bilinmiyor", 
                    "images": html_data['images'], "price": price_clean, "evaluation": eval_val, 
                    "evaluation_len": eval_len_val, "explanation": html_data['explanation'], "attributes": html_data['attributes']
                }, "OK"
                
        return None, "Fiyat Bulunamadı"
            
    except Exception as e:
        return None, f"Hata: {str(e)[:50]}"
    
    finally:
        page.close()

def mod1_kuyruk_temizle(context,job_id):
    """SADECE fiyatı eksik olan hatalı URL'leri kurtarır."""
    update_pw_stats(job_id, "hata_coz", 0, 0)
    while True:
        bekleyenler = list(failed_col.find({
            "cozuldu": False, 
            "hata_tipi": {"$in": ["price_missing", "HTTP_403", "HTTP_429"]}
        }).limit(10))
        
        if not bekleyenler:
            print("\n✅ Hata kuyruğunda 'Fiyatı Eksik' ürün kalmadı. İşlem tamamlandı.")
            break
            
        print(f"\n[MOD 1] ⏳ Kuyruktan {len(bekleyenler)} adet URL kurtarılıyor...")
        simdi = datetime.now(timezone.utc)
        today_str = simdi.strftime("%Y-%m-%d")
        
        basarili_sayisi = 0 
        deneme_sayisi = len(bekleyenler) 
        
        for item in bekleyenler:
            url = item["url"]
            data, status = get_product_data_with_playwright(context, url)
            
            if data and data.get("price"):
                products_col.update_one({"url": url}, {"$set": {"title": data["title"], "category": data["category"], "images": data["images"], "explanation": data["explanation"], "attributes": data["attributes"], "last_seen": simdi, "scrape_method": "playwright"}}, upsert=True)
                prices_col.update_one({"url": url, "date": today_str}, {"$set": {"price": data["price"], "evaluation": data["evaluation"], "evaluation_len": data["evaluation_len"]}}, upsert=True)
                failed_col.update_one({"_id": item["_id"]}, {"$set": {"cozuldu": True, "cozulme_tarihi": simdi}})
                basarili_sayisi += 1
                print(f"  🟢 KURTARILDI: {data['title'][:30]}... | Fiyat: {data['price']} TL")
            else:
                failed_col.update_one(
                    {"_id": item["_id"]},
                    {
                        "$inc": {"playwright_deneme": 1},
                        "$set": {"son_hata_sebebi": status},
                        "$push": {
                            "attempts": {
                                "$each": [{"ts": simdi, "status": status, "worker": "playwright"}],
                                "$slice": -20  # FIX: array şişmez
                            }
                        }
                    }
                )
                print(f"  🔴 BAŞARISIZ: {status} -> {url.split('?')[0][-30:]}")
        update_pw_stats(job_id, "hata_coz", deneme_sayisi, basarili_sayisi)
def mod2_fiyat_guncelle(context, job_id):
    """SADECE veritabanındaki kayıtlı ürünlerin bugünkü fiyatlarını günceller."""
    update_pw_stats(job_id, "fiyat_guncelle", 0, 0)
    while True:
        simdi = datetime.now(timezone.utc)
        today_str = simdi.strftime("%Y-%m-%d")
        
        guncellenen_urller = prices_col.distinct("url", {"date": today_str})
        guncellenecekler = list(products_col.find({
            "url": {"$nin": guncellenen_urller},
            "scrape_method": "playwright"
        }, {"url": 1}).limit(10))
        
        if not guncellenecekler:
            print("\n✅ Tüm kayıtlı ürünlerin bugünkü fiyatları güncel! İşlem tamamlandı.")
            break
            
        print(f"\n[MOD 2] 🔄 {len(guncellenecekler)} kayıtlı ürünün fiyatı güncelleniyor...")
        
        basarili_sayisi = 0 
        deneme_sayisi = len(guncellenecekler) 
        
        for item in guncellenecekler:
            url = item["url"]
            data, status = get_product_data_with_playwright(context, url)
            
            if data and data.get("price"):
                products_col.update_one({"url": url}, {"$set": {"last_seen": simdi, "images": data["images"], "explanation": data["explanation"], "attributes": data["attributes"], "scrape_method": "playwright"}})
                prices_col.update_one({"url": url, "date": today_str}, {"$set": {"price": data["price"], "evaluation": data["evaluation"], "evaluation_len": data["evaluation_len"]}}, upsert=True)
                basarili_sayisi += 1
                print(f"  🔵 GÜNCELLENDİ: Fiyat -> {data['price']} TL | {data['title'][:30]}...")
            else:
                print(f"  🟠 PAS GEÇİLDİ: {status} -> {url.split('?')[0][-30:]}")
        update_pw_stats(job_id, "fiyat_guncelle", deneme_sayisi, basarili_sayisi)
def mod3_liste_kurtar(context, job_id):
    """Liste sayfalarındaki (pi=) 403'lü URL'lere girer, 24 ürünü bulup kazır."""
    update_pw_stats(job_id, "hata_coz", 0, 0)
    
    while True:
        # Önce kurtarılmamış liste sayfalarını al
        bekleyenler = list(failed_col.find({
            "cozuldu": False,
            "sayfa_turu": "liste"
        }).limit(5))
        
        if not bekleyenler:
            print("\n✅ Kurtarılacak liste sayfası kalmadı.")
            break
        
        print(f"\n[MOD 3] 🔍 {len(bekleyenler)} liste sayfası kurtarılıyor...")
        simdi = datetime.now(timezone.utc)
        today_str = simdi.strftime("%Y-%m-%d")
        
        basarili_sayisi = 0
        deneme_sayisi = 0
        
        for item in bekleyenler:
            liste_url = item["url"]
            print(f"\n  📋 Liste sayfasına giriliyor: {liste_url[-60:]}")
            
            try:
                page = context.new_page()  # LİSTE İÇİN GEÇİCİ SEKME AÇ
                page.goto(liste_url, wait_until="load", timeout=30000)
                page.wait_for_timeout(2000)
                
                # Sayfadaki 24 ürün linkini topla
                urun_linkleri = page.evaluate('''() => {
                    let links = document.querySelectorAll("a.product-card");
                    return Array.from(links).map(a => a.href).filter(h => h.includes("trendyol.com"));
                }''')
                
                page.close()
                
                if not urun_linkleri:
                    print(f"  ⚠️ Liste sayfasında ürün linki bulunamadı.")
                    failed_col.update_one(
                        {"_id": item["_id"]},
                        {"$set": {"cozuldu": True, "son_hata_sebebi": "link_yok", "cozulme_tarihi": simdi}}
                    )
                    continue
                
                print(f"  ✅ {len(urun_linkleri)} ürün linki bulundu, kazınıyor...")
                
                for urun_url in urun_linkleri:
                    deneme_sayisi += 1
                    data, status = get_product_data_with_playwright(page, urun_url)
                    
                    if data and data.get("price"):
                        products_col.update_one(
                            {"url": urun_url},
                            {"$set": {
                                "title": data["title"], "category": data["category"],
                                "images": data["images"], "explanation": data["explanation"],
                                "attributes": data["attributes"], "last_seen": simdi,
                                "scrape_method": "playwright"
                            }},
                            upsert=True
                        )
                        prices_col.update_one(
                            {"url": urun_url, "date": today_str},
                            {"$set": {
                                "price": data["price"], "evaluation": data["evaluation"],
                                "evaluation_len": data["evaluation_len"]
                            }},
                            upsert=True
                        )
                        # failed_urls'deki ürün hatasını da çözdü işaretle
                        failed_col.update_one(
                            {"url": urun_url},
                            {"$set": {"cozuldu": True, "cozulme_tarihi": simdi}},
                        )
                        basarili_sayisi += 1
                        print(f"    🟢 {data['title'][:35]}... | {data['price']} TL")
                    else:
                        print(f"    🔴 {status} | {urun_url[-40:]}")
                
                # Liste sayfasını çözüldü işaretle
                failed_col.update_one(
                    {"_id": item["_id"]},
                    {"$set": {"cozuldu": True, "cozulme_tarihi": simdi}}
                )
                
            except Exception as e:
                print(f"  ❌ Liste sayfası hatası: {str(e)[:60]}")
                failed_col.update_one(
                    {"_id": item["_id"]},
                    {"$inc": {"playwright_deneme": 1}, "$set": {"son_hata_sebebi": str(e)[:60]}}
                )
        
        update_pw_stats(job_id, "hata_coz", deneme_sayisi, basarili_sayisi)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="NeuraNovaV Playwright İşçisi")
    parser.add_argument("--gorev", choices=['hata_coz', 'fiyat_guncelle', 'liste_kurtar'], required=True, 
                        help="Hangi işlemin yapılacağını seçin")
    parser.add_argument("--job_id", default=None,
                        help="İlişkilendirilecek Scrapy job_id (opsiyonel)")
    
    args = parser.parse_args()

    print(f"NeuraNovaV Playwright İşçisi Başlatıldı! | Görev: {args.gorev.upper()}")
    if args.job_id:
        print(f"   Job ID: {args.job_id}")
    else:
        print(f"   job_id verilmedi — istatistikler jobs koleksiyonuna yazılmayacak")
    
    try:
        with sync_playwright() as p:
            print("🔄 [SİSTEM] Tarayıcı Anti-Leak ve Endüstriyel modda başlatılıyor...")
            browser = p.chromium.launch(
                headless=True,
                args=[
                    "--disable-dev-shm-usage",             # Linux RAM kilitlenmesini önler
                    "--js-flags=--max-old-space-size=512", # RAM limitini 512MB'a kilitler
                    "--disk-cache-size=1",                 # Disk %100 sorununu çözer (Diske yazmayı engeller)
                    "--disable-disk-cache",
                    "--disable-crash-reporter",
                    "--disable-logging",
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-gpu",
                    "--disable-software-rasterizer",
                    "--disable-background-networking",
                    "--disable-extensions",
                    "--disable-default-apps",
                    "--blink-settings=imagesEnabled=false" # Görüntüleri indirmez, ağ ve RAM tasarrufu sağlar
                ]
            )
            context = browser.new_context(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/122.0.0.0 Safari/537.36")
            
            # DİKKAT: Burada tekil bir 'page' oluşturmuyoruz! 
            # Context'i gönderiyoruz ki fonksiyonlar içeride kendi sekmelerini açıp kapatabilsin.
            
            if args.gorev == 'hata_coz':
                mod1_kuyruk_temizle(context, args.job_id)
            elif args.gorev == 'fiyat_guncelle':
                mod2_fiyat_guncelle(context, args.job_id)
            elif args.gorev == 'liste_kurtar':
                mod3_liste_kurtar(context, args.job_id)
                
            context.close()
            browser.close()
            
            # RAM'de kalan Python çöplerini zorla temizle
            gc.collect()
            print("🧹 [SİSTEM] Tarayıcı tamamen imha edildi. RAM ve Disk OS'e iade edildi.")
            
    except KeyboardInterrupt:
        print("\n🛑 Kullanıcı tarafından durduruldu.")
    except Exception as e:
        print(f"\n❌ Kritik Hata: {e}")