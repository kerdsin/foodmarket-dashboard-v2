import streamlit as st
import pandas as pd
import json
import math
import google.generativeai as genai
from PIL import Image
import gspread
from google.oauth2.service_account import Credentials
import datetime

# --- 🎯 1. CONFIG: ล็อคสาขา และ คอลัมน์ CSV ---
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

# --- 🛠️ 2. ระบบเชื่อมต่อ Google Sheets ---
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
    
    # --- 🧠 3. สมองกล AI ---
def analyze_receipts(images, model_version):
    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
    
    api_model_name = 'gemini-2.5-flash' if model_version == "Flash (เน้นแม่นยำ)" else 'gemini-2.5-flash-lite'
    model = genai.GenerativeModel(api_model_name)
    
    # ⚠️ เปลี่ยนให้ AI ดึงแค่ ราคา (Unit_Price) และ ยอดรวม (Total_Amount)
    prompt = f"""
    Find VID number in the receipt header. Valid VIDs: {list(BRANCH_CONFIG.keys())}
    Extract for each item line: Line_Number, Item_Code, Unit_Price, and Total_Amount.
    
    The receipt lines ALWAYS follow this exact structure in 2 rows:
    Row 1: [Line Number]. [Item Name]
    Row 2: [Item Code]   [Unit Price]   [Quantity]   [Total Amount]
    
    Example:
    1. ข้าวมันไก่ต้ม
    FMFC033-001  60  77 4,620.00
    -> Your extraction: line_no: "1", code: "FMFC033-001", unit_price: 60.0, total_amount: 4620.0
    
    Return ONLY JSON list: [{{"vid": "str", "line_no": "str", "code": "str", "unit_price": float, "total_amount": float}}]
    """
    response = model.generate_content([prompt] + images)
    return json.loads(response.text.replace("```json", "").replace("```", "").strip())

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

# --- 📱 4. หน้าจอผู้ใช้งาน (Mobile Web App) ---
st.set_page_config(page_title="Power One One-Stop", page_icon="⚡", layout="wide")
st.title("📲 ระบบบันทึกยอดขาย One-Stop")

try:
    with open('item_master.json', 'r', encoding='utf-8') as f:
        master_data = json.load(f)
except Exception:
    st.error("❌ ไม่พบไฟล์ item_master.json")
    master_data = {}

st.subheader("📅 1. ตั้งค่าการทำงาน")
col1, col2 = st.columns(2)
with col1:
    selected_date = st.date_input("ระบุวันที่ของยอดขาย:", datetime.date.today())
    formatted_date_for_sheet = selected_date.strftime("%Y-%m-%d")
with col2:
    ai_choice = st.radio("🤖 เลือกขุมพลัง AI:", ["Flash (เน้นแม่นยำ)", "Flash Lite (เน้นความเร็ว)"])

st.info(f"💡 ระบบจะล็อคข้อมูลทั้งหมดเป็นวันที่ **{selected_date.strftime('%d/%m/%Y')}** และตัดวันอื่นใน CSV ทิ้ง")
st.divider()

st.subheader("📷 2. นำเข้าสลิปและไฟล์")
files = st.file_uploader("ถ่ายรูปสลิปสาขา", type=['jpg', 'jpeg', 'png'], accept_multiple_files=True)
csv_file = st.file_uploader("หรืออัปโหลดไฟล์ CSV (เอสพลานาด)", type=['csv'])

