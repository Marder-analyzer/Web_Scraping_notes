import time
import pymongo
import subprocess
import psutil
import sys
import os
import re
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
    if not os.path.exists("saved_mails.json"): return
    with open("saved_mails.json", "r") as f:
        mails = json.load(f)
    if not mails: return
    target_mail = mails[0]

    zaman = datetime.now(TR_TZ).strftime('%d/%m/%Y %H:%M:%S')

    # DB'den özet al
    try:
        _db = client["neuranovav_db"]
        latest_job = _db.jobs.find_one(sort=[("start_time", pymongo.DESCENDING)])
        total_products = _db.products.count_documents({})
        total_history  = _db.price_history.count_documents({})
        failed_bekleyen = _db.failed_urls.count_documents({"cozuldu": False})
        emekli_proxy   = _db.proxy_performance.count_documents({"retired": True})
        proxy_stats    = _db.bot_commands.find_one({"bot_id": "proxy_stats"})
        toplam_proxy   = proxy_stats.get("aktif_proxy", 0) if proxy_stats else 0
        aktif_proxy    = max(0, toplam_proxy - emekli_proxy)

        stats     = latest_job.get("stats", {}) if latest_job else {}
        sure_sn   = latest_job.get("duration_seconds", 0) if latest_job else 0
        hiz       = int(total_products / (sure_sn / 3600)) if sure_sn > 0 else 0
        sure_str  = f"{int(sure_sn//3600)}s {int((sure_sn%3600)//60)}dk" if sure_sn else "-"

        ozet_html = f"""
        <h3 style="color:#444">📊 Anlık Sistem Özeti</h3>
        <table style="width:100%;border-collapse:collapse;font-size:14px">
            <tr><td style="padding:7px;background:#f9f9f9"><b>🗃️ Toplam Ürün</b></td><td style="padding:7px;background:#f9f9f9;color:#2e7d32"><b>{total_products:,}</b></td></tr>
            <tr><td style="padding:7px"><b>📈 Fiyat Geçmişi</b></td><td style="padding:7px">{total_history:,}</td></tr>
            <tr><td style="padding:7px;background:#f9f9f9"><b>⚡ Saatlik Verim</b></td><td style="padding:7px;background:#f9f9f9">~{hiz:,} ürün/saat</td></tr>
            <tr><td style="padding:7px"><b>✨ Yeni Keşfedilen</b></td><td style="padding:7px;color:#2e7d32">{stats.get('yeni_urun',0):,}</td></tr>
            <tr><td style="padding:7px;background:#f9f9f9"><b>🔄 Gün İçi Değişim</b></td><td style="padding:7px;background:#f9f9f9">{stats.get('gun_ici_degisim',0):,}</td></tr>
            <tr><td style="padding:7px"><b>🗑️ Fiyatsız Drop</b></td><td style="padding:7px;color:#c62828">{stats.get('drop_fiyatsiz',0):,}</td></tr>
            <tr><td style="padding:7px;background:#f9f9f9"><b>✅ Aktif Proxy</b></td><td style="padding:7px;background:#f9f9f9">{aktif_proxy} / {toplam_proxy}</td></tr>
            <tr><td style="padding:7px"><b>⏳ Bekleyen Hata URL</b></td><td style="padding:7px;color:#e65100">{failed_bekleyen:,}</td></tr>
        </table>"""
    except:
        ozet_html = "<p style='color:#aaa'>Sistem özeti alınamadı.</p>"

    if is_start:
        subject     = f"🚀 NeuraNovaV: {bot_id.upper()} Sahaya Sürüldü"
        renk        = "#1565c0"
        durum_metni = "🟢 BAŞLATILDI"
        mesaj       = "Bot başarıyla sahaya sürüldü ve veri toplamaya/işlemeye başladı."
    else:
        if exit_code == 0:
            subject     = f"🏁 NeuraNovaV: {bot_id.upper()} Görevi Tamamladı"
            renk        = "#2e7d32"
            durum_metni = "✅ BAŞARIYLA TAMAMLANDI"
            mesaj       = "Bot tüm işleri bitirdi ve sistemden güvenli şekilde ayrıldı."
        elif exit_code == "Bilinmiyor":
            subject     = f"🛑 NeuraNovaV: {bot_id.upper()} Durduruldu"
            renk        = "#e65100"
            durum_metni = "🛑 MANUEL DURDURULDU"
            mesaj       = "Bot kullanıcı tarafından durduruldu."
        elif exit_code == "heartbeat_yok":
            subject     = f"⚠️ NeuraNovaV: {bot_id.upper()} YANIT VERMİYOR"
            renk        = "#f57c00"
            durum_metni = "⚠️ YANIT VERMİYOR"
            mesaj       = "Bot process çalışıyor ama 30 dakikadır heartbeat sinyali gelmiyor. Dashboard'u kontrol edin."
        else:
            subject     = f"🚨 NeuraNovaV: {bot_id.upper()} ÇÖKTÜ!"
            renk        = "#c62828"
            durum_metni = f"❌ HATA İLE ÇÖKTÜ (Kod: {exit_code})"
            mesaj       = "Bot beklenmedik hatayla kapandı. Dashboard loglarını kontrol edin."

    html_body = f"""
    <html><body style="font-family:Arial,sans-serif;background:#f4f4f4;padding:20px">
    <div style="max-width:560px;margin:auto;background:white;border-radius:12px;padding:24px;box-shadow:0 2px 8px #ccc">
        <h2 style="color:{renk};margin-top:0">{durum_metni}</h2>
        <p style="color:#555;font-size:15px"><b>🤖 Bot:</b> {bot_id.upper()}</p>
        <p style="color:#555;font-size:15px"><b>📅 Zaman:</b> {zaman}</p>
        <hr style="border:1px solid #eee;margin:15px 0"/>
        <p style="color:#333;font-size:14px">{mesaj}</p>
        <hr style="border:1px solid #eee;margin:15px 0"/>
        {ozet_html}
        <p style="color:#888;font-size:12px;margin-top:20px">
            📊 <a href="http://localhost:8501" style="color:#6a0dad">Dashboard'u Aç</a> &nbsp;|&nbsp; NeuraNovaV Otomatik Bildirim
        </p>
    </div></body></html>"""

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"]    = f"NeuraNovaV Komuta <{MAIL_SENDER}>"
        msg["To"]      = target_mail
        msg.attach(MIMEText(html_body, "html"))
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(MAIL_SENDER, MAIL_APP_PASS)
            server.sendmail(MAIL_SENDER, target_mail, msg.as_string())
        print(f"📧 Durum Maili Gönderildi: {bot_id} -> {durum_metni}")
    except Exception as e:
        print(f"⚠️ Mail gönderilemedi: {e}")



