import time
import pymongo
import subprocess
import psutil
import sys
import os
from datetime import datetime, timezone

import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import json
import pytz
from dotenv import load_dotenv


load_dotenv()
MAIL_SENDER = os.getenv("MAIL_SENDER", "")
MAIL_APP_PASS = os.getenv("MAIL_APP_PASS", "")
TR_TZ = pytz.timezone("Europe/Istanbul")

def notify_bot_status(bot_id, is_start=True, exit_code=None):
    """Dashboard'daki mevcut HTML mail yapısını kullanarak şık bildirimler atar."""
    if bot_id == "ana_bot":
        return
    # Kayıtlı maili bul
    if not os.path.exists("saved_mails.json"): return
    with open("saved_mails.json", "r") as f:
        mails = json.load(f)
    if not mails: return
    target_mail = mails[0]

    zaman = datetime.now(TR_TZ).strftime('%d/%m/%Y %H:%M:%S')

    # Duruma göre renk, ikon ve mesaj belirle
    if is_start:
        subject = f"🚀 NeuraNovaV: {bot_id.upper()} Sahaya Sürüldü"
        renk = "#1565c0"  # Mavi
        durum_metni = "🟢 BAŞLATILDI"
        mesaj = "Bot başarıyla sahaya sürüldü ve veri toplamaya/işlemeye başladı."
    else:
        if exit_code == 0:
            subject = f"🏁 NeuraNovaV: {bot_id.upper()} Görevi Tamamladı"
            renk = "#2e7d32"  # Yeşil
            durum_metni = "✅ BAŞARIYLA TAMAMLANDI (İş Kalmadı)"
            mesaj = "Bot atanan tüm işleri bitirdi ve güvenli bir şekilde sistemden ayrıldı."
        elif exit_code == "Bilinmiyor":
            subject = f"🛑 NeuraNovaV: {bot_id.upper()} Durduruldu"
            renk = "#e65100"  # Turuncu
            durum_metni = "🛑 MANUEL DURDURULDU"
            mesaj = "Bot kullanıcı tarafından Dashboard üzerinden veya sistem tarafından durduruldu."
        else:
            subject = f"🚨 NeuraNovaV: {bot_id.upper()} ÇÖKTÜ!"
            renk = "#c62828"  # Kırmızı
            durum_metni = f"❌ HATA İLE ÇÖKTÜ (Çıkış Kodu: {exit_code})"
            mesaj = "Bot beklenmedik bir hatayla karşılaştı ve kapandı. Lütfen Dashboard loglarını kontrol edin."

    # Dashboard tarzı şık HTML Gövdesi
    html_body = f"""
    <html><body style="font-family:Arial,sans-serif;background:#f4f4f4;padding:20px">
    <div style="max-width:500px;margin:auto;background:white;border-radius:12px;padding:24px;box-shadow:0 2px 8px #ccc">
        <h2 style="color:{renk}; margin-top:0;">{durum_metni}</h2>
        <p style="color:#555; font-size:16px;"><b>🤖 Bot ID:</b> {bot_id}</p>
        <p style="color:#555; font-size:16px;"><b>📅 Zaman:</b> {zaman}</p>
        <hr style="border:1px solid #eee; margin:15px 0;"/>
        <p style="color:#333; font-size:15px;">{mesaj}</p>
        <p style="color:#888;font-size:12px; margin-top:20px;">NeuraNovaV Komuta Merkezi Otomatik Bildirimi</p>
    </div></body></html>
    """

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = f"NeuraNovaV Komuta <{MAIL_SENDER}>"
        msg["To"] = target_mail
        msg.attach(MIMEText(html_body, "html"))

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(MAIL_SENDER, MAIL_APP_PASS)
            server.sendmail(MAIL_SENDER, target_mail, msg.as_string())
        print(f"📧 Durum Maili Gönderildi: {bot_id} -> {durum_metni}")
    except Exception as e:
        print(f"⚠️ Mail gönderilemedi: {e}")


son_ram_maili = 0

def slaughter_zombies():
    """Görünmez (Headless) Chrome'ları ve asılı kalan Playwright işçilerini acımasızca katleder."""
    killed_count = 0
    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            name = (proc.info.get('name') or "").lower()
            cmdline = proc.info.get('cmdline') or []
            cmd_str = " ".join(cmdline).lower()

            if (('chrome' in name or 'chromium' in name) and '--headless' in cmd_str) or \
               ('python' in name and 'playwright_worker.py' in cmd_str):
                proc.kill()
                killed_count += 1
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    return killed_count


