import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import requests
import base64

# --- 設定區 ---
SPREADSHEET_NAME = "inventory_system"
IMGBB_API_KEY = "請將您的 ImgBB API Key 貼在這裡" 

# --- 連線設定 ---
@st.cache_resource(ttl=600)
def get_gspread_client():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    try:
        creds_dict = dict(st.secrets["gcp_service_account"])
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        client = gspread.authorize(creds)
        return client
    except Exception as e:
        st.error(f"❌ Google 登入失敗: {e}")
        return None

def get_worksheet(sheet_name="sheet1"):
    client = get_gspread_client()
    if not client: return None
    
    try:
        # 嘗試開啟指定分頁
        if sheet_name == "sheet1":
            return client.open(SPREADSHEET_NAME).sheet1
        else:
            return client.open(SPREADSHEET_NAME).worksheet(sheet_name)
            
    except gspread.exceptions.WorksheetNotFound:
        # ⚠️ 關鍵修正：如果找不到 vendors 分頁，自動建立！
        if sheet_name == "vendors":
            try:
                sh = client.open(SPREADSHEET_NAME)
                # 建立新分頁
                new_ws = sh.add_worksheet(title="vendors", rows="100", cols="10")
                # 寫入標題列
                new_ws.append_row(["廠商名稱", "聯絡人", "電話", "地址", "備註"])
                st.toast("已自動建立 'vendors' 分頁！")
                return new_ws
            except Exception as e:
                st.error(f"建立分頁失敗: {e}")
                return None
        return None
        
    except gspread.exceptions.SpreadsheetNotFound:
        st.error(f"❌ 找不到試算表 '{SPREADSHEET_NAME}'")
        return None
    except Exception as e:
        st.cache_resource.clear()
        st.warning("⚠️ 連線忙碌中，請重整頁面...")
        return None

# --- ImgBB 上傳 ---
def upload_image_to_imgbb(uploaded_file):
    if not IMGBB_API_KEY or "請將" in IMGBB_API_KEY:
        st.error("⚠️ 請先設定 IMGBB_API_KEY")
        return ""
    try:
        image_content = uploaded_file.read()
        b64_image = base64.b64encode(image_content)
        payload = {"key": IMGBB_API_KEY, "image": b64_image}
        response = requests.post("https://api.imgbb.com/1/upload", data=payload)
        result = response.json()
        if result["status"] == 200:
            return result["data"]["url"]
        else:
            st.error(f"上傳失敗: {result.get('error', {}).get('message')}")
            return ""
    except Exception as e:
        st.error(f"錯誤: {e}")
        return ""

# --- 權限管理 ---
def check_password():
    stored_password = st.secrets.get("admin_password")
    if not stored_password:
        st.error("⚠️ 請先在 Secrets 設定 'admin_password'")
        return
    if st.session_state["password_input"] == stored_password:
        st.session_state["is_admin"] = True
    else:
        st.session_state["is_admin"] = False
        st.error("❌ 密碼錯誤")

def logout():
    st.session_state["is_admin"] = False
    st.rerun()

def show_login_block():
    st.warning("🔒 **此功能僅限管理員使用**")
    st.info("請使用左側欄位輸入密碼登入。")
    st.stop()

# --- 核心功能：商品管理 ---

def get_inventory_df():
    sheet = get_worksheet("sheet1")
    if sheet:
        data = sheet.get_all_records()
        df = pd.DataFrame(data)
        if '商品名稱' in df.columns: df['商品名稱'] = df['商品名稱'].astype(str).str.strip()
        if '圖片連結' not in df.columns: df['圖片連結'] = ""
        if '備註' not in df.columns: df['備註'] = ""
        if '分類' not in df.columns: df['分類'] = "未分類"
        if '廠商' not in df.columns: df['廠商'] = ""
        
        df['分類'] = df['分類'].astype(str).replace('', '未分類').replace('nan', '未分類')
        df['廠商'] = df['廠商'].astype(str).replace('nan', '')
        return df
    return pd.DataFrame()

def find_product_cell(sheet, name):
    target_name = str(name).strip()
    try:
        col_values = sheet.col_values(1)
        str_values = [str(v).strip() for v in col_values]
        if target_name in str_values:
            all_indices 
