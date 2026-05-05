import streamlit as st
import pandas as pd
import json
import math
import google.generativeai as genai
from PIL import Image
import gspread
from google.oauth2.service_account import Credentials
import datetime

# --- CONFIG ---
BRANCH_CONFIG = {
    "208413": "อโศก",
    "205711": "พระราม 3",
    "206025": "แฟชั่น 3",
    "207033": "แฟชั่น B",
    "990221": "เอสพลานาด"
}

CSV_CONFIG = {
    "date_col": "วันที่เปิดบิล",
    "item_col": "ชื่อเมนู",
    "qty_col": "จำนวน",
    "amount_col": "ยอดขายสุทธิ"
}

# --- Google Sheets ---
@st.cache_resource
def get_gspread_client():
    creds_info = json.loads(st.secrets["GCP_SERVICE_ACCOUNT"])
    creds = Credentials.from_service_account_info(creds_info, scopes=["https://www.googleapis.com/auth/spreadsheets"])
    return gspread.authorize(creds)

def get_google_sheet():
    return get_gspread_client().open_by_key(st.secrets["SHEET_ID"]).worksheet("Data")

def clean_for_sheets(value):
    if value is None:
        return ""
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return ""
    return value

# --- AI ---
def analyze_receipts(images, model_version):
    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
    api_model_name = 'gemini-2.5-flash' if model_version == "Flash (เน้นแม่นยำ)" else 'gemini-2.5-flash-lite'
    model = genai.GenerativeModel(api_model_name)
    prompt = f"""
    Find VID number in the receipt header. Valid VIDs: {list(BRANCH_CONFIG.keys())}
    Extract for each item line where Total_Amount > 0.

    The receipt lines ALWAYS follow this exact structure in 2 rows:
    Row 1: [Line Number]. [Item Name]
    Row 2: [Item Code]   [Unit Price]   [Quantity]   [Total Amount]

    Example:
    2. ข้าวมันไก่ทอด
    FMFC033-002  60  33 1,980.00
    → code: "FMFC033-002", unit_price: 60.0, qty: 33, total_amount: 1980.0

    Return ONLY JSON list: [{{"vid": "str", "code": "str", "unit_price": float, "qty": int, "total_amount": float}}]
    """
    for attempt in range(3):
        try:
            response = model.generate_content([prompt] + images)
            text = response.text.strip()
            if not text:
                raise ValueError("AI returned empty response")
            return json.loads(text.replace("```json", "").replace("```", "").strip())
        except (ValueError, json.JSONDecodeError) as e:
            if attempt == 2:
                raise ValueError(f"AI ไม่สามารถอ่านสลิปได้ ({e}) — ลองใช้โหมดอื่นหรืออัปโหลดรูปใหม่")
            import time; time.sleep(2)

# ============================================================
# UI
# ============================================================
st.set_page_config(page_title="Power One One-Stop", page_icon="⚡", layout="wide")

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Sarabun:wght@300;400;500;600;700;800&display=swap');

html, body, [class*="css"], .stApp, .stMarkdown, .stButton,
input, textarea, select, label, p, h1, h2, h3, h4, span, div {
    font-family: 'Sarabun', sans-serif !important;
}

