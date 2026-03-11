import pymongo
client = pymongo.MongoClient("mongodb://localhost:27017/")
db = client["neuranovav_db"]
# Sadece BUGÜNKÜ fiyat tablosunu boşaltıyoruz
db["price_history"].delete_many({}) 
print("✅ Bugünün fiyat kayıtları silindi. Şimdi Playwright'ı kandırabiliriz!")