if st.button("🚀 สแกนและตรวจสอบข้อมูล", type="primary", use_container_width=True):
    temp_data = []
  
     # 📝 ประมวลผลรูปภาพ
    if files:
        with st.spinner(f"กำลังสแกนด้วยโหมด {ai_choice}..."):
            try:
                imgs = [Image.open(f) for f in files]
                ai_results = analyze_receipts(imgs, ai_choice)
                
                for d in ai_results:
                    branch = BRANCH_CONFIG.get(d.get('vid'), "ไม่ทราบสาขา")
                    line = str(d.get('line_no'))
                    branch_items = master_data.get(branch, {})
                    match = branch_items.get(line)
                    if not match and d.get('code'):
                        match = next((item for item in branch_items.values() if item.get('code') == d['code']), None)
                    
                    # 💡 ดึงราคา และ ยอดรวมมา เพื่อคำนวณหาจำนวน (Qty) เอง
                    unit_price = float(d.get('unit_price', 0))
                    total_amount = float(d.get('total_amount', 0))
                    
                    calculated_qty = 0
                    if unit_price > 0:
                        calculated_qty = round(total_amount / unit_price)
                    
                    if calculated_qty > 0:
                        is_valid = match and match['code'] == d['code'] and match['price'] == unit_price
                        temp_data.append({
                            "วันที่": formatted_date_for_sheet,
                            "สาขา (จาก CSV)": branch,
                            "รหัสสินค้า": d.get('code', ''),
                            "ชื่อเมนู": match['name'] if match else "⚠️ รหัสไม่ตรง",
                            "ราคา": unit_price,
                            "จำนวน": int(calculated_qty),
                            "ยอด (฿)": total_amount,
                            "ตรวจสอบ": "✅ ผ่าน" if is_valid else "❌ ขัดข้อง"
                        })
            except Exception as e:
                st.error(f"เกิดข้อผิดพลาดในการสแกนภาพ: {e}")
                    
    # 📝 ประมวลผล CSV
    if csv_file:
        try:
            # อ่านไฟล์รอบเดียว
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
                # ฟังก์ชันแปลงวันที่แบบครอบจักรวาล
                def parse_date(x):
                    try:
                        if str(x).replace('.','',1).isdigit(): # แก้เคสเลข Excel 46027
                            return pd.to_datetime('1899-12-30') + pd.to_timedelta(float(x), 'D')
                        return pd.to_datetime(x, dayfirst=True)
                    except:
                        return pd.NaT

                df_csv['parsed_date'] = df_csv[date_col].apply(parse_date).dt.date
                # กรองเอาเฉพาะวันที่เลือก
                df_csv = df_csv[df_csv['parsed_date'] == selected_date]
            else:
                st.warning(f"⚠️ ไม่พบคอลัมน์ '{date_col}'")

            for _, row in df_csv.iterrows():
                qty = float(row.get(CSV_CONFIG["qty_col"], 0))
                
                # เอาเฉพาะรายการที่ขายได้จริงๆ (>0)
                if pd.notna(qty) and qty > 0:
                    
                    # 💡 ตัดวงเล็บและช่องว่างทิ้ง
                    raw_item_name = str(row.get(CSV_CONFIG["item_col"], 'ไม่ระบุชื่อ'))
                    item_name = raw_item_name.split('(')[0].strip()
                    
                    item_code = str(row.get('รหัสเมนู', 'ไม่ระบุ'))
                    unit_price = float(row.get('ราคาต่อหน่วย', 0))
                    amount = float(row.get(CSV_CONFIG["amount_col"], row.get('ยอดขาย', 0)))

                    # ⚠️ ตรวจจับคำว่า "สยาม" และแปลงเป็น "เอสพลานาด"
                    raw_branch = str(row.get('สาขา', 'เอสพลานาด'))
                    if "สยาม" in raw_branch or "ข้าวมันไก่สยาม" in raw_branch:
                        mapped_branch = "เอสพลานาด"
                    else:
                        mapped_branch = raw_branch.strip()
                    
                    temp_data.append({
                        "วันที่": formatted_date_for_sheet,
                        "สาขา (จาก CSV)": mapped_branch, # ⚠️ แก้จุดนี้ให้ใช้ตัวแปร mapped_branch
                        "รหัสสินค้า": item_code,
                        "ชื่อเมนู": item_name,
                        "ราคา": unit_price,
                        "จำนวน": int(qty),
                        "ยอด (฿)": amount,
                        "ตรวจสอบ": "✅ ผ่าน (CSV)"
                    })
        except Exception as e:
             st.error(f"❌ เกิดข้อผิดพลาดในการอ่าน CSV: {e}")

    # แสดงผล
    if temp_data:
        st.session_state['preview_data'] = temp_data
        st.success(f"สแกนสำเร็จ! พบข้อมูลที่ตรงกับวันที่ {selected_date.strftime('%d/%m/%Y')} จำนวน {len(temp_data)} รายการ")
    elif csv_file or files:
        st.warning(f"⚠️ ไม่พบข้อมูลของวันที่ {selected_date.strftime('%d/%m/%Y')}")

# --- 📋 5. ยืนยันข้อมูลก่อนลง Sheet ---
if 'preview_data' in st.session_state and st.session_state['preview_data']:
    df_preview = pd.DataFrame(st.session_state['preview_data'])
    df_edited = st.data_editor(df_preview, use_container_width=True)

    if st.button("✅ ยืนยันและบันทึกลง Google Sheets", type="primary", use_container_width=True):
        try:
            sheet = get_google_sheet()
            raw_rows = df_edited.drop(columns=['ตรวจสอบ']).values.tolist()

            data_to_save = []
            for row in raw_rows:
                cleaned = [clean_for_sheets(v) for v in row]
                cleaned.extend(["", ""])
                data_to_save.append(cleaned)

            sheet.append_rows(data_to_save, value_input_option="USER_ENTERED")

            st.success("🎉 บันทึกข้อมูลสำเร็จ! ยอดขายวิ่งเข้าชีตเรียบร้อย")
            st.balloons()
            st.session_state['preview_data'] = []
        except Exception as e:
            st.error(f"❌ ไม่สามารถบันทึกลงชีตได้: {e}")