/* ── App background ── */
.stApp { background: #0d1117; }
.block-container { padding: 1.5rem 1.5rem 3rem !important; max-width: 960px; }

/* ── Hero header ── */
.hero {
    background: linear-gradient(135deg, #0f2027 0%, #203a43 50%, #2c5364 100%);
    border-radius: 16px;
    padding: 28px 28px 22px;
    margin-bottom: 28px;
    border: 1px solid rgba(255,255,255,0.07);
    box-shadow: 0 8px 40px rgba(0,0,0,0.5);
    position: relative;
    overflow: hidden;
}
.hero::before {
    content: '';
    position: absolute;
    top: -40px; right: -40px;
    width: 200px; height: 200px;
    background: radial-gradient(circle, rgba(240,175,0,0.12) 0%, transparent 70%);
    pointer-events: none;
}
.hero-title {
    font-size: 24px;
    font-weight: 800;
    color: #f1f5f9;
    margin: 0 0 4px 0;
    letter-spacing: 0.3px;
}
.hero-sub {
    font-size: 13px;
    color: #94a3b8;
    margin: 0 0 12px 0;
}
.hero-badge {
    display: inline-block;
    background: linear-gradient(90deg, #f0af00, #e07800);
    color: #000;
    font-size: 10px;
    font-weight: 800;
    padding: 3px 12px;
    border-radius: 20px;
    letter-spacing: 1.5px;
    text-transform: uppercase;
}

/* ── Section cards ── */
.card {
    background: #161b22;
    border: 1px solid #21262d;
    border-radius: 12px;
    padding: 20px 22px 16px;
    margin-bottom: 18px;
}
.card-header {
    display: flex;
    align-items: center;
    gap: 10px;
    margin-bottom: 14px;
    padding-bottom: 12px;
    border-bottom: 1px solid #21262d;
}
.step-num {
    background: linear-gradient(135deg, #2563eb, #1d4ed8);
    color: #fff;
    font-size: 11px;
    font-weight: 700;
    width: 26px; height: 26px;
    border-radius: 50%;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    flex-shrink: 0;
}
.card-title {
    color: #e2e8f0;
    font-size: 15px;
    font-weight: 600;
    margin: 0;
}

/* ── Date info banner ── */
.info-banner {
    background: rgba(37,99,235,0.12);
    border: 1px solid rgba(37,99,235,0.35);
    border-left: 3px solid #3b82f6;
    border-radius: 8px;
    padding: 10px 14px;
    color: #93c5fd;
    font-size: 13.5px;
    margin-top: 4px;
}

/* ── Scan button ── */
.stButton > button[kind="primary"] {
    background: linear-gradient(135deg, #1d4ed8, #1e40af) !important;
    color: #fff !important;
    border: none !important;
    border-radius: 10px !important;
    font-size: 15px !important;
    font-weight: 600 !important;
    padding: 0.6rem 1.2rem !important;
    box-shadow: 0 4px 18px rgba(29,78,216,0.45) !important;
    letter-spacing: 0.2px !important;
    transition: all 0.18s ease !important;
}
.stButton > button[kind="primary"]:hover {
    background: linear-gradient(135deg, #2563eb, #1d4ed8) !important;
    box-shadow: 0 6px 24px rgba(37,99,235,0.55) !important;
    transform: translateY(-1px) !important;
}

/* ── Save button (wraps last primary button) ── */
.save-wrap .stButton > button[kind="primary"] {
    background: linear-gradient(135deg, #047857, #065f46) !important;
    box-shadow: 0 4px 18px rgba(4,120,87,0.45) !important;
}
.save-wrap .stButton > button[kind="primary"]:hover {
    background: linear-gradient(135deg, #059669, #047857) !important;
    box-shadow: 0 6px 24px rgba(5,150,105,0.55) !important;
}

/* ── Summary section ── */
.summary-card {
    background: linear-gradient(135deg, #0a2818, #0f3d24);
    border: 1px solid rgba(16,185,129,0.25);
    border-radius: 12px;
    padding: 18px 22px;
    margin: 18px 0 12px;
}
.summary-card-title {
    color: #6ee7b7;
    font-size: 15px;
    font-weight: 600;
    margin: 0 0 14px 0;
    display: flex;
    align-items: center;
    gap: 8px;
}

/* ── Metric box ── */
[data-testid="metric-container"] {
    background: linear-gradient(135deg, #1e2d40, #1e3a5f) !important;
    border: 1px solid rgba(251,191,36,0.3) !important;
    border-radius: 12px !important;
    padding: 14px 20px !important;
}
[data-testid="stMetricValue"] {
    color: #fbbf24 !important;
    font-size: 30px !important;
    font-weight: 800 !important;
}
[data-testid="stMetricLabel"] {
    color: #93c5fd !important;
    font-size: 13px !important;
    font-weight: 500 !important;
}

/* ── Inputs & radio ── */
[data-testid="stDateInput"] > div > div > input {
    background: #21262d !important;
    border: 1px solid #30363d !important;
    color: #e2e8f0 !important;
    border-radius: 8px !important;
}
[data-testid="stRadio"] label {
    color: #cbd5e1 !important;
    font-size: 14px !important;
}
[data-testid="stRadio"] [data-testid="stMarkdownContainer"] p {
    color: #cbd5e1 !important;
}

/* ── File uploader ── */
[data-testid="stFileUploader"] section {
    background: #161b22 !important;
    border: 2px dashed #30363d !important;
    border-radius: 10px !important;
}
[data-testid="stFileUploader"] section:hover {
    border-color: #3b82f6 !important;
}

/* ── Dataframe ── */
[data-testid="stDataFrame"] { border-radius: 10px; overflow: hidden; }

/* ── Alert messages ── */
[data-testid="stAlert"] { border-radius: 10px !important; font-size: 14px !important; }

/* ── Divider ── */
hr { border-color: #21262d !important; margin: 18px 0 !important; }

/* ── Hide default Streamlit branding ── */
#MainMenu { visibility: hidden; }
footer { visibility: hidden; }
header { visibility: hidden; }
</style>
""", unsafe_allow_html=True)

# ── Hero header ──────────────────────────────────────────────
st.markdown("""
<div class="hero">
    <div class="hero-title">⚡ Power One One-Stop</div>
    <div class="hero-sub">ระบบบันทึกยอดขาย · Food Market Dashboard</div>
    <span class="hero-badge">AI Powered</span>
</div>
""", unsafe_allow_html=True)

try:
    with open('item_master.json', 'r', encoding='utf-8') as f:
        master_data = json.load(f)
except Exception:
    st.error("ไม่พบไฟล์ item_master.json")
    master_data = {}

# ── Section 1: Settings ──────────────────────────────────────
st.markdown("""
<div class="card">
    <div class="card-header">
        <span class="step-num">1</span>
        <span class="card-title">ตั้งค่าการทำงาน</span>
    </div>
</div>
""", unsafe_allow_html=True)

with st.container():
    col1, col2 = st.columns(2)
    with col1:
        selected_date = st.date_input("วันที่ยอดขาย", datetime.date.today())
        formatted_date_for_sheet = selected_date.strftime("%Y-%m-%d")
    with col2:
        ai_choice = st.radio("ขุมพลัง AI", ["Flash (เน้นแม่นยำ)", "Flash Lite (เน้นความเร็ว)"])

    st.markdown(f"""
    <div class="info-banner">
        📅 ล็อคข้อมูลทั้งหมดเป็นวันที่ <strong>{selected_date.strftime('%d/%m/%Y')}</strong>
        &nbsp;·&nbsp; วันอื่นใน CSV จะถูกตัดออก
    </div>
    """, unsafe_allow_html=True)

st.markdown("<div style='height:20px'></div>", unsafe_allow_html=True)

# ── Section 2: Upload ────────────────────────────────────────
st.markdown("""
<div class="card">
    <div class="card-header">
        <span class="step-num">2</span>
        <span class="card-title">นำเข้าสลิปและไฟล์ CSV</span>
    </div>
</div>
""", unsafe_allow_html=True)

files = st.file_uploader("ถ่ายรูปสลิปสาขา", type=['jpg', 'jpeg', 'png'], accept_multiple_files=True)
csv_file = st.file_uploader("อัปโหลดไฟล์ CSV (เอสพลานาด)", type=['csv'])

st.markdown("<div style='height:10px'></div>", unsafe_allow_html=True)

if st.button("🔍  สแกนและตรวจสอบข้อมูล", type="primary", use_container_width=True):
    temp_data = []

    if files:
        with st.spinner(f"กำลังสแกนด้วย {ai_choice} ..."):
            try:
                imgs = [Image.open(f) for f in files]
                ai_results = analyze_receipts(imgs, ai_choice)

                for d in ai_results:
                    branch = BRANCH_CONFIG.get(d.get('vid'), "ไม่ทราบสาขา")
                    extracted_code = str(d.get('code', '')).strip()
                    ai_unit_price = float(d.get('unit_price', 0))
                    ai_qty = int(d.get('qty', 0))
                    ai_total = float(d.get('total_amount', 0))

                    if ai_total > 0:
                        branch_items = master_data.get(branch, {})
                        match = next((item for item in branch_items.values() if item.get('code') == extracted_code), None)

                        if match:
                            db_price = float(match['price'])
                            if (ai_unit_price == db_price) and (ai_qty * ai_unit_price == ai_total):
                                final_qty = ai_qty
                                final_total = ai_total
                                status = "✅ ผ่าน"
                            else:
                                final_qty = round(ai_total / db_price) if db_price > 0 else 0
                                final_total = ai_total
                                status = "⚠️ ปรับยอดจาก Total"

                            if final_qty > 0:
                                temp_data.append({
                                    "วันที่": formatted_date_for_sheet,
                                    "สาขา (จาก CSV)": branch,
                                    "รหัสสินค้า": match['code'],
                                    "ชื่อเมนู": match['name'],
                                    "ราคา": db_price,
                                    "จำนวน": int(final_qty),
                                    "ยอด (฿)": final_total,
                                    "ตรวจสอบ": status
                                })
                        else:
                            temp_data.append({
                                "วันที่": formatted_date_for_sheet,
                                "สาขา (จาก CSV)": branch,
                                "รหัสสินค้า": extracted_code,
                                "ชื่อเมนู": "⚠️ รหัสไม่ตรง Database",
                                "ราคา": ai_unit_price,
                                "จำนวน": ai_qty,
                                "ยอด (฿)": ai_total,
                                "ตรวจสอบ": "❌ ขัดข้อง"
                            })
            except Exception as e:
                st.error(f"เกิดข้อผิดพลาดในการสแกนภาพ: {e}")

    if csv_file:
        try:
            try:
                df_csv = pd.read_csv(csv_file, encoding='utf-8')
            except:
                csv_file.seek(0)
                try:
                    df_csv = pd.read_csv(csv_file, encoding='utf-8-sig')
                except:
                    csv_file.seek(0)
                    df_csv = pd.read_csv(csv_file, encoding='tis-620')

            date_col = CSV_CONFIG["date_col"]
            if date_col in df_csv.columns:
                def parse_date(x):
                    try:
                        if str(x).replace('.', '', 1).isdigit():
                            return pd.to_datetime('1899-12-30') + pd.to_timedelta(float(x), 'D')
                        return pd.to_datetime(x, dayfirst=True)
                    except:
                        return pd.NaT

                df_csv['parsed_date'] = df_csv[date_col].apply(parse_date).dt.date
                df_csv = df_csv[df_csv['parsed_date'] == selected_date]
            else:
                st.warning(f"ไม่พบคอลัมน์ '{date_col}'")

            for _, row in df_csv.iterrows():
                qty = float(row.get(CSV_CONFIG["qty_col"], 0))
                if pd.notna(qty) and qty > 0:
                    raw_item_name = str(row.get(CSV_CONFIG["item_col"], 'ไม่ระบุชื่อ'))
                    item_name = raw_item_name.split('(')[0].strip()
                    item_code = str(row.get('รหัสเมนู', 'ไม่ระบุ'))
                    unit_price = float(row.get('ราคาต่อหน่วย', 0))
                    amount = float(row.get(CSV_CONFIG["amount_col"], row.get('ยอดขาย', 0)))

                    raw_branch = str(row.get('สาขา', 'เอสพลานาด'))
                    if "สยาม" in raw_branch or "ข้าวมันไก่สยาม" in raw_branch:
                        mapped_branch = "เอสพลานาด"
                    else:
                        mapped_branch = raw_branch.strip()

                    temp_data.append({
                        "วันที่": formatted_date_for_sheet,
                        "สาขา (จาก CSV)": mapped_branch,
                        "รหัสสินค้า": item_code,
                        "ชื่อเมนู": item_name,
                        "ราคา": unit_price,
                        "จำนวน": int(qty),
                        "ยอด (฿)": amount,
                        "ตรวจสอบ": "✅ ผ่าน (CSV)"
                    })
        except Exception as e:
            st.error(f"เกิดข้อผิดพลาดในการอ่าน CSV: {e}")

    if temp_data:
        st.session_state['preview_data'] = temp_data
        st.success(f"สแกนสำเร็จ — พบ {len(temp_data)} รายการ ของวันที่ {selected_date.strftime('%d/%m/%Y')}")
    elif csv_file or files:
        st.warning(f"ไม่พบข้อมูลของวันที่ {selected_date.strftime('%d/%m/%Y')}")

# ── Section 3: Review & Save ─────────────────────────────────
if 'preview_data' in st.session_state and st.session_state['preview_data']:

    st.markdown("""
    <div class="card">
        <div class="card-header">
            <span class="step-num">3</span>
            <span class="card-title">ตรวจสอบและยืนยันข้อมูล</span>
        </div>
    </div>
    """, unsafe_allow_html=True)

    df_preview = pd.DataFrame(st.session_state['preview_data'])
    df_edited = st.data_editor(df_preview, use_container_width=True)

    # ── Summary ──────────────────────────────────────────────
    df_summary = (
        df_edited
        .groupby("สาขา (จาก CSV)", as_index=False)
        .agg(จำนวนรายการ=("ชื่อเมนู", "count"), ยอดรวม_บาท=("ยอด (฿)", "sum"))
        .rename(columns={"สาขา (จาก CSV)": "สาขา", "ยอดรวม_บาท": "ยอดรวม (฿)"})
        .sort_values("สาขา")
    )
    df_summary["ยอดรวม (฿)"] = df_summary["ยอดรวม (฿)"].map("{:,.2f}".format)
    total_all = df_edited["ยอด (฿)"].sum()

    st.markdown('<div class="summary-card"><div class="summary-card-title">📊 สรุปยอดขายตามสาขา</div>', unsafe_allow_html=True)
    st.dataframe(df_summary, use_container_width=True, hide_index=True)
    st.markdown('</div>', unsafe_allow_html=True)

    st.metric("ยอดรวมทั้งหมด", f"฿{total_all:,.2f}")
    st.markdown("<div style='height:16px'></div>", unsafe_allow_html=True)

    st.markdown('<div class="save-wrap">', unsafe_allow_html=True)
    if st.button("✅  ยืนยันและบันทึกลง Google Sheets", type="primary", use_container_width=True):
        try:
            sheet = get_google_sheet()
            raw_rows = df_edited.drop(columns=['ตรวจสอบ']).values.tolist()
            data_to_save = []
            for row in raw_rows:
                cleaned = [clean_for_sheets(v) for v in row]
                cleaned.extend(["", ""])
                data_to_save.append(cleaned)

            sheet.append_rows(data_to_save, value_input_option="USER_ENTERED")
            st.success("บันทึกข้อมูลสำเร็จ — ยอดขายวิ่งเข้าชีตเรียบร้อย 🎉")
            st.balloons()
            st.session_state['preview_data'] = []
        except Exception as e:
            st.error(f"ไม่สามารถบันทึกลงชีตได้: {e}")
    st.markdown('</div>', unsafe_allow_html=True)