son_ram_maili = 0
son_acil_kapatma = 0
def check_ram_and_alert():
    global son_ram_maili, son_acil_kapatma
    ram_yuzde = psutil.virtual_memory().percent

    
    # --- KADEME 1: %80 — Uyarı Maili ---
    if ram_yuzde > 80.0 and (time.time() - son_ram_maili > 3600):
        print(f" RAM %{ram_yuzde} — Uyarı maili atılıyor...")
        try:
            with open("saved_mails.json", "r") as f:
                target_mail = json.load(f)[0]
            html_body = f"""<html><body style="font-family:Arial,sans-serif;padding:20px">
            <div style="max-width:500px;margin:auto;background:white;border-radius:12px;padding:24px;border-left:8px solid #f57c00">
                <h2 style="color:#f57c00"> RAM UYARISI: %{ram_yuzde:.1f}</h2>
                <p>Sistem belleği <b>%{ram_yuzde:.1f}</b> dolulukta. Playwright botları çalışıyorsa yakında otomatik kapatılabilir.</p>
                <p>%92'yi geçerse tüm botlar otomatik durdurulacak.</p>
            </div></body></html>"""
            msg = MIMEMultipart("alternative")
            msg["Subject"] = f" NeuraNovaV RAM Uyarısı: %{ram_yuzde:.1f}"
            msg["From"] = f"NeuraNovaV Komuta <{MAIL_SENDER}>"
            msg["To"] = target_mail
            msg.attach(MIMEText(html_body, "html"))
            with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
                server.login(MAIL_SENDER, MAIL_APP_PASS)
                server.sendmail(MAIL_SENDER, target_mail, msg.as_string())
            son_ram_maili = time.time()
            print(" RAM uyarı maili gönderildi.")
        except Exception as e:
            son_ram_maili = time.time()
            print(f" RAM maili gönderilemedi: {e}")

    # --- KADEME 2: %92 — Acil Otomatik Kapatma ---
    if ram_yuzde > 92.0 and (time.time() - son_acil_kapatma > 1800):
        print(f" KRİTİK: RAM %{ram_yuzde:.1f}! ACİL KAPATMA BAŞLIYOR...")
        son_acil_kapatma = time.time()

        # 1. Tüm PW botlarını DB üzerinden durdur
        pw_botlar = ["pw_hata", "pw_fiyat", "pw_liste"]
        for pw_bot in pw_botlar:
            kayit = cmd_col.find_one({"bot_id": pw_bot, "is_running": True})
            if kayit and kayit.get("pid"):
                kill_process_tree(kayit["pid"])
                cmd_col.update_one(
                    {"bot_id": pw_bot},
                    {"$set": {"is_running": False, "status": "killed_ram", "pid": None}}
                )
                print(f" {pw_bot} RAM koruma nedeniyle kapatıldı.")

        # 2. Zombi chrome'ları temizle
        oldurulen = slaughter_zombies()

        # 3. Python GC
        import gc
        gc.collect()

        # 4. Windows'ta WSL'yi kapat
        if os.name == 'nt':
            try:
                subprocess.run(["wsl", "--shutdown"], timeout=10, capture_output=True)
                print("🔧 WSL kapatıldı, RAM iade edildi.")
            except Exception:
                pass
        
        else:  # Linux/Ubuntu
            try:
                # Disk cache'i temizle (sudo gerektirir, sudoers'a eklenmiş olmalı)
                subprocess.run(["sync"], timeout=5, capture_output=True)
                subprocess.run(["sh", "-c", "echo 3 > /proc/sys/vm/drop_caches"], timeout=5, capture_output=True)
                print("🔧 Linux bellek önbelleği temizlendi.")
            except Exception:
                pass

        print(f"✅ Acil kapatma tamamlandı. {oldurulen} zombi temizlendi.")

        # 5. Rapor maili
        try:
            with open("saved_mails.json", "r") as f:
                target_mail = json.load(f)[0]
            html_body = f"""<html><body style="font-family:Arial,sans-serif;padding:20px">
            <div style="max-width:500px;margin:auto;background:white;border-radius:12px;padding:24px;border-left:8px solid #c62828">
                <h2 style="color:#c62828">🚨 ACİL KAPATMA GERÇEKLEŞTİ</h2>
                <p>RAM <b>%{ram_yuzde:.1f}</b> seviyesine ulaştı.</p>
                <p>Tüm Playwright botları otomatik durduruldu, {oldurulen} zombi temizlendi.</p>
                <p>Scrapy devam ediyor. Dashboard'dan botları yeniden başlatabilirsiniz.</p>
            </div></body></html>"""
            msg = MIMEMultipart("alternative")
            msg["Subject"] = f"🚨 NeuraNovaV ACİL KAPATMA: RAM %{ram_yuzde:.1f}"
            msg["From"] = f"NeuraNovaV Komuta <{MAIL_SENDER}>"
            msg["To"] = target_mail
            msg.attach(MIMEText(html_body, "html"))
            with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
                server.login(MAIL_SENDER, MAIL_APP_PASS)
                server.sendmail(MAIL_SENDER, target_mail, msg.as_string())
        except Exception as e:
            print(f"⚠️ Acil kapatma maili gönderilemedi: {e}")

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
os.makedirs("crawls", exist_ok=True)