def slaughter_zombies():
    """Zombi süreçleri, headless Chrome'ları ve asılı kalan Playwright işçilerini temizler."""
    killed_count = 0
    for proc in psutil.process_iter(['pid', 'name', 'cmdline', 'status']):
        try:
            name = (proc.info.get('name') or "").lower()
            cmdline = proc.info.get('cmdline') or []
            cmd_str = " ".join(cmdline).lower()
            status = proc.info.get('status', "")

            # Zombi süreçleri temizle (<defunct>)
            if status == psutil.STATUS_ZOMBIE:
                try:
                    proc.wait(timeout=1)
                    killed_count += 1
                except Exception:
                    pass
                continue

            # Headless Chrome ve Playwright worker temizle
            if (('chrome' in name or 'chromium' in name) and '--headless' in cmd_str) or \
               ('python' in name and 'playwright_worker.py' in cmd_str):
                proc.kill()
                killed_count += 1

        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            pass
    return killed_count

son_ram_kontrol = 0
son_ram_maili = 0
son_acil_kapatma = 0
son_heartbeat_maili = 0
son_heartbeat_durumu = "normal"
son_cpu_maili = 0
son_cpu_durdurma = 0
son_cpu_durumu = "yesil"  

son_internet_kontrol = 0
son_internet_durumu = "ok"

def check_internet():
    global son_internet_durumu
    try:
        import urllib.request
        urllib.request.urlopen("http://clients3.google.com/generate_204", timeout=5)

        if son_internet_durumu == "kopuk":
            print("İnternet bağlantısı geri geldi.")
            son_internet_durumu = "ok"
        return True
    except:
        if son_internet_durumu == "ok":
            print("İnternet bağlantısı koptu!")
            son_internet_durumu = "kopuk"
        return False

