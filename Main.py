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
# PAGE CONFIG & STYLES
# ============================================================
st.set_page_config(page_title="Power One One-Stop", page_icon="⚡", layout="wide")

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Sarabun:wght@300;400;500;600;700;800&display=swap');

html, body, [class*="css"] {
    font-family: 'Sarabun', sans-serif !important;
}

/* ── App background ── */
.stApp {
    background-color: #F1F5F9;
}
.block-container {
    padding: 1.5rem 1.5rem 3rem !important;
    max-width: 900px;
}

/* ── Hero header ── */
.hero {
    background: linear-gradient(135deg, #1E3A5F 0%, #2563EB 100%);
    border-radius: 16px;
    padding: 24px 28px 20px;
    margin-bottom: 24px;
    box-shadow: 0 4px 24px rgba(37,99,235,0.25);
}
.hero-title {
    font-size: 22px;
    font-weight: 800;
    color: #FFFFFF;
    margin: 0 0 4px 0;
}
.hero-sub {
    font-size: 13px;
    color: rgba(255,255,255,0.75);
    margin: 0 0 10px 0;
}
.hero-badge {
    display: inline-block;
    background: #FCD34D;
    color: #1E3A5F;
    font-size: 10px;
    font-weight: 800;
    padding: 2px 10px;
    border-radius: 20px;
    letter-spacing: 1.5px;
    text-transform: uppercase;
}

/* ── Section cards ── */
.card {
    background: #FFFFFF;
    border: 1px solid #E2E8F0;
    border-radius: 14px;
    padding: 18px 22px 14px;
    margin-bottom: 16px;
    box-shadow: 0 1px 6px rgba(0,0,0,0.06);
}
.card-header {
    display: flex;
    align-items: center;
    gap: 10px;
    margin-bottom: 6px;
}
.step-num {
    background: linear-gradient(135deg, #2563EB, #1D4ED8);
    color: #fff;
    font-size: 12px;
    font-weight: 700;
    width: 28px;
    height: 28px;
    border-radius: 50%;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    flex-shrink: 0;
}
.card-title {
    color: #1E293B;
    font-size: 15px;
    font-weight: 700;
    margin: 0;
}

/* ── Date info banner ── */
.info-banner {
    background: #EFF6FF;
    border: 1px solid #BFDBFE;
    border-left: 4px solid #3B82F6;
    border-radius: 8px;
    padding: 10px 14px;
    color: #1E40AF;
    font-size: 14px;
    margin-top: 12px;
}

/* ── Primary button (scan) ── */
.stButton > button[kind="primary"] {
    background: linear-gradient(135deg, #2563EB, #1D4ED8) !important;
    color: #fff !important;
    border: none !important;
    border-radius: 10px !important;
    font-size: 15px !important;
    font-weight: 600 !important;
    padding: 0.65rem 1.2rem !important;
    box-shadow: 0 4px 14px rgba(37,99,235,0.35) !important;
    font-family: 'Sarabun', sans-serif !important;
}
.stButton > button[kind="primary"]:hover {
    background: linear-gradient(135deg, #1D4ED8, #1E40AF) !important;
    box-shadow: 0 6px 20px rgba(37,99,235,0.45) !important;
    transform: translateY(-1px) !important;
}

/* ── Save button (green) ── */
.save-wrap .stButton > button[kind="primary"] {
    background: linear-gradient(135deg, #059669, #047857) !important;
    box-shadow: 0 4px 14px rgba(5,150,105,0.35) !important;
}
.save-wrap .stButton > button[kind="primary"]:hover {
    background: linear-gradient(135deg, #047857, #065F46) !important;
    box-shadow: 0 6px 20px rgba(5,150,105,0.45) !important;
}

/* ── Summary card ── */
.summary-box {
    background: #F0FDF4;
    border: 1px solid #BBF7D0;
    border-radius: 12px;
    padding: 16px 20px 12px;
    margin: 16px 0 12px;
}
.summary-box-title {
    color: #166534;
    font-size: 14px;
    font-weight: 700;
    margin-bottom: 12px;
}

/* ── Metric box ── */
[data-testid="metric-container"] {
    background: linear-gradient(135deg, #EFF6FF, #DBEAFE) !important;
    border: 1px solid #BFDBFE !important;
    border-radius: 12px !important;
    padding: 14px 20px !important;
}
[data-testid="stMetricValue"] {
    color: #1E40AF !important;
    font-size: 28px !important;
    font-weight: 800 !important;
}
[data-testid="stMetricLabel"] {
    color: #3B82F6 !important;
    font-size: 13px !important;
    font-weight: 600 !important;
}

/* ── Divider ── */
hr { border-color: #E2E8F0 !important; margin: 16px 0 !important; }

/* ── Alerts ── */
[data-testid="stAlert"] { border-radius: 10px !important; font-size: 14px !important; }

/* ── Dataframe ── */
[data-testid="stDataFrame"] { border-radius: 10px; overflow: hidden; }

/* ── Hide Streamlit branding ── */
#MainMenu { visibility: hidden; }
footer { visibility: hidden; }
header { visibility: hidden; }
</style>
""", unsafe_allow_html=True)

# ── Hero ─────────────────────────────────────────────────────
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

# ── Step 1: Settings ─────────────────────────────────────────
st.markdown("""
<div class="card">
    <div class="card-header">
        <span class="step-num">1</span>
        <span class="card-title">ตั้งค่าการทำงาน</span>
    </div>
</div>
""", unsafe_allow_html=True)

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

st.markdown("<div style='height:18px'></div>", unsafe_allow_html=True)

# ── Step 2: Upload ───────────────────────────────────────────
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

# ── Step 3: Review & Save ────────────────────────────────────
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

    # Summary
    df_summary = (
        df_edited
        .groupby("สาขา (จาก CSV)", as_index=False)
        .agg(จำนวนรายการ=("ชื่อเมนู", "count"), ยอดรวม_บาท=("ยอด (฿)", "sum"))
        .rename(columns={"สาขา (จาก CSV)": "สาขา", "ยอดรวม_บาท": "ยอดรวม (฿)"})
        .sort_values("สาขา")
    )
    df_summary["ยอดรวม (฿)"] = df_summary["ยอดรวม (฿)"].map("{:,.2f}".format)
    total_all = df_edited["ยอด (฿)"].sum()

    st.markdown('<div class="summary-box"><div class="summary-box-title">📊 สรุปยอดขายตามสาขา</div>', unsafe_allow_html=True)
    st.dataframe(df_summary, use_container_width=True, hide_index=True)
    st.markdown('</div>', unsafe_allow_html=True)

    st.metric("ยอดรวมทั้งหมด", f"฿{total_all:,.2f}")
    st.markdown("<div style='height:14px'></div>", unsafe_allow_html=True)

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

# ── Section 4: Delete wrong upload ──────────────────────────
st.markdown("<div style='height:24px'></div>", unsafe_allow_html=True)

with st.expander("🗑️  แก้ไขข้อมูลที่อัปโหลดผิด — ลบตามวันที่"):
    st.markdown("""
    <div style='color:#6B7280;font-size:13px;margin-bottom:16px;'>
    เลือกวันที่ที่ต้องการลบออกจาก Google Sheets — ระบบแสดง preview ก่อนลบจริง
    </div>
    """, unsafe_allow_html=True)

    del_date = st.date_input("วันที่ที่ต้องการลบ", datetime.date.today(), key="del_date")
    del_date_str = del_date.strftime("%Y-%m-%d")

    if st.button("🔎  ดูข้อมูลที่จะถูกลบ", key="preview_delete"):
        try:
            sheet = get_google_sheet()
            all_rows = sheet.get_all_values()

            if len(all_rows) < 2:
                st.info("ไม่มีข้อมูลในชีท")
            else:
                header = all_rows[0]
                data_rows = all_rows[1:]
                matched, matched_indices = [], []
                for i, row in enumerate(data_rows):
                    if row and row[0] == del_date_str:
                        padded = row + [''] * max(0, len(header) - len(row))
                        matched.append(padded[:len(header)])
                        matched_indices.append(i + 2)  # 1-based, header=row1

                if matched:
                    st.session_state['delete_rows_indices'] = matched_indices
                    st.session_state['delete_date_str'] = del_date_str
                    df_del = pd.DataFrame(matched, columns=header)
                    st.warning(f"พบ **{len(matched)} แถว** ของวันที่ {del_date.strftime('%d/%m/%Y')} — ตรวจสอบก่อนกดลบ")
                    st.dataframe(df_del, use_container_width=True, hide_index=True)
                else:
                    st.info(f"ไม่พบข้อมูลของวันที่ {del_date.strftime('%d/%m/%Y')} ในชีท")
                    st.session_state.pop('delete_rows_indices', None)
        except Exception as e:
            st.error(f"ดึงข้อมูลไม่ได้: {e}")

    # ปุ่มยืนยัน — แสดงเมื่อมี preview
    indices = st.session_state.get('delete_rows_indices', [])
    if indices and st.session_state.get('delete_date_str') == del_date_str:
        n = len(indices)
        st.markdown(f"<p style='color:#DC2626;font-weight:600;font-size:14px;margin-top:12px;'>⚠️ การลบ {n} แถวนี้ไม่สามารถย้อนกลับได้</p>", unsafe_allow_html=True)
        col_ok, col_no = st.columns(2)
        with col_ok:
            if st.button(f"🗑️  ยืนยันลบ {n} แถว", type="primary", use_container_width=True, key="confirm_delete"):
                try:
                    sheet = get_google_sheet()
                    for row_idx in sorted(indices, reverse=True):
                        sheet.delete_rows(row_idx)
                    st.success(f"ลบ {n} แถวของวันที่ {del_date.strftime('%d/%m/%Y')} สำเร็จ")
                    st.session_state.pop('delete_rows_indices', None)
                    st.session_state.pop('delete_date_str', None)
                except Exception as e:
                    st.error(f"ลบไม่สำเร็จ: {e}")
        with col_no:
            if st.button("ยกเลิก", use_container_width=True, key="cancel_delete"):
                st.session_state.pop('delete_rows_indices', None)
                st.session_state.pop('delete_date_str', None)
                st.rerun()