def sync_with_db():
    """Manager açıldığında DB'de 'çalışıyor' görünen botları kontrol eder."""
    running_in_db = list(cmd_col.find({"is_running": True}))
    for bot in running_in_db:
        pid = bot.get("pid")
        bot_id = bot.get("bot_id")
        if pid and psutil.pid_exists(pid):
            if bot_id not in active_processes:
                active_processes[bot_id] = pid 
                print(f"🔄 Zombi bot bulundu ve kontrol altına alındı: {bot_id} (PID: {pid})")
        else:
            cmd_col.update_one({"bot_id": bot_id}, {"$set": {"is_running": False, "status": "stopped"}})

# Döngüden önce mutlaka çalıştır
sync_with_db()



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

def get_actual_job_id():
    """
    Playwright işçilerinin hangi Scrapy oturumuna (Job) 
    veri yazacağını belirlemek için en taze ID'yi getirir.
    """
    latest = db.jobs.find_one(sort=[("start_time", pymongo.DESCENDING)])
    return latest["job_id"] if latest else None

def close_active_jobs_in_db(bot_id, manual_stop=False):
    """Sadece ana botlar kapandığında genel durumu günceller, yan botlar genel durumu bozamaz."""
    # Playwright (Yan) botları ana durumu değiştiremez! Filtre:
    if bot_id != "ana_bot":   # Sadece ana_bot ana durumu kapatabilir
        return
        
    # Manuel durdurulduysa durumu farklı yaz
    yeni_durum = "Manuel Durduruldu" if manual_stop else "Tamamlandı"
    
    try:
        db.jobs.update_many(
            {"status": "Running"}, 
            {"$set": {
                "status": yeni_durum, 
                "end_time": datetime.now(timezone.utc)
            }}
        )
    except Exception as e:
        pass
# ---------------------------

