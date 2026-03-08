import urllib.request

print("Monosans deposundan güncel proxy avı başlatıldı...")

# Monosans'ın güncel HTTP proxy listesinin RAW (ham) linki
url = "https://raw.githubusercontent.com/monosans/proxy-list/main/proxies/http.txt"

try:
    # İnternetten proxy listesini indiriyoruz
    response = urllib.request.urlopen(url)
    veri = response.read().decode('utf-8')
    
    # Gelen veriyi satır satır ayırıyoruz
    proxies = veri.strip().split('\n')
    
    # Ücretsiz proxy'lerin birçoğu ölü olabileceği için sayıyı yüksek tutuyoruz (Örn: 200)
    secilen_proxyler = proxies[:200]
    
    # Bunları proxies.txt dosyamıza yazdırıyoruz
    with open("proxies.txt", "w", encoding="utf-8") as dosya:
        for p in secilen_proxyler:
            # Scrapy'nin anlaması için başına http:// ekliyoruz
            dosya.write(f"http://{p.strip()}\n")
            
    print(f"Başarılı! Tam {len(secilen_proxyler)} adet taptaze proxy 'proxies.txt' dosyasına kaydedildi.")
    print("Artık terminalden 'scrapy crawl trendyol' diyerek botu ateşleyebilirsin!")

except Exception as e:
    print("Proxy çekilirken bir hata oluştu:", e)