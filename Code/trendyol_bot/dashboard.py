import streamlit as st
import subprocess
import sys
import pymongo
import pandas as pd
import plotly.express as px
from datetime import datetime, timezone
from streamlit_autorefresh import st_autorefresh
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import json
import os
import pytz
import psutil
import time
from dotenv import load_dotenv
import plotly.graph_objects as go
from datetime import timedelta
import urllib.request

load_dotenv()

def get_bot_ram_usage_mb():
    total_rss = 0
    for proc in psutil.process_iter(['name', 'cmdline', 'memory_info']):
        try:
            name = (proc.info.get('name') or "").lower()
            cmdline = proc.info.get('cmdline') or []
            cmd_str = " ".join(cmdline).lower()
            
            # Python botları (scrapy, playwright, bot_manager, streamlit/dashboard)
            is_our_python = "python" in name and (
                "playwright_worker.py" in cmd_str or
                "scrapy" in cmd_str or
                "bot_manager.py" in cmd_str or
                "dashboard.py" in cmd_str or
                "streamlit" in cmd_str
            )
            
            # Headless Chrome (Playwright'ın açtığı)
            is_our_chrome = ("chrome" in name or "chromium" in name) and "--headless" in cmd_str
            
            # MongoDB (mongod süreci)
            is_mongo = "mongod" in name
            
            if is_our_python or is_our_chrome or is_mongo:
                total_rss += proc.info['memory_info'].rss
                
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            pass
            
    return total_rss / (1024 * 1024)

# ─────────────────────────────────────────────
# AYARLAR
# ─────────────────────────────────────────────
MAIL_SENDER      = os.getenv("MAIL_SENDER", "")
MAIL_APP_PASS    = os.getenv("MAIL_APP_PASS", "")
SAVED_MAILS_FILE = "saved_mails.json"
ZOMBIE_FLAG_FILE = "zombie_mail_sent.json"
TR_TZ            = pytz.timezone("Europe/Istanbul")

# ─────────────────────────────────────────────
# SAYFA YAPILANDIRMASI
# ─────────────────────────────────────────────
st.set_page_config(page_title="NeuraNovaV Komuta Merkezi", page_icon="🛸", layout="wide")
refresh_count = st_autorefresh(interval=8000, limit=100000, key="auto_refresh")

# Ekran kararmasını ve "Running..." ikonunu engelle
st.markdown("""
    <style>
        * { transition: none !important; animation: none !important; }
        
        .stApp, [data-testid="stAppViewContainer"],
        [data-testid="stMainBlockContainer"],
        section[data-testid="stMain"],
        [data-testid="stAppViewBlockContainer"],
        .main, .block-container,
        [data-testid="stVerticalBlock"],
        [data-testid="stHorizontalBlock"] {
            opacity: 1 !important;
            filter: none !important;
            transition: none !important;
            animation: none !important;
        }
        
        .stApp[data-teststate="running"] .stMarkdown,
        .stApp[data-teststate="running"] .element-container,
        .stApp[data-teststate="running"] [data-testid] {
            opacity: 1 !important;
            filter: none !important;
        }
        
        [data-testid="stStatusWidget"] { visibility: hidden !important; }
        iframe[title="streamlit_autorefresh.autorefresh"] { display: none !important; }
        div[data-testid="stDecoration"] { display: none !important; }
        #MainMenu { visibility: hidden !important; }
        [data-testid="stAppViewContainer"] > div { opacity: 1 !important; }
        div[class*="withScreencast"] { opacity: 1 !important; }
        div[class*="stSpinner"] { display: none !important; }
        header { visibility: hidden !important; }
        body { opacity: 1 !important; }
    </style>
    <script>
        setInterval(() => {
            document.querySelectorAll('[data-testid="stAppViewContainer"], .stApp, body, .main, .block-container').forEach(el => {
                el.style.setProperty('opacity', '1', 'important');
                el.style.setProperty('filter', 'none', 'important');
                el.style.setProperty('transition', 'none', 'important');
            });
        }, 50);
    </script>
""", unsafe_allow_html=True)

# Son yenileme zamanı
if "last_refresh_time" not in st.session_state:
    st.session_state["last_refresh_time"] = datetime.now(TR_TZ).strftime("%H:%M:%S")
if refresh_count and refresh_count > 0:
    st.session_state["last_refresh_time"] = datetime.now(TR_TZ).strftime("%H:%M:%S")

# Hata logu
if "error_log" not in st.session_state:
    st.session_state["error_log"] = []
    
if "active_bots" not in st.session_state:
    st.session_state["active_bots"] = {}
    
if "bot_statuses" not in st.session_state:
    st.session_state["bot_statuses"] = {
        "ana_bot": "Uyku Modu 💤",
        "pw_hata": "Uyku Modu 💤",
        "scrapy_fiyat": "Uyku Modu 💤",
        "pw_fiyat": "Uyku Modu 💤"
    }

# ─────────────────────────────────────────────
# YARDIMCI FONKSİYONLAR
# ─────────────────────────────────────────────
def log_error(msg):
    ts = datetime.now(TR_TZ).strftime("%H:%M:%S")
    st.session_state["error_log"].insert(0, f"[{ts}] {msg}")
    st.session_state["error_log"] = st.session_state["error_log"][:20]
    
if "active_bots" not in st.session_state:
    st.session_state["active_bots"] = {}

# Aktif botların durumunu kontrol et (Her yenilemede çalışır)
bitenler = []
for bot_id, bot_info in st.session_state["active_bots"].items():
    proc = bot_info["proc"]
    ret = proc.poll() # Süreç bitti mi diye kontrol et
    
    if ret is not None:  # Süreç kapanmış (başarılı veya çökmüş)
        if ret != 0:     # 0 dışında bir kod, "HATA" demektir!
            # Çöken botun terminaldeki kırmızı hata mesajını oku
            hata_ciktisi = proc.stderr.read() if proc.stderr else "Bilinmeyen Hata"
            # Çok uzun olmasın diye sadece son 200 karakterini al
            kisa_hata = hata_ciktisi[-200:].strip() if hata_ciktisi else f"Çıkış Kodu: {ret}"
            # Senin kendi fonksiyonunla Dashboard'a fırlat!
            log_error(f"{bot_info['name']} Çöktü! Hata: {kisa_hata}")
            
        # Biten botu listeden çıkar
        bitenler.append(bot_id)

for b in bitenler:
    del st.session_state["active_bots"][b]
# ------------------------------------------
    


def load_saved_mails():
    if os.path.exists(SAVED_MAILS_FILE):
        with open(SAVED_MAILS_FILE, "r") as f:
            return json.load(f)
    return []

def save_mail_to_list(email):
    mails = load_saved_mails()
    if email and email not in mails:
        mails.insert(0, email)
        mails = mails[:10]
        with open(SAVED_MAILS_FILE, "w") as f:
            json.dump(mails, f)

# Zombie flag — dosyada tutulur, F5 ve yeniden başlatmaya karşı dayanıklı
def get_zombie_job_id():
    if os.path.exists(ZOMBIE_FLAG_FILE):
        with open(ZOMBIE_FLAG_FILE, "r") as f:
            return json.load(f).get("job_id")
    return None

def set_zombie_job_id(job_id):
    with open(ZOMBIE_FLAG_FILE, "w") as f:
        json.dump({"job_id": job_id}, f)

def clear_zombie_flag():
    if os.path.exists(ZOMBIE_FLAG_FILE):
        os.remove(ZOMBIE_FLAG_FILE)

def send_mail(to_email, subject, html_body, attachment_data=None, attachment_name=None):
    """Mail gönderir. (True, None) veya (False, hata_mesajı) döner."""
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"]    = f"NeuraNovaV Bot <{MAIL_SENDER}>"
        msg["To"]      = to_email
        msg.attach(MIMEText(html_body, "html"))
        if attachment_data:
            from email.mime.application import MIMEApplication
            part = MIMEApplication(attachment_data, Name=attachment_name)
            part["Content-Disposition"] = f'attachment; filename="{attachment_name}"'
            msg.attach(part)
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(MAIL_SENDER, MAIL_APP_PASS)
            server.sendmail(MAIL_SENDER, to_email, msg.as_string())
        return True, None
    except smtplib.SMTPAuthenticationError:
        err = "Gmail kimlik hatası! App Password yanlış veya 2FA kapalı."
        log_error(f"MAIL: {err}")
        return False, err
    except smtplib.SMTPException as e:
        err = f"SMTP hatası: {str(e)[:120]}"
        log_error(f"MAIL: {err}")
        return False, err
    except Exception as e:
        err = f"Bilinmeyen hata: {str(e)[:120]}"
        log_error(f"MAIL: {err}")
        return False, err