def check_ram_and_alert():
    global son_ram_maili, son_acil_kapatma

    # ── DİNAMİK RAM FREN ──
    try:
        sanal        = psutil.virtual_memory()
        sistem_yuzde = sanal.percent
        toplam_ram   = sanal.total
        proje_ram    = 0

        for proc in psutil.process_iter(['name', 'cmdline', 'memory_info']):
            try:
                name = (proc.info.get('name') or "").lower()
                cmd  = " ".join(proc.info.get('cmdline') or []).lower()
                if ("python" in name and any(x in cmd for x in ["scrapy","bot_manager","playwright","streamlit"])) or \
                   (("chrome" in name or "chromium" in name) and "--headless" in cmd) or \
                   "mongod" in name:
                    proje_ram += proc.info['memory_info'].rss
            except: pass

        proje_yuzde = (proje_ram / toplam_ram) * 100

        if   proje_yuzde > 88 or sistem_yuzde > 92: hedef = 2
        elif proje_yuzde > 82 or sistem_yuzde > 88: hedef = 4
        elif proje_yuzde > 75 or sistem_yuzde > 85: hedef = 8
        else:                                        hedef = 16

        mevcut = cmd_col.find_one({"bot_id": "ram_throttle"})
        if not mevcut or mevcut.get("concurrent") != hedef:
            cmd_col.update_one(
                {"bot_id": "ram_throttle"},
                {"$set": {
                    "concurrent":   hedef,
                    "proje_yuzde":  round(proje_yuzde, 1),
                    "sistem_yuzde": round(sistem_yuzde, 1),
                    "updated_at":   datetime.now(timezone.utc)
                }},
                upsert=True
            )
            print(f"🧠 RAM Fren: Proje %{proje_yuzde:.1f} | Sistem %{sistem_yuzde:.1f} → CONCURRENT={hedef}")
    except Exception as e:
        pass
    
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


def check_cpu_temp():
    global son_cpu_maili, son_cpu_durdurma, son_cpu_durumu

    # CPU sıcaklığını oku
    try:
        with open("/sys/class/thermal/thermal_zone0/temp") as f:
            cpu_sicaklik = int(f.read().strip()) / 1000
    except:
        return

    # SSD max sensör sıcaklığını oku (Controller dahil en yüksek değer)
    ssd_sicaklik = 0
    try:
        result = subprocess.run(
            ["sensors"], capture_output=True, text=True, timeout=5
        )
        nvme_bolge = False
        ssd_degerler = []
        for satir in result.stdout.splitlines():
            if "nvme" in satir.lower():
                nvme_bolge = True
            if nvme_bolge:
                eslesen = re.findall(r'\+([\d.]+)\s*C', satir)
                if eslesen:
                    ssd_degerler.append(float(eslesen[0]))
            if nvme_bolge and satir.strip() == "" and ssd_degerler:
                break
        if ssd_degerler:
            ssd_sicaklik = max(ssd_degerler)
    except:
        pass

    # Termal durumu belirle
    if cpu_sicaklik > 95 or ssd_sicaklik > 85:
        yeni_seviye = "siyah"
        hedef_concurrent = 2
    elif cpu_sicaklik > 90 or ssd_sicaklik > 82:
        yeni_seviye = "kirmizi"
        hedef_concurrent = 4
    elif ssd_sicaklik > 78:
        yeni_seviye = "turuncu"
        hedef_concurrent = 8
    elif cpu_sicaklik > 82:
        yeni_seviye = "sari"
        hedef_concurrent = 8
    else:
        yeni_seviye = "yesil"
        hedef_concurrent = 16

    # Durum değiştiyse logla
    if yeni_seviye != son_cpu_durumu:
        emojiler = {
            "yesil": "🟢", "sari": "🟡",
            "turuncu": "🟠", "kirmizi": "🔴", "siyah": "⚫"
        }
        print(
            f"{emojiler.get(yeni_seviye,'?')} TERMAL: {son_cpu_durumu}→{yeni_seviye} | "
            f"CPU={cpu_sicaklik}°C SSD={ssd_sicaklik}°C → concurrent={hedef_concurrent}"
        )
        son_cpu_durumu = yeni_seviye

        # Siyah veya kırmızıya geçişte mail at
        if yeni_seviye in ("siyah", "kirmizi", "turuncu") and time.time() - son_cpu_maili > 3600:

            son_cpu_maili = time.time()
            try:
                with open("saved_mails.json") as f:
                    target_mail = json.load(f)[0]
                html_body = f"""<html><body style="font-family:Arial,sans-serif;padding:20px">
                <div style="max-width:500px;margin:auto;background:white;border-radius:12px;
                padding:24px;border-left:8px solid #c62828">
                    <h2 style="color:#c62828">🌡️ Termal Uyarı: {yeni_seviye.upper()}</h2>
                    <p>CPU: <b>{cpu_sicaklik}°C</b> | SSD: <b>{ssd_sicaklik}°C</b></p>
                    <p>Scrapy {hedef_concurrent} concurrent'a düşürüldü.</p>
                    <p>Playwright bekleme moduna alındı.</p>
                    <p>Sistem otomatik yönetiliyor, müdahale gerekmez.</p>
                </div></body></html>"""
                msg = MIMEMultipart("alternative")
                msg["Subject"] = f"🌡️ NeuraNovaV Termal Uyarı: {yeni_seviye.upper()}"
                msg["From"] = f"NeuraNovaV Komuta <{MAIL_SENDER}>"
                msg["To"] = target_mail
                msg.attach(MIMEText(html_body, "html"))
                with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
                    server.login(MAIL_SENDER, MAIL_APP_PASS)
                    server.sendmail(MAIL_SENDER, target_mail, msg.as_string())
            except:
                pass

    # DB'ye termal durumu yaz (Playwright ve dashboard okusun)
    try:
        cmd_col.update_one(
            {"bot_id": "termal_durum"},
            {"$set": {
                "seviye": yeni_seviye,
                "cpu_temp": cpu_sicaklik,
                "ssd_temp": ssd_sicaklik,
                "concurrent": hedef_concurrent,
                "updated_at": datetime.now(timezone.utc)
            }},
            upsert=True
        )
        # Scrapy concurrent'ı güncelle
        cmd_col.update_one(
            {"bot_id": "ram_throttle"},
            {"$set": {
                "concurrent": hedef_concurrent,
                "termal_kaynakli": yeni_seviye != "yesil",
                "updated_at": datetime.now(timezone.utc)
            }},
            upsert=True
        )
    except:
        pass


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

