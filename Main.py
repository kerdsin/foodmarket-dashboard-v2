import streamlit as st
import pandas as pd
import json
import google.generativeai as genai
from PIL import Image
import gspread
from google.oauth2.service_account import Credentials
import datetime # เพิ่ม Library จัดการวันที่

# --- 🎯 1. CONFIG: ล็อคสาขา และ คอลัมน์ CSV ---
BRANCH_CONFIG = {
    "208413": "อโศก",
    "205711": "พระราม 3",
    "206025": "แฟชั่น 3",
    "207033": "แฟชั่น B",
    "990221": "เอสพลานาด"
}

# ⚠️ แมปปิ้งคอลัมน์ให้ตรงกับไฟล์ CSV ของระบบ POS (ภาษาไทย)
CSV_CONFIG = {
    "date_col": "วันที่เปิดบิล",     # ดึงวันที่จากคอลัมน์ 'วันที่เปิดบิล'
    "item_col": "ชื่อเมนู",          # ดึงชื่อเมนูจากคอลัมน์ 'ชื่อเมนู'
    "qty_col": "จำนวน",             # ดึงยอดขายจากคอลัมน์ 'จำนวน'
    "amount_col": "ยอดขายสุทธิ"      # ดึงยอดเงินรวมจากคอลัมน์ 'ยอดขายสุทธิ' (หรือจะใช้ 'รวม' ก็ได้ครับ)
}

# --- 🛠️ 2. ระบบเชื่อมต่อ Google Sheets ---
@st.cache_resource
def get_google_sheet():
    creds_info = json.loads(st.secrets["GCP_SERVICE_ACCOUNT"])
    creds = Credentials.from_service_account_info(creds_info, scopes=["https://www.googleapis.com/auth/spreadsheets"])
    return gspread.authorize(creds).open_by_key(st.secrets["SHEET_ID"]).sheet1

# --- 🧠 3. สมองกล AI ---
def analyze_receipts(images, model_version):
    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
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

# โหลด Master Data
try:
    with open('item_master.json', 'r', encoding='utf-8') as f:
        master_data = json.load(f)
except Exception:
    st.error("❌ ไม่พบไฟล์ item_master.json")
    master_data = {}

# ---------------------------------------------------------
# 🆕 ส่วนที่ 1: ตั้งค่าวันที่และ AI (เพิ่มใหม่ตามรีเควส)
# ---------------------------------------------------------
st.subheader("📅 1. ตั้งค่าการทำงาน")
col1, col2 = st.columns(2)
with col1:
    # ให้ผู้ใช้เลือกวันที่ก่อนรัน
    selected_date = st.date_input("ระบุวันที่ของยอดขาย:", datetime.date.today())
    formatted_date = selected_date.strftime("%d/%m/%Y")
with col2:
    ai_choice = st.radio("🤖 เลือกขุมพลัง AI:", ["Flash (เน้นแม่นยำ)", "Flash Lite (เน้นความเร็ว)"])

st.info(f"💡 ระบบจะล็อคข้อมูลทั้งหมดเป็นวันที่ **{formatted_date}** และตัดวันอื่นใน CSV ทิ้ง")
st.divider()

# ---------------------------------------------------------
# ส่วนที่ 2: นำเข้าข้อมูล
# ---------------------------------------------------------
st.subheader("📷 2. นำเข้าสลิปและไฟล์")
files = st.file_uploader("ถ่ายรูปสลิปสาขา", type=['jpg', 'jpeg', 'png'], accept_multiple_files=True)
csv_file = st.file_uploader("หรืออัปโหลดไฟล์ CSV (เอสพลานาด)", type=['csv'])

