import time
import pymongo
import subprocess
import psutil
import sys
import os
from datetime import datetime, timezone

print("💂‍♂️ NeuraNovaV Bot Manager (Komutan) Başlatıldı! Emirler bekleniyor...")

MONGO_URI = "mongodb://localhost:27017/"
MONGO_DB = "neuranovav_db"

client = pymongo.MongoClient(MONGO_URI)
db = client[MONGO_DB]
cmd_col = db["bot_commands"]

# İşletim sisteminde çalışan süreçleri takip edeceğimiz sözlük
# Format: {"ana_bot": <subprocess.Popen object>, ...}
active_processes = {}

os.makedirs("logs", exist_ok=True)

def kill_process_tree(pid):
    """Verilen PID ve ona bağlı tüm alt süreçleri (Chrome sekmeleri dahil) acımasızca öldürür."""
    try:
        parent = psutil.Process(pid)
        for child in parent.children(recursive=True):
            child.kill()
        parent.kill()
    except psutil.NoSuchProcess:
        pass
    except Exception as e:
        print(f"Süreç öldürülürken hata: {e}")

def get_latest_job_id():
    """Playwright'ın hangi Scrapy oturumuna bağlanacağını bulur."""
    latest_job = db.jobs.find_one(sort=[("start_time", pymongo.DESCENDING)])
    return latest_job["job_id"] if latest_job else None

while True:
    try:
        # 1. MONGODB'DEN YENİ EMİRLERİ (PENDING) KONTROL ET
        bekleyen_emirler = list(cmd_col.find({"status": "pending"}))
        
        for emir in bekleyen_emirler:
            bot_id = emir["bot_id"]
            action = emir["action"]
            emir_id = emir["_id"]
            
            print(f"📨 Yeni Emir Alındı: Bot [{bot_id}] -> Komut [{action.upper()}]")
            
            if action == "start":
                # Eğer zaten çalışıyorsa pas geç
                if bot_id in active_processes and active_processes[bot_id].poll() is None:
                    cmd_col.update_one({"_id": emir_id}, {"$set": {"status": "already_running"}})
                    continue
                
                # Hangi botun hangi komutla çalışacağını belirle
                cmd_list = []
                log_file = os.path.join("logs", f"{bot_id}.log")
                
                if bot_id == "ana_bot":
                    cmd_list = [sys.executable, "-m", "scrapy", "crawl", "trendyol"]
                elif bot_id == "scrapy_fiyat":
                    cmd_list = [sys.executable, "-m", "scrapy", "crawl", "fiyat_guncelle"]
                elif bot_id in ["pw_hata", "pw_fiyat"]:
                    gorev_adi = "hata_coz" if bot_id == "pw_hata" else "fiyat_guncelle"
                    job_id = get_latest_job_id()
                    cmd_list = [sys.executable, "playwright_worker.py", "--gorev", gorev_adi]
                    if job_id:
                        cmd_list.extend(["--job_id", job_id])
                
                # Botu Başlat!
                with open(log_file, "a", encoding="utf-8") as f:
                    f.write(f"\n--- YENİ OTURUM: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ---\n")
                    proc = subprocess.Popen(cmd_list, stdout=f, stderr=subprocess.STDOUT, text=True)
                
                active_processes[bot_id] = proc
                
                # MongoDB'ye "Başarıyla Başlattım" raporu ver
                cmd_col.update_one(
                    {"_id": emir_id},
                    {"$set": {
                        "status": "running",
                        "pid": proc.pid,
                        "started_at": datetime.now(timezone.utc),
                        "is_running": True
                    }}
                )
                print(f"🚀 {bot_id} başarıyla sahaya sürüldü! (PID: {proc.pid})")
                
            elif action == "stop":
                # Botu durdur
                if bot_id in active_processes:
                    proc = active_processes[bot_id]
                    kill_process_tree(proc.pid)
                    del active_processes[bot_id]
                else:
                    # Belki de script yeniden başladı ama OS'de çalışıyor, DB'den PID bulup öldür
                    eski_kayit = cmd_col.find_one({"bot_id": bot_id, "is_running": True})
                    if eski_kayit and eski_kayit.get("pid"):
                        kill_process_tree(eski_kayit["pid"])
                
                # MongoDB'ye "Durduruldu" raporu ver
                cmd_col.update_one(
                    {"bot_id": bot_id, "is_running": True}, # Tüm aktif olanları kapat
                    {"$set": {
                        "status": "stopped",
                        "is_running": False,
                        "pid": None,
                        "stopped_at": datetime.now(timezone.utc)
                    }}
                )
                # Orijinal emri de tamamlandı işaretle
                cmd_col.update_one({"_id": emir_id}, {"$set": {"status": "done"}})
                print(f"🛑 {bot_id} komuta merkezinden gelen emirle durduruldu.")

        # 2. ÇALIŞAN BOTLARIN SAĞLIK KONTROLÜ (Kendi kendine kapanmış mı?)
        for b_id, p in list(active_processes.items()):
            if p.poll() is not None: # Bot kapanmış (hata veya başarıyla)
                print(f"🏁 {b_id} görevini tamamladı veya kapandı. (Çıkış kodu: {p.poll()})")
                cmd_col.update_many(
                    {"bot_id": b_id, "is_running": True},
                    {"$set": {
                        "is_running": False,
                        "status": "completed",
                        "pid": None,
                        "completed_at": datetime.now(timezone.utc)
                    }}
                )
                del active_processes[b_id]

        time.sleep(2) # CPU'yu yormamak için 2 saniye bekle ve tekrar kontrol et

    except Exception as e:
        print(f"❌ Bot Manager Hatası: {e}")
        time.sleep(5)