# ── MERKEZİ RAM PAY HESAPLAMA ──
BOT_AGIRLIKLARI = {
    "ana_bot":      1,  # Scrapy
    "scrapy_fiyat": 1,  # Scrapy
    "pw_hata":      2,  # Playwright
    "pw_fiyat":     2,  # Playwright
    "pw_liste":     2,  # Playwright
}

def recalculate_ram_shares():
    """Aktif bot sayısına göre RAM paylarını hesaplar ve DB'ye yazar."""
    try:
        # Aktif botları bul
        aktif = [b for b in BOT_AGIRLIKLARI.keys() 
                 if b in active_processes and (
                     hasattr(active_processes[b], 'poll') and active_processes[b].poll() is None
                     or isinstance(active_processes[b], int) and psutil.pid_exists(active_processes[b])
                 )]

        # Sistem RAM bilgisi
        sanal        = psutil.virtual_memory()
        sistem_yuzde = sanal.percent
        kullanilabilir = 88  # Sistemin max %88'i kullanılabilir

        if len(aktif) == 0:
            # Bot yok — varsayılan
            cmd_col.update_one(
                {"bot_id": "ram_shares"},
                {"$set": {
                    "aktif_botlar": [],
                    "scrapy_limit": 80,
                    "playwright_limit": 80,
                    "updated_at": datetime.now(timezone.utc)
                }},
                upsert=True
            )
            return

        if len(aktif) == 1:
            # Tek bot — serbest, sadece sistem limiti
            cmd_col.update_one(
                {"bot_id": "ram_shares"},
                {"$set": {
                    "aktif_botlar":     aktif,
                    "scrapy_limit":     kullanilabilir,
                    "playwright_limit": kullanilabilir,
                    "updated_at":       datetime.now(timezone.utc)
                }},
                upsert=True
            )
            print(f"📊 RAM Pay: Tek bot ({aktif[0]}) → serbest (%{kullanilabilir})")
            return

        # Birden fazla bot — ağırlıklı dağıtım
        # MongoDB + dashboard için %10 sabit ayır
        paylasılacak = kullanilabilir - 10

        toplam_agirlik = sum(BOT_AGIRLIKLARI.get(b, 1) for b in aktif)

        scrapy_agirligi     = sum(BOT_AGIRLIKLARI[b] for b in aktif if BOT_AGIRLIKLARI.get(b) == 1)
        playwright_agirligi = sum(BOT_AGIRLIKLARI[b] for b in aktif if BOT_AGIRLIKLARI.get(b) == 2)

        scrapy_limit     = round((scrapy_agirligi / toplam_agirlik) * paylasılacak) if scrapy_agirligi > 0 else 0
        playwright_limit = round((playwright_agirligi / toplam_agirlik) * paylasılacak) if playwright_agirligi > 0 else 0

        cmd_col.update_one(
            {"bot_id": "ram_shares"},
            {"$set": {
                "aktif_botlar":     aktif,
                "scrapy_limit":     scrapy_limit,
                "playwright_limit": playwright_limit,
                "updated_at":       datetime.now(timezone.utc)
            }},
            upsert=True
        )
        print(f"📊 RAM Pay: {aktif} → Scrapy:%{scrapy_limit} | Playwright:%{playwright_limit}")

    except Exception as e:
        print(f"⚠️ RAM pay hesaplama hatası: {e}")

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
        if not check_internet():
            time.sleep(30)
            continue
        
        if time.time() - son_ram_kontrol > 30:
            
            check_ram_and_alert()
            check_cpu_temp()
            

                        
            
            try:
                latest_job = db.jobs.find_one({"status": "Running"}, sort=[("start_time", -1)])
                if latest_job:
                    last_ping = latest_job.get("last_ping")
                    if last_ping:
                        fark = (datetime.now(timezone.utc) - last_ping.replace(tzinfo=timezone.utc)).total_seconds()
                        
                        if fark > 1800 and son_heartbeat_durumu == "normal":
                            # 30 dakikadır sinyal yok — ilk uyarı
                            son_heartbeat_durumu = "uyari"
                            son_heartbeat_maili = time.time()
                            notify_bot_status("ana_bot", is_start=False, exit_code="heartbeat_yok")
                            print(f"⚠️ Heartbeat uyarısı gönderildi | {int(fark//60)} dk sinyal yok")
                            
                        elif fark > 1800 and son_heartbeat_durumu == "uyari":
                            # Hala sorun var — 2 saatte bir tekrar at
                            if time.time() - son_heartbeat_maili > 7200:
                                son_heartbeat_maili = time.time()
                                notify_bot_status("ana_bot", is_start=False, exit_code="heartbeat_yok")
                                print(f"⚠️ Heartbeat tekrar uyarısı | {int(fark//60)} dk sinyal yok")
                                
                        elif fark <= 1800 and son_heartbeat_durumu == "uyari":
                            # Düzeldi — bildir
                            son_heartbeat_durumu = "normal"
                            print(f"✅ Heartbeat normale döndü")
            except Exception as e:
                pass
            son_ram_kontrol = time.time()
            
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
                    cmd_list = [sys.executable, "-m", "scrapy", "crawl", "trendyol"]
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
                recalculate_ram_shares()
                
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
                recalculate_ram_shares()

        # 2. ÇALIŞAN BOTLARIN SAĞLIK KONTROLÜ (Kendi kendine kapanmış mı?)
        for b_id, p in list(active_processes.items()):
            finished = False
            exit_code = "Bilinmiyor"

            # Durum A: Bot yeni başlatıldı (Popen objesi)
            if hasattr(p, 'poll'):
                if p.poll() is not None:
                    finished = True
                    exit_code = p.poll()
                    # Zombi oluşmasını önle
                    try:
                        p.wait(timeout=3)
                    except Exception:
                        pass
            
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
                    close_active_jobs_in_db(b_id, manual_stop=False) 
                    recalculate_ram_shares()
                
                if b_id in active_processes:
                    del active_processes[b_id]

        time.sleep(2) # CPU'yu yormamak için ideal süre

    except Exception as e:
        print(f"❌ Bot Manager Hatası: {e}")
        time.sleep(5)