if st.button("🚀 สแกนและตรวจสอบข้อมูล", type="primary", use_container_width=True):
    temp_data = []
    
    # 📝 ประมวลผลรูปภาพ (ล็อควันที่ตามที่เลือก)
    if files:
        with st.spinner(f"กำลังสแกนด้วยโหมด {ai_choice}..."):
            try:
                imgs = [Image.open(f) for f in files]
                ai_results = analyze_receipts(imgs, ai_choice)
                
                for d in ai_results:
                    branch = BRANCH_CONFIG.get(d.get('vid'), "ไม่ทราบสาขา")
                    line = str(d.get('line_no'))
                    match = master_data.get(branch, {}).get(line)
                    
                    if d.get('qty', 0) > 0:
                        is_valid = match and match['code'] == d['code'] and match['price'] == d['unit_price']
                        temp_data.append({
                            "วันที่": formatted_date, # บังคับใช้วันที่ที่เลือก
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

        # ดำเนินการส่วน CSV (เช่น เอสพลานาด หรือ ดึงจาก POS โดยตรง)
    if csv_file:
        try:
            # รองรับไฟล์ภาษาไทย
            df_csv = pd.read_csv(csv_file) 
            
            for _, row in df_csv.iterrows():
                # กรองเฉพาะรายการที่มีการขายจริง
                if pd.notna(row.get('จำนวน')) and float(row.get('จำนวน', 0)) > 0:
                    temp_data.append({
                        "วันที่": row.get('วันที่เช็คบิล', pd.Timestamp.now().strftime("%d/%m/%Y")),
                        "สาขา": row.get('สาขา', 'CSV-Import'),
                        "รหัสสินค้า": str(row.get('รหัสเมนู', '')),
                        "ชื่อเมนู": str(row.get('ชื่อเมนู', 'ไม่ระบุชื่อ')),
                        "ราคา": float(row.get('ราคาต่อหน่วย', 0)),
                        "จำนวน": float(row.get('จำนวน', 0)),
                        "ยอด (฿)": float(row.get('ยอดขาย', 0)),
                        "ตรวจสอบ": "✅ CSV Auto"
                    })
        except Exception as e:
            st.error(f"❌ เกิดข้อผิดพลาดในการอ่านไฟล์ CSV: {e}")
# 📝 ประมวลผล CSV (ทำการ Filter ตัดวันที่ไม่เกี่ยวข้องทิ้ง)
    if csv_file:
        try:
            df_csv = pd.read_csv(csv_file)
            
            # ค้นหาคอลัมน์วันที่ใน CSV
            date_col = next((col for col in df_csv.columns if 'date' in col.lower() or 'วันที่' in col), None)
            
            # กรองข้อมูลเอาเฉพาะวันที่เลือก
            if date_col:
                parsed_dates = pd.to_datetime(df_csv[date_col], errors='coerce', dayfirst=True)
                df_csv = df_csv[parsed_dates.dt.date == selected_date]
            
            for _, row in df_csv.iterrows():
                # ปรับหัวคอลัมน์ 'Item Name', 'Qty', 'Amount' ให้ตรงกับไฟล์ CSV ของคุณสมาร์ท
                temp_data.append({
                    "วันที่": formatted_date,
                    "สาขา": "เอสพลานาด",
                    "รหัสสินค้า": "CSV-Import",
                    "ชื่อเมนู": row.get('Item Name', 'N/A'),
                    "ราคา": 0,
                    "จำนวน": row.get('Qty', 0),
                    "ยอด (฿)": row.get('Amount', 0),
                    "ตรวจสอบ": "✅ CSV"
                })
        except Exception as e:
             st.error(f"เกิดข้อผิดพลาดในการอ่าน CSV: {e}")

    # แสดงผล
    if temp_data:
        st.session_state['preview_data'] = temp_data
        st.success(f"สแกนสำเร็จ! พบข้อมูลที่ตรงกับวันที่ {formatted_date} จำนวน {len(temp_data)} รายการ")
    elif csv_file or files:
        st.warning(f"⚠️ ไม่พบข้อมูลของวันที่ {formatted_date} กรุณาตรวจสอบไฟล์หรือสลิปอีกครั้ง")

# --- 📋 5. ยืนยันข้อมูลก่อนลง Sheet ---
if 'preview_data' in st.session_state and st.session_state['preview_data']:
    df_preview = pd.DataFrame(st.session_state['preview_data'])
    st.data_editor(df_preview, use_container_width=True)
    
    if st.button("✅ ยืนยันและบันทึกลง Google Sheets", type="primary", use_container_width=True):
        try:
            sheet = get_google_sheet()
            data_to_save = df_preview.drop(columns=['ตรวจสอบ']).values.tolist()
            sheet.append_rows(data_to_save)
            
            st.success("🎉 บันทึกข้อมูลสำเร็จ! ยอดขายวิ่งเข้าชีตเรียบร้อย")
            st.balloons()
            st.session_state['preview_data'] = []
        except Exception as e:
            st.error(f"❌ ไม่สามารถบันทึกลงชีตได้: {e}")
