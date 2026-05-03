import streamlit as st
import pandas as pd
import json
import google.generativeai as genai
from PIL import Image
import gspread
from google.oauth2.service_account import Credentials

# --- 🎯 1. CONFIG: ล็อคเลขไอดีสาขา ---
BRANCH_CONFIG = {
    "208413": "อโศก",
    "205711": "พระราม 3",
    "206025": "แฟชั่น 3",
    "207033": "แฟชั่น B",
    "990221": "เอสพลานาด"
}

# --- 🛠️ 2. ระบบเชื่อมต่อ Google Sheets ---
@st.cache_resource
def get_google_sheet():
    creds_info = json.loads(st.secrets["GCP_SERVICE_ACCOUNT"])
    creds = Credentials.from_service_account_info(creds_info, scopes=["https://www.googleapis.com/auth/spreadsheets"])
    return gspread.authorize(creds).open_by_key(st.secrets["SHEET_ID"]).sheet1

# --- 🧠 3. สมองกล AI (รองรับการสลับรุ่น Flash / Flash Lite) ---
def analyze_receipts(images, model_version):
    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
    
    # สลับรุ่น API ตามที่คุณสมาร์ทเลือกบนหน้าจอ
    api_model_name = 'gemini-2.5-flash' if model_version == "Flash (เน้นแม่นยำ)" else 'gemini-2.5-flash-lite'
    model = genai.GenerativeModel(api_model_name)
    
    prompt = f"""
    Find VID number in the receipt header. Valid VIDs: {list(BRANCH_CONFIG.keys())}
    Extract for each item line: Line_Number (number before item name), Item_Code, Qty, and Unit_Price.
    Return ONLY JSON list: [{{"vid": "str", "line_no": "str", "code": "str", "qty": int, "unit_price": float}}]
    """
    response = model.generate_content([prompt] + images)
    return json.loads(response.text.replace("```json", "").replace("```", "").strip())

# --- 📱 4. หน้าจอผู้ใช้งาน (Mobile Web App) ---
st.set_page_config(page_title="Power One One-Stop", page_icon="⚡", layout="centered")
st.title("📲 ระบบบันทึกยอดขาย One-Stop")
st.caption("อัปเดตยอดเข้าไฟล์ FoodMarket May2569 อัตโนมัติ")

# โหลด Master Data
try:
    with open('item_master.json', 'r', encoding='utf-8') as f:
        master_data = json.load(f)
except Exception:
    st.error("❌ ไม่พบไฟล์ item_master.json")
    master_data = {}

# ตั้งค่าโมเดล AI
ai_choice = st.radio(
    "🤖 เลือกขุมพลัง AI สำหรับสแกน:",
    ["Flash (เน้นแม่นยำ)", "Flash Lite (เน้นความเร็ว)"],
    horizontal=True
)

st.divider()

# อัปโหลดสลิป
files = st.file_uploader("📷 ถ่ายรูปสลิปสาขา", type=['jpg', 'jpeg', 'png'], accept_multiple_files=True)
csv_file = st.file_uploader("📄 หรืออัปโหลดไฟล์ CSV (เอสพลานาด)", type=['csv'])

if st.button("🚀 สแกนและตรวจสอบข้อมูล", type="primary", use_container_width=True):
    temp_data = []
    
    if files:
        with st.spinner(f"กำลังสแกนด้วยโหมด {ai_choice}..."):
            try:
                imgs = [Image.open(f) for f in files]
                ai_results = analyze_receipts(imgs, ai_choice)
                
                for d in ai_results:
                    branch = BRANCH_CONFIG.get(d.get('vid'), "ไม่ทราบสาขา")
                    line = str(d.get('line_no'))
                    match = master_data.get(branch, {}).get(line)
                    
                    # กรองยอด 0 บาททิ้ง
                    if d.get('qty', 0) > 0:
                        is_valid = match and match['code'] == d['code'] and match['price'] == d['unit_price']
                        temp_data.append({
                            "วันที่": pd.Timestamp.now().strftime("%d/%m/%Y"),
                            "สาขา": branch,
                            "รหัสสินค้า": d.get('code', ''),
                            "ชื่อเมนู": match['name'] if match else "⚠️ รหัสไม่ตรง",
                            "ราคา": d.get('unit_price', 0),
                            "จำนวน": d.get('qty', 0),
                            "ยอด (฿)": d.get('qty', 0) * d.get('unit_price', 0),
                            "ตรวจสอบ": "✅ ผ่าน" if is_valid else "❌ ขัดข้อง"
                        })
            except Exception as e:
                st.error(f"เกิดข้อผิดพลาดในการสแกนภาพ: {e}")

    if csv_file:
        df_csv = pd.read_csv(csv_file)
        for _, row in df_csv.iterrows():
            temp_data.append({
                "วันที่": pd.Timestamp.now().strftime("%d/%m/%Y"),
                "สาขา": "เอสพลานาด",
                "รหัสสินค้า": "CSV-Import",
                "ชื่อเมนู": row.get('Item Name', 'N/A'),
                "ราคา": 0, # ปรับตามโครงสร้าง CSV จริง
                "จำนวน": row.get('Qty', 0),
                "ยอด (฿)": row.get('Amount', 0),
                "ตรวจสอบ": "✅ CSV"
            })

    if temp_data:
        st.session_state['preview_data'] = temp_data
        st.success("สแกนสำเร็จ! โปรดตรวจสอบข้อมูลด้านล่าง")

# --- 📋 5. ยืนยันข้อมูลก่อนลง Sheet ---
if 'preview_data' in st.session_state and st.session_state['preview_data']:
    df_preview = pd.DataFrame(st.session_state['preview_data'])
    st.data_editor(df_preview, use_container_width=True)
    
    if st.button("✅ ยืนยันและบันทึกลง Google Sheets", type="primary", use_container_width=True):
        try:
            sheet = get_google_sheet()
            # ตัดคอลัมน์ "ตรวจสอบ" ทิ้งก่อนเอาลง Sheet เพื่อให้ตรงกับโครงสร้าง Data
            data_to_save = df_preview.drop(columns=['ตรวจสอบ']).values.tolist()
            sheet.append_rows(data_to_save)
            
            st.success("🎉 บันทึกข้อมูลสำเร็จ! ยอดขายวิ่งเข้าชีตเรียบร้อย")
            st.balloons()
            st.session_state['preview_data'] = []
        except Exception as e:
            st.error(f"❌ ไม่สามารถบันทึกลงชีตได้: {e}")