while True:
    try:
        
        check_ram_and_alert()
        # 1. MONGODB'DEN YENİ EMİRLERİ (PENDING) KONTROL ET
        bekleyen_emirler = list(cmd_col.find({
            "$or": [
                {"status": "pending"},
                {"action": "force_stop", "stop_processed": False}
            ]
        }))
        
        for emir in bekleyen_emirler:
            bot_id = emir["bot_id"]
            action = emir["action"]
            emir_id = emir["_id"]
            
            
            if action == "panic_kill":
                print("🚨 PANİK BUTONUNA BASILDI! Sistemdeki tüm zombiler temizleniyor...")
                oldurulen = slaughter_zombies()
                print(f"💀 Temizlik Tamamlandı! {oldurulen} adet gizli süreç yokedildi.")
                
                cmd_col.update_one({"_id": emir_id}, {"$set": {"status": "processed", "stop_processed": True}})
                continue
            
            # --- ZORLA KAPATMA (FORCE STOP) MANTIĞI ---
            if action == "force_stop":
                print(f"🚨 ACİL İMHA EMRİ: {bot_id} için fiş çekiliyor...")
                
                # DB'den botun güncel PID'sini çek
                bot_info = cmd_col.find_one({"bot_id": bot_id})
                target_pid = bot_info.get("pid")
                
                if target_pid and psutil.pid_exists(target_pid):
                    print(f"💀 PID {target_pid} imha ediliyor...")
                    kill_process_tree(target_pid)
                
                # Veritabanını temizle
                cmd_col.update_one(
                    {"bot_id": bot_id},
                    {"$set": {
                        "is_running": False,
                        "status": "force_killed",
                        "pid": None,
                        "action": "idle",
                        "stop_processed": True
                    }}
                )
                if bot_id in active_processes:
                    del active_processes[bot_id]
                
                print(f"💀 {bot_id} tamamen sistemden kazındı.")
                continue # Bu emir bitti, sıradakine geç
            
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
                    cmd_list = [sys.executable, "-m", "scrapy", "crawl", "trendyol", "-s", "JOBDIR=crawls/trendyol_state"]
                elif bot_id == "scrapy_fiyat":
                    cmd_list = [sys.executable, "-m", "scrapy", "crawl", "fiyat_guncelle"]
                elif bot_id in ["pw_hata", "pw_fiyat", "pw_liste"]:
                    if bot_id == "pw_hata":
                        gorev_adi = "hata_coz"
                    elif bot_id == "pw_fiyat":
                        gorev_adi = "fiyat_guncelle"
                    elif bot_id == "pw_liste":
                        gorev_adi = "liste_kurtar"
                    job_id = get_latest_job_id()
                    cmd_list = [sys.executable, "playwright_worker.py", "--gorev", gorev_adi]
                    if job_id:
                        cmd_list.extend(["--job_id", job_id])
                
                print(f"DEBUG cmd_list: {cmd_list}")
                print(f"DEBUG log_file: {log_file}")
                proje_yolu = os.path.dirname(os.path.abspath(__file__))
                # Botu Başlat!
                f = open(log_file, "a", encoding="utf-8", errors="ignore")
                f.write(f"\n--- YENİ OTURUM: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ---\n")
                f.flush()
                
                proc = subprocess.Popen(
                    cmd_list, 
                    stdout=f, 
                    stderr=subprocess.STDOUT, 
                    text=True,
                    cwd=proje_yolu  # <--- TAM OLARAK BURAYA BU SATIRI EKLE
                )
                
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
                notify_bot_status(bot_id, is_start=True)
                
            elif action == "stop":
                # Botu durdur
                if bot_id in active_processes:
                    proc = active_processes[bot_id]
                    kill_process_tree(proc.pid if hasattr(proc, 'pid') else proc)
                    del active_processes[bot_id]
                    
                
                
                else:
                    # Belki de script yeniden başladı ama OS'de çalışıyor, DB'den PID bulup öldür
                    eski_kayit = cmd_col.find_one({"bot_id": bot_id, "is_running": True})
                    if eski_kayit and eski_kayit.get("pid"):
                        kill_process_tree(eski_kayit["pid"])
                
                # MongoDB'ye "Durduruldu" raporu ver
                cmd_col.update_many({"bot_id": bot_id, "is_running": True}, {
                    "$set": {
                        "is_running": False, 
                        "status": "stopped", 
                        "stopped_at": datetime.now(timezone.utc)
                    }
                })
                # Orijinal emri de tamamlandı işaretle
                cmd_col.update_one({"_id": emir_id}, {"$set": {"status": "processed", "stop_processed": True}})

                print(f"🛑 {bot_id} komuta merkezinden gelen emirle durduruldu.")
                
                close_active_jobs_in_db(bot_id, manual_stop=True)
                notify_bot_status(bot_id, is_start=False, exit_code="Bilinmiyor")

        # 2. ÇALIŞAN BOTLARIN SAĞLIK KONTROLÜ (Kendi kendine kapanmış mı?)
        for b_id, p in list(active_processes.items()):
            finished = False
            exit_code = "Bilinmiyor"

            # Durum A: Bot yeni başlatıldı (Popen objesi)
            if hasattr(p, 'poll'):
                if p.poll() is not None:
                    finished = True
                    exit_code = p.poll()
            
            # Durum B: Bot Manager açıldığında "zombi" olarak devralındı (int PID)
            else:
                import psutil
                if not psutil.pid_exists(p):
                    finished = True

            if finished:
                print(f"🏁 {b_id} görevini tamamladı veya kapandı. (Çıkış kodu: {exit_code})")
                # Sadece 1 kere mail atılmasını garantiye almak için kaydı siliyoruz
                yeni_status = "completed" if exit_code == 0 else "error"
                error_reason = None if exit_code == 0 else f"crash_code_{exit_code}"

                eski_kayit = cmd_col.find_one_and_update(
                    {"bot_id": b_id, "is_running": True},
                    {"$set": {
                        "is_running": False,
                        "status": yeni_status,
                        "error_reason": error_reason,
                        "pid": None,
                        "completed_at": datetime.now(timezone.utc)
                    }}
                )
                
                # Eğer kayıt bulunduysa (yani ilk kez kapanıyorsa) mail at
                if eski_kayit:
                    notify_bot_status(b_id, is_start=False, exit_code=exit_code)
                    close_active_jobs_in_db(b_id, manual_stop=False) # Dashboard'u 2 dakika takılmaktan kurtarır
                
                if b_id in active_processes:
                    del active_processes[b_id]

        time.sleep(2) # CPU'yu yormamak için ideal süre

    except Exception as e:
        print(f"❌ Bot Manager Hatası: {e}")
        time.sleep(5)