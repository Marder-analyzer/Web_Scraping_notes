import streamlit as st
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
from dotenv import load_dotenv

load_dotenv()

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
refresh_count = st_autorefresh(interval=30000, limit=100000, key="auto_refresh")

# Ekran kararmasını ve "Running..." ikonunu engelle
st.markdown("""
    <style>
        .stApp, [data-testid="stAppViewContainer"],
        [data-testid="stMainBlockContainer"],
        section[data-testid="stMain"] {
            opacity: 1 !important;
            filter: none !important;
            transition: none !important;
            animation: none !important;
        }
        [data-testid="stStatusWidget"] { visibility: hidden !important; }
    </style>
""", unsafe_allow_html=True)

# Son yenileme zamanı
if "last_refresh_time" not in st.session_state:
    st.session_state["last_refresh_time"] = datetime.now(TR_TZ).strftime("%H:%M:%S")
if refresh_count and refresh_count > 0:
    st.session_state["last_refresh_time"] = datetime.now(TR_TZ).strftime("%H:%M:%S")

# Hata logu
if "error_log" not in st.session_state:
    st.session_state["error_log"] = []

# ─────────────────────────────────────────────
# YARDIMCI FONKSİYONLAR
# ─────────────────────────────────────────────
def log_error(msg):
    ts = datetime.now(TR_TZ).strftime("%H:%M:%S")
    st.session_state["error_log"].insert(0, f"[{ts}] {msg}")
    st.session_state["error_log"] = st.session_state["error_log"][:20]

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
def build_report_html(job, stats, total_products, total_history, subject_prefix="📊 Rapor", bot_status=None):
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

    return f"""
    <html><body style="font-family:Arial,sans-serif;background:#f4f4f4;padding:20px">
    <div style="max-width:600px;margin:auto;background:white;border-radius:12px;padding:24px;box-shadow:0 2px 8px #ccc">
        <h2 style="color:#6a0dad">&#128760; NeuraNovaV Bot Raporu</h2>
        <p style="color:#555">{subject_prefix} &mdash; {datetime.now(TR_TZ).strftime('%d %B %Y %H:%M')}</p>
        <hr/>
        <h3>Operasyon Özeti</h3>
        <table style="width:100%;border-collapse:collapse">
            <tr><td style="padding:8px;background:#f9f9f9"><b>Bot Durumu</b></td><td style="padding:8px">{status}</td></tr>
            <tr><td style="padding:8px"><b>Toplam İşlenen URL</b></td><td style="padding:8px">{toplam:,}</td></tr>
            <tr><td style="padding:8px;background:#f9f9f9"><b>Çalışma Süresi</b></td><td style="padding:8px;background:#f9f9f9">{round(sure/60,1)} dakika</td></tr>
        </table>
        <h3>Veri Detayları</h3>
        <table style="width:100%;border-collapse:collapse">
            <tr><td style="padding:8px;background:#e8f5e9"><b>Yeni Keşfedilen Ürün</b></td><td style="padding:8px;background:#e8f5e9;color:#2e7d32"><b>{yeni:,}</b></td></tr>
            <tr><td style="padding:8px"><b>Bugünün İlk Kaydı</b></td><td style="padding:8px;color:#1565c0"><b>{gun_kaydi:,}</b></td></tr>
            <tr><td style="padding:8px;background:#f9f9f9"><b>Gün İçi Değişim</b></td><td style="padding:8px;background:#f9f9f9;color:#e65100"><b>{degisim:,}</b></td></tr>
            <tr><td style="padding:8px"><b>Fiyatsız (Düşürülen)</b></td><td style="padding:8px;color:#c62828"><b>{fiyatsiz:,}</b></td></tr>
            <tr><td style="padding:8px;background:#f9f9f9"><b>Hatalı (Düşürülen)</b></td><td style="padding:8px;background:#f9f9f9;color:#c62828"><b>{hata:,}</b></td></tr>
        </table>
        <h3>Veritabanı Durumu</h3>
        <table style="width:100%;border-collapse:collapse">
            <tr><td style="padding:8px;background:#f9f9f9"><b>Toplam Benzersiz Ürün</b></td><td style="padding:8px;background:#f9f9f9">{total_products:,}</td></tr>
            <tr><td style="padding:8px"><b>Toplam Fiyat Geçmişi Kaydı</b></td><td style="padding:8px">{total_history:,}</td></tr>
        </table>
        <hr/>
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
                html = build_report_html(jfm, s, tp, th, "📤 Manuel Rapor", bot_status=jfm_status)
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
                    html = build_report_html(jfm, s, tp, th, "📤 Hızlı Rapor", bot_status=jfm_status)
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
    st.warning("MongoDB şu anda kapalı veya yanıt vermiyor.")
    st.info("🛠️ Docker Desktop'ı açın, MongoDB container'ını başlatın (▶️), ardından 'Anında Yenile'ye tıklayın.")
    st.stop()

db = client["neuranovav_db"]

default_mail = load_saved_mails()
default_mail = default_mail[0] if default_mail else None

# ─────────────────────────────────────────────
# ANA İÇERİK VE ZOMBIE KONTROLÜ
# ─────────────────────────────────────────────
latest_job = db.jobs.find_one(sort=[("start_time", pymongo.DESCENDING)])

if latest_job:
    stats      = latest_job.get("stats", {})
    job_id     = latest_job.get("job_id", "")
    is_running = latest_job.get("status") == "Running"
    last_ping  = latest_job.get("last_ping") or latest_job.get("start_time")
    status_text = "🟢 AKTİF ÇALIŞIYOR" if is_running else "🔴 TAMAMLANDI"

    # ── ZOMBIE JOB KONTROLÜ ──
    if last_ping and is_running:
        fark_sn = (datetime.now(timezone.utc) - last_ping.replace(tzinfo=timezone.utc)).total_seconds()
        if fark_sn > 120:
            is_running  = False
            sessiz_dk   = int(fark_sn // 60)
            status_text = f"🟡 BOT YANIT VERMİYOR ({sessiz_dk} dakikadır sinyal yok)"
            
            if default_mail and get_zombie_job_id() != job_id:
                tp   = db.products.count_documents({})
                th   = db.price_history.count_documents({})
                html = build_report_html(latest_job, stats, tp, th, "⚠️ Bot Yanıt Vermiyor", bot_status=status_text)
                ok, _ = send_mail(default_mail, "🚨 NeuraNovaV Bot Yanıt Vermiyor!", html)
                if ok:
                    set_zombie_job_id(job_id)
    else:
        clear_zombie_flag()

    st.subheader(f"Durum: {status_text}")

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
    r2c1, r2c2, r2c3 = st.columns(3)

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
            st.plotly_chart(fig, use_container_width=True)
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
        st.plotly_chart(fig_cat, use_container_width=True)
    else:
        st.info("Kategori verisi için önce botu çalıştırın.")

    st.markdown("---")

    # ── CANLI VERİ AKIŞI ──
    st.subheader("📡 Canlı Veri Akışı (Son Eklenen 5 Ürün)")
    if current_page != "Belirsiz":
        st.caption(f"🔖 Bot şu an Trendyol'da **Sayfa {current_page}** üzerinde tarama yapıyor.")

    cursor = db.products.find(
        {}, {"title": 1, "category": 1, "last_seen": 1}
    ).sort("last_seen", -1).limit(5)
    recent_products = list(cursor)

    if recent_products:
        df_recent = pd.DataFrame(recent_products)
        if "_id" in df_recent.columns:
            df_recent = df_recent.drop(columns=["_id"])
        df_recent["category"] = df_recent["category"].apply(
            lambda x: str(x).split(">")[-1].strip() if x else "-"
        )
        df_recent["last_seen"] = pd.to_datetime(
            df_recent["last_seen"], utc=True
        ).dt.tz_convert("Europe/Istanbul").dt.strftime("%H:%M:%S")
        df_recent = df_recent[["title", "category", "last_seen"]]
        df_recent.columns = ["Ürün Adı", "Kategori", "İşlem Saati"]
        df_recent.index = range(1, len(df_recent) + 1)
        st.table(df_recent)
    else:
        st.write("Henüz veri akışı yok.")

else:
    st.warning("Henüz başlatılmış bir görev bulunamadı. Lütfen botu çalıştırın: `scrapy crawl trendyol`")