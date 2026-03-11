import time
import pymongo
import re
import argparse
from datetime import datetime, timezone
from playwright.sync_api import sync_playwright

# --- MONGODB BAĞLANTISI ---
MONGO_URI = "mongodb://localhost:27017/"
MONGO_DB = "neuranovav_db"

client = pymongo.MongoClient(MONGO_URI)
db = client[MONGO_DB]
failed_col = db["failed_urls"]
products_col = db["products"]
prices_col = db["price_history"]

def update_pw_stats(gorev_adi, denenen, basarili):
    
    # En son çalışan job'ı bul
    latest_job = db.jobs.find_one(sort=[("start_time", pymongo.DESCENDING)])
    
    if latest_job:
        job_id = latest_job["_id"]
        # Hangi görevi çalıştırıyorsa onun sayaçlarını artır
        db.jobs.update_one(
            {"_id": job_id},
            {
                "$inc": {
                    f"pw_{gorev_adi}_denenen": denenen,
                    f"pw_{gorev_adi}_basarili": basarili
                },
                "$set": {
                    "pw_last_ping": datetime.now(timezone.utc)
                }
            }
        )

def get_product_data_with_playwright(page, url):
    """Playwright ile ekrandan tüm verileri (Fiyat, Resimler, Özellikler vb.) eksiksiz söker."""
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

def mod1_kuyruk_temizle(page):
    """SADECE fiyatı eksik olan hatalı URL'leri kurtarır."""
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
            data, status = get_product_data_with_playwright(page, url)
            
            if data and data.get("price"):
                products_col.update_one({"url": url}, {"$set": {"title": data["title"], "category": data["category"], "images": data["images"], "explanation": data["explanation"], "attributes": data["attributes"], "last_seen": simdi, "scrape_method": "playwright"}}, upsert=True)
                prices_col.update_one({"url": url, "date": today_str}, {"$set": {"price": data["price"], "evaluation": data["evaluation"], "evaluation_len": data["evaluation_len"]}}, upsert=True)
                failed_col.update_one({"_id": item["_id"]}, {"$set": {"cozuldu": True, "cozulme_tarihi": simdi}})
                basarili_sayisi += 1
                print(f"  🟢 KURTARILDI: {data['title'][:30]}... | Fiyat: {data['price']} TL")
            else:
                failed_col.update_one({"_id": item["_id"]}, {"$inc": {"playwright_deneme": 1}, "$set": {"son_hata_sebebi": status}})
                print(f"  🔴 BAŞARISIZ: {status} -> {url.split('?')[0][-30:]}")
        update_pw_stats("hata_coz", deneme_sayisi, basarili_sayisi)
def mod2_fiyat_guncelle(page):
    """SADECE veritabanındaki kayıtlı ürünlerin bugünkü fiyatlarını günceller."""
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
            data, status = get_product_data_with_playwright(page, url)
            
            if data and data.get("price"):
                products_col.update_one({"url": url}, {"$set": {"last_seen": simdi, "images": data["images"], "explanation": data["explanation"], "attributes": data["attributes"]}})
                prices_col.update_one({"url": url, "date": today_str}, {"$set": {"price": data["price"], "evaluation": data["evaluation"], "evaluation_len": data["evaluation_len"]}}, upsert=True)
                basarili_sayisi += 1
                print(f"  🔵 GÜNCELLENDİ: Fiyat -> {data['price']} TL | {data['title'][:30]}...")
            else:
                print(f"  🟠 PAS GEÇİLDİ: {status} -> {url.split('?')[0][-30:]}")
        update_pw_stats("fiyat_guncelle", deneme_sayisi, basarili_sayisi)
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="NeuraNovaV Playwright İşçisi")
    parser.add_argument("--gorev", choices=['hata_coz', 'fiyat_guncelle'], required=True, 
                        help="Hangi işlemin yapılacağını seçin (hata_coz veya fiyat_guncelle)")
    args = parser.parse_args()

    print(f"🚀 NeuraNovaV Playwright İşçisi Başlatıldı! | Görev: {args.gorev.upper()}")
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True) 
        context = browser.new_context(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/122.0.0.0 Safari/537.36")
        page = context.new_page()
        
        try:
            if args.gorev == 'hata_coz':
                mod1_kuyruk_temizle(page)
            elif args.gorev == 'fiyat_guncelle':
                mod2_fiyat_guncelle(page)
                
        except KeyboardInterrupt:
            print("\n🛑 Kullanıcı tarafından durduruldu.")
        finally:
            context.close()
            browser.close()
            print("👋 Tarayıcı güvenle kapatıldı.")
            
    