# 1. DÜZELTME: bot_status parametresi düzeltildi ve Türkçe karakterler eklendi
def build_report_html(job, stats, total_products, total_history, subject_prefix="📊 Rapor", bot_status=None , proxy_data=None):
    yeni      = stats.get("yeni_urun", 0)
    gun_kaydi = stats.get("yeni_gun_kaydi", 0)
    degisim   = stats.get("gun_ici_degisim", 0)
    fiyatsiz  = stats.get("drop_fiyatsiz", 0)
    hata      = stats.get("drop_hata", 0)
    toplam    = job.get("total_processed", 0)
    status    = bot_status if bot_status else job.get("status", "-")
    start_time = job.get("start_time")
    end_time   = job.get("end_time") or datetime.now(timezone.utc)
    sure = (end_time.replace(tzinfo=timezone.utc) - start_time.replace(tzinfo=timezone.utc)).total_seconds() if start_time else 0
    sure_str = f"{int(sure//3600)}s {int((sure%3600)//60)}dk"

    # Saatlik verim
    hiz = int(toplam / (sure / 3600)) if sure > 0 else 0

    # Tahmini bitiş
    total_target = job.get("total_target_urls", 0)
    gercek_toplam = total_products
    bitis_str = "-"
    if total_target > 0 and gercek_toplam > 0 and sure > 0 and total_target > gercek_toplam:
        hiz_sn = gercek_toplam / sure
        kalan_sn = (total_target - gercek_toplam) / hiz_sn
        kalan_gun = int(kalan_sn // 86400)
        kalan_saat = int((kalan_sn % 86400) // 3600)
        bitis_str = f"{kalan_gun} gün {kalan_saat} saat sonra"

    # Proxy özeti
    try:
        db_client = pymongo.MongoClient("mongodb://localhost:27017/")
        _db = db_client["neuranovav_db"]
        emekli_proxy = _db["proxy_performance"].count_documents({"retired": True})
        proxy_stats  = _db["bot_commands"].find_one({"bot_id": "proxy_stats"})
        toplam_proxy = proxy_stats.get("aktif_proxy", 0) if proxy_stats else 0
        aktif_proxy  = max(0, toplam_proxy - emekli_proxy)
        failed_cozulmemis = _db["failed_urls"].count_documents({"cozuldu": False})
        failed_cozulmus   = _db["failed_urls"].count_documents({"cozuldu": True})
    except:
        aktif_proxy = emekli_proxy = toplam_proxy = failed_cozulmemis = failed_cozulmus = 0

    # Proxy tablosu
    proxy_html = ""
    if proxy_data:
        satirlar = ""
        for p in proxy_data:
            durum = "🚫 Emekli" if p.get("retired") else "✅ Aktif"
            satirlar += f"""
            <tr>
                <td style="padding:6px;font-size:12px">{p.get('proxy','?')}</td>
                <td style="padding:6px;text-align:center">{p.get('success_count',0)}</td>
                <td style="padding:6px;text-align:center;color:#c62828"><b>{p.get('ban_count',0)}</b></td>
                <td style="padding:6px;text-align:center">{durum}</td>
            </tr>"""
        proxy_html = f"""
            <h3>🛡️ Proxy Durumu (Top 5)</h3>
            <table style="width:100%;border-collapse:collapse;font-size:13px">
                <tr style="background:#f0f0f0">
                    <th style="padding:6px;text-align:left">Proxy</th>
                    <th style="padding:6px">Başarılı</th>
                    <th style="padding:6px">Ban</th>
                    <th style="padding:6px">Durum</th>
                </tr>
                {satirlar}
            </table>"""

    return f"""
    <html><body style="font-family:Arial,sans-serif;background:#f4f4f4;padding:20px">
    <div style="max-width:600px;margin:auto;background:white;border-radius:12px;padding:24px;box-shadow:0 2px 8px #ccc">
        <h2 style="color:#6a0dad">&#128760; NeuraNovaV Bot Raporu</h2>
        <p style="color:#555">{subject_prefix} &mdash; {datetime.now(TR_TZ).strftime('%d %B %Y %H:%M')}</p>
        <p style="color:#888;font-size:13px">📊 Canlı dashboard: <a href="http://localhost:8501" style="color:#6a0dad">http://localhost:8501</a></p>
        <hr/>

        <h3>🤖 Bot Durumu</h3>
        <table style="width:100%;border-collapse:collapse">
            <tr><td style="padding:8px;background:#f9f9f9"><b>Durum</b></td><td style="padding:8px">{status}</td></tr>
            <tr><td style="padding:8px"><b>Çalışma Süresi</b></td><td style="padding:8px">{sure_str}</td></tr>
            <tr><td style="padding:8px;background:#f9f9f9"><b>Saatlik Verim</b></td><td style="padding:8px;background:#f9f9f9">~{hiz:,} ürün/saat</td></tr>
            <tr><td style="padding:8px"><b>Tahmini Bitiş</b></td><td style="padding:8px">{bitis_str}</td></tr>
        </table>

        <h3>📦 Veri Durumu</h3>
        <table style="width:100%;border-collapse:collapse">
            <tr><td style="padding:8px;background:#e8f5e9"><b>Toplam Benzersiz Ürün</b></td><td style="padding:8px;background:#e8f5e9;color:#2e7d32"><b>{total_products:,}</b></td></tr>
            <tr><td style="padding:8px"><b>Toplam Fiyat Geçmişi</b></td><td style="padding:8px">{total_history:,}</td></tr>
            <tr><td style="padding:8px;background:#f9f9f9"><b>Toplam İşlenen URL</b></td><td style="padding:8px;background:#f9f9f9">{toplam:,}</td></tr>
        </table>

        <h3>📊 Oturum İstatistikleri</h3>
        <table style="width:100%;border-collapse:collapse">
            <tr><td style="padding:8px;background:#e8f5e9"><b>✨ Yeni Keşfedilen</b></td><td style="padding:8px;background:#e8f5e9;color:#2e7d32"><b>{yeni:,}</b></td></tr>
            <tr><td style="padding:8px"><b>📅 Bugünün İlk Kaydı</b></td><td style="padding:8px;color:#1565c0"><b>{gun_kaydi:,}</b></td></tr>
            <tr><td style="padding:8px;background:#f9f9f9"><b>🔄 Gün İçi Değişim</b></td><td style="padding:8px;background:#f9f9f9;color:#e65100"><b>{degisim:,}</b></td></tr>
            <tr><td style="padding:8px"><b>🗑️ Fiyatsız Düşürülen</b></td><td style="padding:8px;color:#c62828"><b>{fiyatsiz:,}</b></td></tr>
            <tr><td style="padding:8px;background:#f9f9f9"><b>❌ Hatalı Düşürülen</b></td><td style="padding:8px;background:#f9f9f9;color:#c62828"><b>{hata:,}</b></td></tr>
        </table>

        <h3>🛡️ Proxy Özeti</h3>
        <table style="width:100%;border-collapse:collapse">
            <tr><td style="padding:8px;background:#f9f9f9"><b>✅ Aktif Proxy</b></td><td style="padding:8px;background:#f9f9f9">{aktif_proxy}</td></tr>
            <tr><td style="padding:8px"><b>🚫 Emekli Proxy</b></td><td style="padding:8px">{emekli_proxy}</td></tr>
            <tr><td style="padding:8px;background:#f9f9f9"><b>📦 Toplam Havuz</b></td><td style="padding:8px;background:#f9f9f9">{toplam_proxy}</td></tr>
        </table>

        <h3>🔴 URL Hata Özeti</h3>
        <table style="width:100%;border-collapse:collapse">
            <tr><td style="padding:8px;background:#f9f9f9"><b>⏳ Çözülmemiş</b></td><td style="padding:8px;background:#f9f9f9;color:#c62828"><b>{failed_cozulmemis:,}</b></td></tr>
            <tr><td style="padding:8px"><b>✅ Çözülmüş</b></td><td style="padding:8px;color:#2e7d32"><b>{failed_cozulmus:,}</b></td></tr>
        </table>

        <hr/>
        {proxy_html}
        <p style="color:#aaa;font-size:12px">NeuraNovaV Otomatik Raporlama Sistemi</p>
    </div></body></html>
    """

# ─────────────────────────────────────────────
# MONGODB BAĞLANTISI
# ─────────────────────────────────────────────
@st.cache_resource
def init_connection():
    return pymongo.MongoClient("mongodb://localhost:27017/", serverSelectionTimeoutMS=2000)

client = init_connection()
try:
    client.admin.command("ping")
    db_online = True
except Exception:
    db_online = False

# ─────────────────────────────────────────────
# BAŞLIK
# ─────────────────────────────────────────────
st.title("🛸 NeuraNovaV Veri İstihbarat Kokpiti")
st.markdown("---")

# ─────────────────────────────────────────────
# SIDEBAR VE MAİL GÖNDERİMİ
# ─────────────────────────────────────────────
with st.sidebar:
    st.markdown("""
        <div style='text-align:center;padding:10px 0'>
            <span style='font-size:28px'>🍃</span>
            <span style='font-size:18px;font-weight:bold;color:#00ED64'> MongoDB</span>
        </div>
    """, unsafe_allow_html=True)

    if db_online:
        st.success("✅ MongoDB Bağlantısı Aktif")
    else:
        st.error("❌ MongoDB Bağlantısı Yok")

    st.caption(f"🕐 Son Yenileme: {st.session_state.get('last_refresh_time', '-')}")

    if st.button("🔄 Anında Yenile"):
        st.session_state["last_refresh_time"] = datetime.now(TR_TZ).strftime("%H:%M:%S")
        st.rerun()

    st.markdown("---")

    

    if db_online:
        cmd_col = client["neuranovav_db"]["bot_commands"]

        def is_bot_running_db(bot_id):
            """MongoDB'ye sorar: Komutan bu botu sahaya sürdü mü?"""
            doc = cmd_col.find_one({"bot_id": bot_id})
            # Eğer is_running True ise VEYA başlat emri verilmiş ama henüz işlenmemişse (pending) aktif göster
            if doc and (doc.get("is_running", False) or (doc.get("status") == "pending" and doc.get("action") == "start")):
                return True
            return False

        def send_command(bot_id, action):
            """Dashboard'dan Komutana veritabanı üzerinden emir gönderir."""
            cmd_col.update_one(
                {"bot_id": bot_id},
                {"$set": {
                    "action": action, 
                    "status": "pending", 
                    "updated_at": datetime.now(timezone.utc)
                }},
                upsert=True
            )
            if action == "start":
                st.toast(f"🚀 {bot_id} için BAŞLATMA emri karargaha iletildi!")
            else:
                st.toast(f"🛑 {bot_id} için DURDURMA emri karargaha iletildi!")

        # --- BOT BUTONLARI ---
        st.subheader("🚀 Bot Kontrol Paneli")

        bot_configs = [
            ("ana_bot", "🕷️ 1. Ana Botu Başlat", "ana_bot.log"),
            ("pw_hata", "🚑 2. Hataları Kurtar (PW)", "pw_hata.log"),
            ("pw_liste", "🔍 3. Liste Sayfaları Kurtar (PW)", "pw_liste.log"),
            ("scrapy_fiyat", "⚡ Hızlı Fiyat", "hizli_fiyat.log"),
            ("pw_fiyat", "🐢 Güvenilir (PW)", "pw_fiyat.log")
        ]

        for bot_id, btn_text, log_file in bot_configs:
            calisiyor_mu = is_bot_running_db(bot_id)
            
            if calisiyor_mu:
                # Çalışıyorsa kırmızı DURDUR butonu göster
                st.markdown(f"<div style='color:#00ED64; font-weight:bold; margin-bottom:5px;'>🟢 {bot_id.upper()} SAHADA</div>", unsafe_allow_html=True)
                if st.button(f"🛑 DURDUR", key=f"stop_{bot_id}", type="primary", width='stretch'):
                    send_command(bot_id, "stop")
                    st.rerun()
            else:
                # Çalışmıyorsa normal BAŞLAT butonu göster
                if st.button(btn_text, key=f"start_{bot_id}", width='stretch'):
                    send_command(bot_id, "start")
                    st.rerun()
            
    st.markdown("---")
    
    # Hata logu kutucuğu
    hata_sayisi = len(st.session_state["error_log"])
    if hata_sayisi > 0:
        with st.expander(f"⚠️ Sistem Hataları ({hata_sayisi})", expanded=True):
            for err in st.session_state["error_log"]:
                st.caption(f"🔴 {err}")
            if st.button("🗑️ Hataları Temizle", key="clear_errors"):
                st.session_state["error_log"] = []
                st.rerun()
        st.markdown("---")

    # Rapor arşivi
    st.subheader("📥 Rapor Arşivi")
    csv_data = None
    if db_online:
        all_jobs = list(client["neuranovav_db"].jobs.find({}, {"_id": 0}))
        if all_jobs:
            df_jobs = pd.DataFrame(all_jobs)
            if "stats" in df_jobs.columns:
                stats_df = df_jobs["stats"].apply(pd.Series)
                df_jobs = pd.concat([df_jobs.drop(["stats"], axis=1), stats_df], axis=1)
            csv_data = df_jobs.to_csv(index=False).encode("utf-8")
            st.download_button(
                label="📊 Tüm Geçmişi İndir (CSV)",
                data=csv_data,
                file_name=f"neuranovav_raporlari_{datetime.now(TR_TZ).strftime('%Y%m%d')}.csv",
                mime="text/csv"
            )
        else:
            st.info("Henüz indirilecek rapor yok.")

    st.markdown("---")

    # Mail gönder
    st.subheader("📧 Mail Gönder")
    saved_mails = load_saved_mails()
    mail_input  = st.text_input("Mail adresi:", placeholder="ornek@gmail.com")

    if st.button("📤 Raporu Şimdi Gönder"):
        if mail_input and db_online:
            save_mail_to_list(mail_input)
            jfm = client["neuranovav_db"].jobs.find_one(sort=[("start_time", pymongo.DESCENDING)])
            if jfm:
                # 2. DÜZELTME: Sidebar üzerinden manuel gönderimde bot durumunu hesapla
                jfm_status = jfm.get("status", "-")
                if jfm_status == "Running":
                    jfm_last_ping = jfm.get("last_ping") or jfm.get("start_time")
                    if jfm_last_ping:
                        fark = (datetime.now(timezone.utc) - jfm_last_ping.replace(tzinfo=timezone.utc)).total_seconds()
                        if fark > 120:
                            sessiz = int(fark // 60)
                            jfm_status = f"🟡 BOT YANIT VERMİYOR ({sessiz} dakikadır sinyal yok)"

                s   = jfm.get("stats", {})
                tp  = client["neuranovav_db"].products.count_documents({})
                th  = client["neuranovav_db"].price_history.count_documents({})
                
                proxy_data = list(client["neuranovav_db"]["proxy_performance"].find().sort("ban_count", -1).limit(5))
                html = build_report_html(jfm, s, tp, th, "📤 Hızlı Rapor", bot_status=jfm_status, proxy_data=proxy_data)
                with st.spinner("Gönderiliyor..."):
                    ok, err = send_mail(mail_input, "NeuraNovaV Anlık Rapor", html, csv_data, "rapor.csv")
                if ok:
                    st.success(f"✅ Mail gönderildi: {mail_input}")
                else:
                    st.error(f"❌ {err}")
        elif not mail_input:
            st.warning("Lütfen bir mail adresi girin!")

    if saved_mails:
        st.markdown("**Sık Kullanılanlar:**")
        for m in saved_mails:
            if st.button(f"📨 {m}", key=f"quick_{m}"):
                jfm = client["neuranovav_db"].jobs.find_one(sort=[("start_time", pymongo.DESCENDING)])
                if jfm:
                    # 2. DÜZELTME: Sık kullanılanlardan gönderimde bot durumunu hesapla
                    jfm_status = jfm.get("status", "-")
                    if jfm_status == "Running":
                        jfm_last_ping = jfm.get("last_ping") or jfm.get("start_time")
                        if jfm_last_ping:
                            fark = (datetime.now(timezone.utc) - jfm_last_ping.replace(tzinfo=timezone.utc)).total_seconds()
                            if fark > 120:
                                sessiz = int(fark // 60)
                                jfm_status = f"🟡 BOT YANIT VERMİYOR ({sessiz} dakikadır sinyal yok)"

                    s   = jfm.get("stats", {})
                    tp  = client["neuranovav_db"].products.count_documents({})
                    th  = client["neuranovav_db"].price_history.count_documents({})
                    proxy_data = list(client["neuranovav_db"]["proxy_performance"].find().sort("ban_count", -1).limit(5))
                    html = build_report_html(jfm, s, tp, th, "📤 Hızlı Rapor", bot_status=jfm_status, proxy_data=proxy_data)
                    with st.spinner("Gönderiliyor..."):
                        ok, err = send_mail(m, "NeuraNovaV Hızlı Rapor", html, csv_data, "rapor.csv")
                    if ok:
                        st.success(f"✅ Gönderildi: {m}")
                    else:
                        st.error(f"❌ {err}")

# ─────────────────────────────────────────────
# DB KAPALI → DUR
# ─────────────────────────────────────────────
if not db_online:
    st.error("🚨 **Kritik Hata: Veritabanına Ulaşılamıyor!**")
    # Mongo koptu maili
    if "mongo_alert_sent" not in st.session_state:
        st.session_state["mongo_alert_sent"] = False
    if not st.session_state["mongo_alert_sent"]:
        saved = load_saved_mails()
        if saved:
            html_alert = f"""
            <html><body style="font-family:Arial,sans-serif;padding:20px">
            <div style="max-width:500px;margin:auto;background:white;border-radius:12px;padding:24px">
                <h2 style="color:#c62828">🚨 MongoDB Bağlantısı Koptu!</h2>
                <p>{datetime.now(TR_TZ).strftime('%d/%m/%Y %H:%M')} itibarıyla veritabanına erişilemiyor.</p>
                <p style="color:#888;font-size:13px">📊 Dashboard: <a href="http://localhost:8501">http://localhost:8501</a></p>
            </div></body></html>"""
            send_mail(saved[0], "🚨 NeuraNovaV: MongoDB Bağlantısı Koptu!", html_alert)
            st.session_state["mongo_alert_sent"] = True
            
    st.warning("MongoDB şu anda kapalı veya yanıt vermiyor.")
    st.info("🛠️ Docker Desktop'ı açın, MongoDB container'ını başlatın (▶️), ardından 'Anında Yenile'ye tıklayın.")
    if st.button("▶️ MongoDB Docker Container'ı Başlat", type="primary"):
        import subprocess
        try:
            subprocess.run(["docker", "start", "neuranovav_mongo"], check=True)
            st.success("✅ Veritabanı başlatma sinyali gönderildi! 5 saniye sonra 'Anında Yenile'ye basın.")
        except Exception as e:
            st.error(f"❌ Başlatılamadı! Docker Desktop kapalı olabilir. Hata: {e}")
    st.stop()

db = client["neuranovav_db"]
cmd_col = client["neuranovav_db"]["bot_commands"]
default_mail = load_saved_mails()
default_mail = default_mail[0] if default_mail else None

# ─────────────────────────────────────────────
# ANA İÇERİK VE ZOMBIE KONTROLÜ
# ─────────────────────────────────────────────
latest_job = db.jobs.find_one(sort=[("start_time", pymongo.DESCENDING)])

# ── SYSTEM STATS (her zaman görünür) ──
aktif_kayitlar = list(cmd_col.find({"is_running": True}))
gercek_calisan_sayisi = 0
for bot in aktif_kayitlar:
    pid = bot.get("pid")
    if pid and psutil.pid_exists(pid):
        gercek_calisan_sayisi += 1
    else:
        cmd_col.update_one(
            {"_id": bot["_id"]},
            {"$set": {"is_running": False, "pid": None, "status": "zombie_cleaned"}}
        )
ram = psutil.virtual_memory()
ram_yuzde = ram.percent
ram_renk = "🔴" if ram_yuzde > 85.0 else "🟡" if ram_yuzde > 70.0 else "🟢"
bot_ram_mb = get_bot_ram_usage_mb()
toplam_ram_mb = psutil.virtual_memory().total / (1024 * 1024)
bot_ram_yuzde = (bot_ram_mb / toplam_ram_mb) * 100
try:
    urllib.request.urlopen("http://clients3.google.com/generate_204", timeout=3)
    internet_ok = True
except:
    internet_ok = False
internet_renk = "🟢" if internet_ok else "🔴"
internet_yazi = "Bağlı" if internet_ok else "KOPUK"
try:
    if os.name == 'nt':
        watchdog_yazi = "Sadece Linux'ta"
    else:
        watchdog_aktif = subprocess.run(
            ["systemctl", "is-active", "nic-watchdog"],
            capture_output=True, text=True, timeout=5
        ).stdout.strip() == "active"
        watchdog_yazi = "Çalışıyor ✅" if watchdog_aktif else "Durdu ❌"
except:
    watchdog_yazi = "Bilinmiyor"
try:
    if os.name == 'nt':
        reset_sayisi = 0
        son_reset = "Sadece Linux'ta"
    else:
        with open("/var/log/nic-watchdog.log") as f:
            satirlar = f.readlines()[-200:]
        reset_sayisi = sum(1 for s in satirlar if "resetleniyor" in s)
        son_reset = next(
            (s.strip()[:19] for s in reversed(satirlar) if "Reset tamamlandi" in s),
            "Hiç reset yok"
        )
except:
    reset_sayisi = 0
    son_reset = "Log yok"

col1, col2, col3 = st.columns(3)
with col1:
    st.metric(label="🕵️ Aktif Botlar", value=gercek_calisan_sayisi)
with col2:
    st.metric(label=f"{ram_renk} Sistem Toplam RAM", value=f"%{ram_yuzde:.1f}")
with col3:
    st.metric(label="🤖 Projenin RAM Tüketimi", value=f"{bot_ram_mb:.1f} MB",
              delta=f"Sistemin %{bot_ram_yuzde:.1f}'i")
st.markdown("##### 🌐 Ağ & Sistem Sağlığı")
n1, n2, n3, n4 = st.columns(4)
n1.metric(label="🌐 İnternet", value=f"{internet_renk} {internet_yazi}")
n2.metric(label="🔧 NIC Watchdog", value=watchdog_yazi)
n3.metric(label="🔁 Otomatik Reset", value=f"{reset_sayisi} kez")
n4.metric(label="🕐 Son Reset", value=son_reset)
st.markdown("---")

if latest_job:
    stats      = latest_job.get("stats", {})
    job_id     = latest_job.get("job_id", "")
    is_running = latest_job.get("status") == "Running"
    last_ping  = latest_job.get("last_ping") or latest_job.get("start_time")
    job_status = latest_job.get("status", "")
    ana_cmd = cmd_col.find_one({"bot_id": "ana_bot"}) if db_online else None
    ana_cmd_status = ana_cmd.get("status", "") if ana_cmd else ""

    if is_running:
        if ana_cmd_status == "paused":
            status_text = "⏳ PROXY BEKLENİYOR"
        else:
            status_text = "🟢 AKTİF ÇALIŞIYOR"
    elif job_status == "Manuel Durduruldu":
        status_text = "🛑 MANUEL DURDURULDU"
    elif job_status in ("Tamamlandı", "completed"):
        status_text = "✅ TAMAMLANDI"
    elif job_status == "error":
        status_text = "❌ HATA"
    else:
        status_text = f"🔴 {job_status}" if job_status else "💤 UYKU MODU"

    # ── ZOMBIE JOB KONTROLÜ ──
    if last_ping and is_running:
        fark_sn = (datetime.now(timezone.utc) - last_ping.replace(tzinfo=timezone.utc)).total_seconds()
        if fark_sn > 160:
            is_running  = False
            sessiz_dk   = int(fark_sn // 60)
            if ana_cmd_status == "paused":
                status_text = "⏳ PROXY BEKLENİYOR"
            else:
                status_text = f"🟡 BOT YANIT VERMİYOR ({sessiz_dk} dakikadır sinyal yok)"
            
            if default_mail and get_zombie_job_id() != job_id:
                tp   = db.products.count_documents({})
                th   = db.price_history.count_documents({})
                proxy_data = list(db["proxy_performance"].find().sort("ban_count", -1).limit(5))
                html = build_report_html(latest_job, stats, tp, th, "⚠️ Bot Yanıt Vermiyor", bot_status=status_text, proxy_data=proxy_data)
                ok, _ = send_mail(default_mail, "🚨 NeuraNovaV Bot Yanıt Vermiyor!", html)
                if ok:
                    set_zombie_job_id(job_id)
    else:
        clear_zombie_flag()

    st.subheader(f"Durum: {status_text}")
    # === İLERLEME ÇUBUĞU (PROGRESS BAR) ===
    total_target = latest_job.get("total_target_urls", 0)
    total_proc = db.products.count_documents({})
    
    if total_target > 0:
        # Yüzdeyi hesapla (Maksimum %100 olsun diye min kullandık)
        yuzde = min(100, int((total_proc / total_target) * 100))
        # Streamlit progress bar 0.0 ile 1.0 arası değer alır
        try:
            toplam_sure_sn = sum(
                (d.get("end_time") - d.get("start_time")).total_seconds()
                for d in db.jobs.find({}, {"start_time": 1, "end_time": 1})
                if d.get("start_time") and d.get("end_time")
            )
            ts_h = int(toplam_sure_sn // 3600)
            ts_m = int((toplam_sure_sn % 3600) // 60)
            sure_yazi = f" | ⏱️ Toplam: {ts_h}s {ts_m}dk"
        except:
            sure_yazi = ""

        st.progress(yuzde / 100.0, text=f"🚀 Tarama İlerlemesi: %{yuzde} ({total_proc:,} / {total_target:,} Tahmini Ürün){sure_yazi}")
        try:
            start_time = latest_job.get("start_time")
            if start_time and total_proc > 0 and total_target > total_proc:
                gecen_sn = (datetime.now(timezone.utc) - start_time.replace(tzinfo=timezone.utc)).total_seconds()
                hiz = total_proc / gecen_sn  # ürün/saniye
                kalan_urun = total_target - total_proc
                kalan_sn = kalan_urun / hiz
                kalan_gun = int(kalan_sn // 86400)
                kalan_saat = int((kalan_sn % 86400) // 3600)
                kalan_dk = int((kalan_sn % 3600) // 60)

                if kalan_gun > 0:
                    sure_str = f"{kalan_gun} gün {kalan_saat} saat"
                elif kalan_saat > 0:
                    sure_str = f"{kalan_saat} saat {kalan_dk} dk"
                else:
                    sure_str = f"{kalan_dk} dakika"

                st.caption(f"⏱️ Mevcut hızda tahmini bitiş: **{sure_str}** sonra")
        except:
            pass
    else:
        # Hedef henüz hesaplanmadıysa ufak bir bilgi ver
        st.info("🔄 Tarama hedefi hesaplanıyor...")
    
    st.markdown("##### 🤖 Alt Sistem Görev Durumları")
    col_b1, col_b2, col_b3, col_b4, col_b5 = st.columns(5)
    
    bot_ui_list = [
        ("ana_bot",      "🕷️ Ana Bot",        col_b1),
        ("pw_hata",      "🚑 İtfaiye",         col_b2),
        ("pw_liste",     "🔍 Liste Kurtar",     col_b3),
        ("scrapy_fiyat", "⚡ Hızlı Fiyat",      col_b4),
        ("pw_fiyat",     "🐢 Güvenilir (PW)",   col_b5)
    ]
    
    for b_id, b_name, col in bot_ui_list:
        bot_cmd = cmd_col.find_one({"bot_id": b_id})
        if is_bot_running_db(b_id):
            b_stat = "🟢 Çalışıyor"
        else:
            b_stat = "Uyku Modu 💤"

        # Çalışma süresi hesapla
        sure_yazi = ""
        if bot_cmd:
            started = bot_cmd.get("started_at")
            stopped = bot_cmd.get("stopped_at")
            if started and stopped:
                fark = (stopped.replace(tzinfo=timezone.utc) - started.replace(tzinfo=timezone.utc)).total_seconds()
                if fark > 0:
                    sure_yazi = f"{int(fark//60)}dk {int(fark%60)}sn"
            elif started and is_bot_running_db(b_id):
                fark = (datetime.now(timezone.utc) - started.replace(tzinfo=timezone.utc)).total_seconds()
                sure_yazi = f"{int(fark//60)}dk {int(fark%60)}sn"

        with col:
            st.markdown(f"**{b_name}**")
            st.caption(b_stat)
            if sure_yazi:
                st.caption(f"⏱️ {sure_yazi}")
    st.write("")
    
    

    # --- 2. TÜM BOTLARI ZORLA KAPAT BUTONU ---
    if st.button("🚨 TÜM BOTLARI VE SÜREÇLERİ ZORLA KAPAT (KILL ALL)", width='stretch'):
        # Veritabanındaki tüm botlara 'force_stop' emri gönderiyoruz
        cmd_col.update_many(
            {"is_running": True}, 
            {"$set": {"action": "force_stop", "stop_processed": False}}
        )
        st.error("⚠️ Tüm botlara imha emri gönderildi! İşlem saniyeler içinde tamamlanacak.")

    # --- 3. YENİ: PANİK BUTONU (GÖRÜNMEZ ZOMBİLERİ TEMİZLE) ---
    if st.button("☣️ GİZLİ SÜREÇLERİ (ZOMBİ CHROME'LARI) TEMİZLE (PANİK BUTONU)", type="primary", width='stretch'):
        cmd_col.update_one(
            {"bot_id": "system"},
            {"$set": {"action": "panic_kill", "status": "pending", "stop_processed": False}},
            upsert=True
        )
        st.toast("💀 Panik emri Komuta Merkezi'ne gönderildi! RAM temizleniyor...")
        time.sleep(1) # Tost mesajı ekranda görünsün diye 1 sn bekle
        st.rerun() # RAM'in güncel halini göstermek için sayfayı yenile
    
    st.markdown("---")
    
    if latest_job:
        st.markdown("---")
        
        bekleyen_hata = db.failed_urls.count_documents({"cozuldu": False})
        
        # 2. Fiyat Güncelleme Kuyruğu (Toplam ürün - bugün fiyatı alınanlar)
        today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        bugun_guncellenen = db.price_history.count_documents({"date": today_str})
        toplam_urun = db.products.count_documents({})
        bekleyen_fiyat = max(0, toplam_urun - bugun_guncellenen) # Eksiye düşmesini engelle
        
        st.subheader("🚒 Playwright İşçi Performansı")
        pwc1, pwc2, pwc3 = st.columns(3)

        # 1. Kurtarma Operasyonu (İtfaiye)
        denenen_hata = latest_job.get("pw_hata_coz_denenen", 0)
        basarili_hata = latest_job.get("pw_hata_coz_basarili", 0)
        pwc1.metric(
            "🚒 İtfaiye: Çözülen / Bekleyen", 
            f"{basarili_hata} / {bekleyen_hata}", 
            delta=f"{denenen_hata} deneme",
            help="Playwright'ın hata kuyruğundan kurtardığı ürünler. Sağdaki rakam kuyrukta bekleyen (cozuldu: False) sayıdır."
        )

        # 2. Güvenilir Fiyat Güncelleme
        denenen_fiyat = latest_job.get("pw_fiyat_guncelle_denenen", 0)
        basarili_fiyat = latest_job.get("pw_fiyat_guncelle_basarili", 0)
        pwc2.metric(
            "🐢 PW Fiyat: Güncellenmiş / Bekleyen", 
            f"{basarili_fiyat} / {bekleyen_fiyat}", 
            delta=f"{denenen_fiyat} deneme",
            help="Playwright ile fiyatı güncellenenler. Sağdaki rakam bugün henüz fiyatı çekilmeyen ürün sayısını gösterir."
        )
    st.write("")

    # 3. PW Canlılık (Heartbeat)
    pw_ping = latest_job.get("pw_last_ping")
    if pw_ping:
        pw_sn = int((datetime.now(timezone.utc) - pw_ping.replace(tzinfo=timezone.utc)).total_seconds())
        pw_status = "🔵 AKTİF" if pw_sn < 60 else "⚪ UYKUDA"
        pwc3.metric("📡 PW Son Sinyal", pw_status, help="Playwright işçisinin son veri gönderdiği an.")
        if pw_sn < 60:
            pw_sure_str = f"{pw_sn} saniye önce"
        elif pw_sn < 3600:
            pw_sure_str = f"{pw_sn//60} dakika {pw_sn%60} sn önce"
        else:
            pw_sure_str = f"{pw_sn//3600} saat {(pw_sn%3600)//60} dk önce"
        pwc3.caption(pw_sure_str)
    else:
        pwc3.metric("📡 PW Son Sinyal", "Bağlantı Yok")
    

    # ── ÇALIŞMA SÜRESİ VE HIZ ──
    start_time = latest_job.get("start_time")
    if start_time:
        if is_running:
            elapsed = datetime.now(timezone.utc) - start_time.replace(tzinfo=timezone.utc)
        else:
            end_t   = latest_job.get("end_time") or last_ping
            elapsed = end_t.replace(tzinfo=timezone.utc) - start_time.replace(tzinfo=timezone.utc)

        total_seconds = int(elapsed.total_seconds())
        h = total_seconds // 3600
        m = (total_seconds % 3600) // 60
        s = total_seconds % 60
        elapsed_str = f"{h}s {m}dk {s}sn" if h > 0 else f"{m}dk {s}sn"
        total_proc  = latest_job.get("total_processed", 0)
        hourly_rate = int(total_proc / (total_seconds / 3600)) if total_seconds > 0 else 0

        c1, c2 = st.columns(2)
        c1.info(f"⏱️ **Çalışma Süresi:** {elapsed_str}")
        c2.info(f"⚡ **Saatlik Ortalama Verim:** ~{hourly_rate:,} ürün/saat")

    st.write("")
    
    

    # ── METRİKLER SATIR 1 ──
    r1c1, r1c2, r1c3, r1c4 = st.columns(4)

    r1c1.metric(
        "Toplam İşlenen URL",
        f"{latest_job.get('total_processed', 0):,}",
        help="Botun şu ana kadar girdiği ve okuduğu toplam ürün linki sayısı."
    )

    drop_f = stats.get("drop_fiyatsiz", 0)
    drop_h = stats.get("drop_hata", 0)
    total_dropped = drop_f + drop_h
    r1c2.metric(
        "🗑️ Toplam Çöpe Giden",
        total_dropped,
        delta_color="inverse",
        help="Fiyatı olmayan veya hatalı parse edilen, veritabanına kaydedilmeyen ürünler."
    )
    if total_dropped > 0:
        r1c2.caption(f"📌 {drop_f} Fiyatsız | {drop_h} Hatalı Veri")

    if last_ping:
        lp_aware   = last_ping.replace(tzinfo=timezone.utc)
        local_time = lp_aware.astimezone(TR_TZ).strftime("%H:%M:%S")
        since_sn   = int((datetime.now(timezone.utc) - lp_aware).total_seconds())
        r1c3.metric(
            "📡 Son Heartbeat",
            local_time,
            help="Botun her 10 üründe bir veritabanına attığı canlılık sinyalinin saati. 2 dakika sinyal gelmezse zombie olarak işaretlenir."
        )
        r1c3.caption(f"{since_sn} saniye önce")
    else:
        r1c3.metric("📡 Son Heartbeat", "Sinyal Yok")

    current_page = latest_job.get("current_page", "Belirsiz")
    r1c4.metric(
        "📄 Taranan Sayfa (pi)",
        f"Sayfa {current_page}",
        help="Botun şu anda Trendyol kategori listesinin kaçıncı sayfasını (pi=X) taradığını gösterir."
    )
    
    

    st.write("")

    # ── METRİKLER SATIR 2 ──
    r2c1, r2c2, r2c3, r2c4 = st.columns(4)

    r2c1.metric(
        "✨ Yeni Keşfedilen Ürün",
        stats.get("yeni_urun", 0),
        help="Bu çalışmada veritabanında daha önce hiç olmayan, ilk kez eklenen ürün sayısı."
    )
    r2c2.metric(
        "📅 Bugünün İlk Kaydı",
        stats.get("yeni_gun_kaydi", 0),
        help="Ürünü tanıyoruz ama bugün için henüz fiyat kaydı yoktu. Günlük fiyat serisine ilk kez eklenenler."
    )
    r2c3.metric(
        "🔄 Gün İçi Değişim",
        stats.get("gun_ici_degisim", 0),
        help="Bugün içinde daha önce kaydedilen fiyat veya puan verisi değişmiş olan ürünler."
    )
    kat_stats = latest_job.get("kategori_stats", {})
    benzersiz_kat_sayisi = len(kat_stats)
    r2c4.metric(
        label="📂 Kategori Çeşitliliği",
        value=f"{benzersiz_kat_sayisi} ",
        help="Botun bu oturumda (Job) taradığı ürünlerin kaç farklı ana kategoriden (reyondan) geldiğini gösterir."
    )

    st.markdown("---")

    # ── GRAFİKLER ──
    g1, g2 = st.columns([2, 1])

    with g1:
        st.subheader("🔍 Veri Kalite Analizi")
        drop_data = {
            "Durum": ["Yeni Ürün", "Bugünün İlk Kaydı", "Gün İçi Değişim", "Çöp (Fiyatsız)", "Çöp (Hata)"],
            "Adet": [
                stats.get("yeni_urun", 0),
                stats.get("yeni_gun_kaydi", 0),
                stats.get("gun_ici_degisim", 0),
                stats.get("drop_fiyatsiz", 0),
                stats.get("drop_hata", 0)
            ]
        }
        df_drop = pd.DataFrame(drop_data)
        if df_drop["Adet"].sum() > 0:
            fig = px.pie(df_drop, values="Adet", names="Durum", hole=0.4,
                         color_discrete_sequence=px.colors.sequential.RdBu)
            st.plotly_chart(fig, width='stretch')
        else:
            st.info("Grafik için veri bekleniyor...")

    with g2:
        st.subheader("⚡ Veritabanı Durumu")
        total_products = db.products.count_documents({})
        st.metric(
            "Toplam Benzersiz Ürün",
            f"{total_products:,}",
            help="Her Trendyol URL'si için tek bir ürün kaydı tutulur. Bu sayı toplam izlenen ürün adedini gösterir."
        )
        st.caption("Her URL için tek ürün kaydı tutulur.")

        total_history = db.price_history.count_documents({})
        st.metric(
            "Toplam Fiyat Geçmişi",
            f"{total_history:,}",
            help="Her ürün için her güne ait bir fiyat kaydı tutulur. Bu sayı toplam fiyat veri noktası adedini gösterir."
        )
        st.caption("Fiyat dalgalanmalarını analiz etmek için tutulan günlük zaman serisi.")
        try:
            db_stats = db.command("dbStats")
            veri_mb = db_stats.get("dataSize", 0) / (1024*1024)
            index_mb = db_stats.get("indexSize", 0) / (1024*1024)
            st.metric("💾 MongoDB Disk Kullanımı", f"{veri_mb:.1f} MB",
                    delta=f"Index: {index_mb:.1f} MB")
        except:
            pass

    st.markdown("---")

    # ── KATEGORİ DAĞILIMI ──
    st.subheader("📂 Kategoriye Göre Çekilen Ürün Sayısı")
    cat_pipeline = [
        {"$group": {"_id": "$category", "count": {"$sum": 1}}},
        {"$sort":  {"count": -1}},
        {"$limit": 10}
    ]
    categories = list(db.products.aggregate(cat_pipeline))
    if categories:
        df_cat = pd.DataFrame(categories)
        df_cat.columns = ["Kategori", "Ürün Sayısı"]
        df_cat["Kategori"] = df_cat["Kategori"].apply(
            lambda x: str(x).split(">")[-1].strip() if x else "Bilinmiyor"
        )
        fig_cat = px.bar(
            df_cat, x="Ürün Sayısı", y="Kategori", orientation="h",
            color="Ürün Sayısı", color_continuous_scale="Blues"
        )
        fig_cat.update_layout(
            yaxis=dict(autorange="reversed"),
            showlegend=False,
            margin=dict(l=0, r=0, t=10, b=0)
        )
        st.plotly_chart(fig_cat, width='stretch')
    else:
        st.info("Kategori verisi için önce botu çalıştırın.")

    st.markdown("---")
    
    # 1. BÖLÜM: SAATLİK HIZ GRAFİĞİ
    st.subheader("⏱️ Saat Bazlı Tarama Performansı")
    try:
        sinir = datetime.now(timezone.utc) - timedelta(hours=48)
        tum_jobs = list(db.jobs.find(
            {"start_time": {"$gte": sinir}},
            {"hourly_stats": 1, "start_time": 1}
        ).sort("start_time", 1))
        tum_satirlar = []
        for job in tum_jobs:
            job_start = job.get("start_time")
            if not job_start:
                continue
            job_start = job_start.replace(tzinfo=timezone.utc)
            for h in job.get("hourly_stats", []):
                try:
                    saat_str = h.get("saat", "")
                    saat_int = int(saat_str.split(":")[0])
                    dk_int = int(saat_str.split(":")[1]) if ":" in saat_str else 0
                    from datetime import time as dtime
                    dt = datetime.combine(job_start.date(), dtime(saat_int, dk_int)).replace(tzinfo=timezone.utc)
                    if dt < job_start - timedelta(hours=1):
                        dt = dt + timedelta(days=1)
                    tum_satirlar.append({
                        "Zaman": dt.astimezone(TR_TZ),
                        "Hız (Ürün/Dk)": h.get("hiz_urun_dk", 0),
                    })
                except:
                    pass
        if tum_satirlar:
            df_hourly2 = pd.DataFrame(tum_satirlar).sort_values("Zaman").drop_duplicates("Zaman")
            annotations = []
            hizlar = df_hourly2["Hız (Ürün/Dk)"].tolist()
            zamanlar = df_hourly2["Zaman"].tolist()
            for i in range(1, len(hizlar)):
                onceki = hizlar[i-1] if hizlar[i-1] > 0 else 1
                degisim = (hizlar[i] - hizlar[i-1]) / onceki
                if degisim < -0.4 and hizlar[i-1] > 10:
                    try:
                        zaman_utc = zamanlar[i].astimezone(timezone.utc)
                        proxy_log = db["proxy_logs"].find_one({"ts": {"$gte": zaman_utc - timedelta(minutes=10), "$lte": zaman_utc + timedelta(minutes=10)}})
                        neden = "🔄 Proxy yenilendi" if proxy_log else "📉 Hız düştü"
                    except:
                        neden = "📉 Hız düştü"
                    annotations.append({"zaman": zamanlar[i], "hiz": hizlar[i], "neden": neden})
                elif degisim > 0.5 and hizlar[i-1] < 50:
                    try:
                        zaman_utc = zamanlar[i].astimezone(timezone.utc)
                        proxy_log = db["proxy_logs"].find_one({"ts": {"$gte": zaman_utc - timedelta(minutes=10), "$lte": zaman_utc + timedelta(minutes=10)}})
                        neden = "✅ Proxy yenilendi" if proxy_log else "📈 Hız yükseldi"
                    except:
                        neden = "📈 Hız yükseldi"
                    annotations.append({"zaman": zamanlar[i], "hiz": hizlar[i], "neden": neden})
            fig_speed = go.Figure()
            fig_speed.add_trace(go.Scatter(
                x=df_hourly2["Zaman"], y=df_hourly2["Hız (Ürün/Dk)"],
                mode="lines+markers", line=dict(color="#4fc3f7", width=2), marker=dict(size=5)
            ))
            for ann in annotations:
                fig_speed.add_annotation(
                    x=ann["zaman"], y=ann["hiz"], text=ann["neden"],
                    showarrow=True, arrowhead=2, arrowcolor="#ff7043",
                    font=dict(size=10, color="#ff7043"), bgcolor="rgba(30,30,30,0.8)"
                )
            fig_speed.update_layout(
                title="Anlık Tarama Hızı (Son 48 Saat)",
                xaxis=dict(type="date", tickformat="%d/%m %H:%M"),
                template="plotly_dark", margin=dict(l=0, r=0, t=40, b=0),
                hovermode="x unified"
            )
            st.plotly_chart(fig_speed, width='stretch')
        else:
            st.info("Saatlik performans verisi henüz oluşmadı (Botun en az 1 saat çalışması lazım).")
    except Exception as e:
        st.error(f"Grafik hatası: {e}")

    st.markdown("---")

    # ── CANLI VERİ AKIŞI ──
    # 2. BÖLÜM: CANLI VERİ AKIŞI (Son Eklenen 5 Ürün)
    st.subheader("📡 Canlı Veri Akışı (Son Eklenen 5 Ürün)")
    if current_page != "Belirsiz":
        st.caption(f"🔖 Bot şu an Trendyol'da **Sayfa {current_page}** üzerinde tarama yapıyor.")

    # MongoDB'den son 5 ürünü çekiyoruz
    cursor = db.products.find(
        {}, {"title": 1, "category": 1, "last_seen": 1}
    ).sort("last_seen", -1).limit(5)
    recent_products = list(cursor)

    if recent_products:
        df_recent = pd.DataFrame(recent_products)
        if "_id" in df_recent.columns:
            df_recent = df_recent.drop(columns=["_id"])
        
        # Kategoriyi temizle (pipelines (2).py formatına uygun)
        df_recent["category"] = df_recent["category"].apply(
            lambda x: str(x).split(">")[-1].strip() if x else "-"
        )
        # Türkiye saatine çevir
        df_recent["last_seen"] = pd.to_datetime(
            df_recent["last_seen"], utc=True
        ).dt.tz_convert("Europe/Istanbul").dt.strftime("%H:%M:%S")
        
        df_recent = df_recent[["title", "category", "last_seen"]]
        df_recent.columns = ["Ürün Adı", "Kategori", "İşlem Saati"]
        st.table(df_recent)
    else:
        st.write("Henüz veri akışı yok.")
        
    st.markdown("---")

    # ── FAZ 5: PROXY İSTİHBARAT MERKEZİ ──
    st.subheader("🛡️ Proxy İstihbarat Merkezi")

    try:
        son_log = db["proxy_logs"].find_one(sort=[("ts", -1)])
        if son_log:
            son_guncelleme = son_log.get("ts")
            if son_guncelleme:
                gecen_sn = (datetime.now(timezone.utc) - son_guncelleme.replace(tzinfo=timezone.utc)).total_seconds()
                interval = 3600  # extensions.py'daki interval ile aynı
                kalan_sn = max(0, interval - gecen_sn)
                kalan_dk = int(kalan_sn // 60)
                kalan_s  = int(kalan_sn % 60)
                gecen_dk = int(gecen_sn // 60)

                st.info(
                    f"🕐 Son proxy güncellemesi: **{gecen_dk} dk önce** | "
                    f"⏳ Sonraki güncelleme: **{kalan_dk} dk {kalan_s:02d} sn** sonra"
                )
                try:
                    emekli_proxy = db["proxy_performance"].count_documents({"retired": True})
                    proxy_stats  = db["bot_commands"].find_one({"bot_id": "proxy_stats"})
                    toplam_proxy = proxy_stats.get("aktif_proxy", 0) if proxy_stats else 0
                    scrapy_good  = proxy_stats.get("scrapy_good", 0) if proxy_stats else 0
                    scrapy_dead  = proxy_stats.get("scrapy_dead", 0) if proxy_stats else 0
                    aktif_proxy  = max(0, toplam_proxy - emekli_proxy)

                    pc1, pc2, pc3, pc4 = st.columns(4)
                    pc1.metric("🟢 Scrapy Good",   f"{scrapy_good}")
                    pc2.metric("✅ Aktif Havuz",    f"{aktif_proxy}")
                    pc3.metric("🚫 Emekli Proxy",   f"{emekli_proxy}")
                    pc4.metric("📦 Toplam Havuz",   f"{toplam_proxy}")
                except:
                    pass
    except Exception as e:
        pass

    
    p1, p2 = st.columns(2)

    with p1:
        st.markdown("#### 🌐 Kaynak Sağlık Durumu (Son 5 Güncelleme)")
        try:
            son_loglar = list(db["proxy_logs"].find(
                {"erisim_ok": True}
            ).sort("ts", -1).limit(5))
            
            if son_loglar:
                # Toplam özet satırı
                toplam_proxy = sum(k.get('toplam') or 0 for k in son_loglar)
                toplam_yeni  = sum(k.get('yeni_eklenen') or 0 for k in son_loglar)
                toplam_cop   = sum(k.get('cop') or 0 for k in son_loglar)
                st.markdown(f"📊 **Son tur toplamı:** {toplam_proxy} proxy | +{toplam_yeni} yeni | 🗑️ {toplam_cop} çöp")
                st.markdown("---")
                for k in son_loglar:
                    ts = k.get("ts")
                    if ts:
                        ts_tr = ts.replace(tzinfo=timezone.utc).astimezone(TR_TZ)
                        zaman = ts_tr.strftime("%d/%m %H:%M")
                    else:
                        zaman = "-"
                    st.markdown(
                        f"✅ **{k.get('kaynak', '?')}** | "
                        f"{k.get('toplam') or 0} proxy | "
                        f"TR: {k.get('tr') or 0} | "
                        f"Çöp: {k.get('cop') or 0} | "
                        f"+{k.get('yeni_eklenen') or 0} yeni | "
                        f"_{zaman}_"
                    )
            else:
                st.info("🕐 Bot henüz çalışmadı, kaynak verisi bekleniyor...")
        except Exception as e:
            st.error(f"Kaynak log hatası: {e}")

    with p2:
        st.markdown("#### 📈 Proxy Performans Analizi (Top 10)")
        try:
            perf = list(db["proxy_performance"].find().sort("ban_count", -1).limit(10))
            if perf:
                df_p = pd.DataFrame(perf)
                if "proxy" in df_p.columns:
                    # Eğer proxy ['http://...'] şeklindeyse içindeki metni alır, değilse string'e çevirir
                    df_p["proxy"] = df_p["proxy"].apply(lambda x: x[0] if isinstance(x, list) else str(x))
                
                if "success_count" not in df_p.columns: df_p["success_count"] = 0
                if "ban_count"     not in df_p.columns: df_p["ban_count"]     = 0
                if "retired"       not in df_p.columns: df_p["retired"]       = False
                # Başarı Oranı Hesabı (replace(0,1) ile 0'a bölünme hatası engellenir)
                toplam = df_p["success_count"] + df_p["ban_count"]
                df_p["Başarı %"] = (df_p["success_count"] / toplam.replace(0, 1) * 100).round(1)
                
                # Durum metni (Emoji desteği ile)
                df_p["Durum"] = df_p["retired"].apply(lambda x: "🚫 Emekli" if x else "✅ Aktif")
                
                # Tabloyu son haline getir
                df_goster = df_p[["proxy", "success_count", "ban_count", "Başarı %", "Durum"]].copy()
                df_goster.columns = ["Proxy Adresi", "Başarılı", "Ban", "Başarı %", "Durum"]
                
                # Renklendirme yapmadan düz tablo olarak bas (Daha güvenli)
                st.dataframe(df_goster, width='stretch', hide_index=True)
                
                # Emeklilik Uyarısı (Madde 20)
                emekli_sayisi = int(df_p["retired"].sum())
                if emekli_sayisi > 0:
                    st.warning(f"⚠️ {emekli_sayisi} proxy emekliye ayrıldı (10+ ban)")
            else:
                st.info("🕐 Bot henüz çalışmadı, proxy verisi bekleniyor...")
                
        except Exception as e:
            st.error(f"Proxy performans hatası: {e}")
            
    
    st.markdown("---")
    

    # ── FAZ 6: URL HATA TAKİP MERKEZİ ──
    st.subheader("🔴 URL Hata Takip Merkezi")

    try:
        failed_col = db["failed_urls"]
        toplam_hata    = failed_col.count_documents({})
        cozulmemis     = failed_col.count_documents({"cozuldu": False})
        cozulmus       = failed_col.count_documents({"cozuldu": True})

        # ── ÖZET METRİKLER ──
        m1, m2, m3 = st.columns(3)
        m1.metric("🔴 Toplam Hatalı URL", f"{toplam_hata:,}")
        m2.metric("⏳ Çözülmemiş", f"{cozulmemis:,}", delta_color="inverse")
        m3.metric("✅ Çözülmüş", f"{cozulmus:,}")

        if toplam_hata > 0:
            f1, f2 = st.columns(2)

            # ── HATA TİPİ DAĞILIMI (pasta grafik) ──
            with f1:
                st.markdown("#### 📊 Hata Tipine Göre Dağılım")
                hata_pipeline = [
                    {"$group": {"_id": "$hata_tipi", "count": {"$sum": 1}}},
                    {"$sort": {"count": -1}}
                ]
                hata_dagilim = list(failed_col.aggregate(hata_pipeline))
                if hata_dagilim:
                    df_hata = pd.DataFrame(hata_dagilim)
                    df_hata.columns = ["Hata Tipi", "Adet"]
                    fig_hata = px.pie(df_hata, values="Adet", names="Hata Tipi", hole=0.4,
                                     color_discrete_sequence=px.colors.sequential.Reds_r)
                    st.plotly_chart(fig_hata, width='stretch')

            # ── ÇÖZÜLMEMIŞ vs ÇÖZÜLMÜŞ ──
            with f2:
                st.markdown("#### 🔄 Çözülmemiş vs Çözülmüş")
                df_durum = pd.DataFrame([
                    {"Durum": "⏳ Çözülmemiş", "Adet": cozulmemis},
                    {"Durum": "✅ Çözülmüş",   "Adet": cozulmus},
                ])
                fig_durum = px.pie(df_durum, values="Adet", names="Durum", hole=0.4,
                                   color_discrete_map={"⏳ Çözülmemiş": "#e53935", "✅ Çözülmüş": "#43a047"})
                st.plotly_chart(fig_durum, width='stretch')

            # ── EN ÇOK HATA ALAN URL'LER (Top 10) ──
            st.markdown("#### 🔗 En Çok Hata Alan URL'ler (Top 10)")
            top_urls = list(failed_col.find(
                {}, {"url": 1, "hata_tipi": 1, "deneme_sayisi": 1, "proxy_listesi": 1, "cozuldu": 1}
            ).sort("deneme_sayisi", -1).limit(10))

            if top_urls:
                df_urls = pd.DataFrame(top_urls)
                if "proxy_listesi" not in df_urls.columns:
                    df_urls["proxy_listesi"] = None
                df_urls["proxy_sayisi"] = df_urls["proxy_listesi"].apply(
                    lambda x: len(x) if isinstance(x, list) else 0
                )
                df_urls["Durum"] = df_urls["cozuldu"].apply(
                    lambda x: "✅ Çözüldü" if x else "⏳ Bekliyor"
                )
                df_urls = df_urls[["url", "hata_tipi", "deneme_sayisi", "proxy_sayisi", "Durum"]].copy()
                df_urls.columns = ["URL", "Son Hata", "Deneme", "Proxy Sayısı", "Durum"]
                st.dataframe(df_urls, width='stretch', hide_index=True)

            # ── EN ÇOK BAŞARISIZ PROXY'LER ──
            st.markdown("#### 🛡️ URL Bazlı En Çok Başarısız Proxy'ler")
            proxy_pipeline = [
                {"$unwind": "$proxy_listesi"},
                {"$group": {"_id": "$proxy_listesi", "basarisiz_url": {"$sum": 1}}},
                {"$sort": {"basarisiz_url": -1}},
                {"$limit": 10}
            ]
            proxy_basarisiz = list(failed_col.aggregate(proxy_pipeline))
            if proxy_basarisiz:
                df_pb = pd.DataFrame(proxy_basarisiz)
                df_pb.columns = ["Proxy", "Başarısız URL Sayısı"]
                fig_pb = px.bar(df_pb, x="Başarısız URL Sayısı", y="Proxy", orientation="h",
                                color="Başarısız URL Sayısı", color_continuous_scale="Reds")
                fig_pb.update_layout(yaxis=dict(autorange="reversed"),
                                     margin=dict(l=0, r=0, t=10, b=0))
                st.plotly_chart(fig_pb, width='stretch')
        else:
            st.info("🕐 Henüz hata kaydı yok, bot çalışınca burası dolacak.")

    except Exception as e:
        st.error(f"URL hata takip hatası: {e}")

else:
    st.warning("Henüz başlatılmış bir görev bulunamadı. Lütfen botu çalıştırın: `scrapy crawl trendyol`")
    
    