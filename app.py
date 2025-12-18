import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import requests
import base64

# --- 設定區 ---
SPREADSHEET_NAME = "inventory_system"
IMGBB_API_KEY = "a9e1ead23aa6fb34478cf7a16adaf34b"  

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

def get_worksheet():
    client = get_gspread_client()
    if not client: return None
    try:
        sheet = client.open(SPREADSHEET_NAME).sheet1
        return sheet
    except gspread.exceptions.SpreadsheetNotFound:
        st.error(f"❌ 找不到試算表 '{SPREADSHEET_NAME}'")
        return None
    except gspread.exceptions.APIError:
        st.cache_resource.clear()
        st.warning("⚠️ 連線忙碌中，正在重試...")
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

# --- 核心功能 (修復重複資料問題) ---

def get_inventory_df():
    sheet = get_worksheet()
    if sheet:
        data = sheet.get_all_records()
        df = pd.DataFrame(data)
        # 強制轉型，避免數字/文字混淆
        if '商品名稱' in df.columns: df['商品名稱'] = df['商品名稱'].astype(str)
        if '圖片連結' not in df.columns: df['圖片連結'] = ""
        if '備註' not in df.columns: df['備註'] = ""
        return df
    return pd.DataFrame()

def find_product_cell(sheet, name):
    """
    超級強化的搜尋函式：
    直接讀取第一欄所有資料來比對，解決 'sheet.find' 對數字/文字判斷不穩的問題。
    """
    target_name = str(name).strip()
    
    try:
        # 取得第一欄所有值 (商品名稱)
        col_values = sheet.col_values(1) 
        
        # 找出對應的行數 (注意: col_values 的 index 從 0 開始，但 sheet row 從 1 開始)
        # 這裡我們找 "最後一次出現" 的位置，這樣可以優先更新最新的一筆 (如果已重複)
        # 但為了保險，我們先找第一個匹配的
        
        # 將所有值轉為字串比對
        str_values = [str(v).strip() for v in col_values]
        
        if target_name in str_values:
            # 找到 index，轉換成 row number (index + 1)
            row_idx = str_values.index(target_name) + 1
            return sheet.cell(row_idx, 1) # 回傳該儲存格物件
        
        return None
    except Exception as e:
        st.error(f"搜尋錯誤: {e}")
        return None

def add_product(name, quantity, price, image_urls, remarks):
    sheet = get_worksheet()
    if not sheet: return
    name_str = str(name).strip()
    
    if isinstance(image_urls, list):
        final_url_str = ",".join(image_urls)
    else:
        final_url_str = str(image_urls).strip()

    if len(final_url_str) > 4000: st.error("❌ 網址太長"); return

    cell = find_product_cell(sheet, name_str)
    
    if cell:
        # 更新
        sheet.update_cell(cell.row, 2, int(sheet.cell(cell.row, 2).value) + quantity)
        sheet.update_cell(cell.row, 3, price)
        if final_url_str: sheet.update_cell(cell.row, 4, final_url_str)
        if remarks: sheet.update_cell(cell.row, 5, remarks)
        st.success(f"✅ 更新 '{name_str}'")
    else:
        # 新增
        sheet.append_row([name_str, quantity, price, final_url_str, remarks])
        st.success(f"🆕 新增 '{name_str}'")

def sell_product(name, quantity):
    sheet = get_worksheet()
    if not sheet: return
    cell = find_product_cell(sheet, name)
    if cell:
        try: curr = int(sheet.cell(cell.row, 2).value)
        except: curr = 0
        if curr >= quantity:
            sheet.update_cell(cell.row, 2, curr - quantity)
            st.success(f"💰 售出 {quantity} 個")
        else:
            st.error("❌ 庫存不足")
    else:
        st.error("❌ 找不到商品")

def delete_product(name):
    sheet = get_worksheet()
    if not sheet: return
    cell = find_product_cell(sheet, name)
    if cell:
        sheet.delete_rows(cell.row)
        st.success(f"🗑️ 已刪除")
    else:
        st.error(f"❌ 找不到商品")

def update_product_info(name, new_qty, new_price, new_url_str, new_remarks):
    sheet = get_worksheet()
    if not sheet: return
    clean_url_str = str(new_url_str).strip()
    if len(clean_url_str) > 4000: st.error("❌ 連結太長"); return
    
    cell = find_product_cell(sheet, name)
    if cell:
        sheet.update_cell(cell.row, 2, new_qty)
        sheet.update_cell(cell.row, 3, new_price)
        sheet.update_cell(cell.row, 4, clean_url_str)
        sheet.update_cell(cell.row, 5, new_remarks)
        st.success(f"✅ 更新成功")
    else:
        st.error(f"❌ 找不到商品")

# --- 介面設計 ---
st.set_page_config(page_title="雲端進銷存", layout="wide")

if "is_admin" not in st.session_state: st.session_state["is_admin"] = False

with st.sidebar:
    st.header("👤 用戶登入")
    if not st.session_state["is_admin"]:
        st.text_input("輸入管理員密碼", type="password", key="password_input", on_change=check_password)
        st.info("💡 未登入僅能瀏覽")
    else:
        st.success("✅ 已登入")
        if st.button("登出"): logout()

st.title("☁️ 視覺化進銷存系統")

tab1, tab2, tab3, tab4, tab5 = st.tabs(["🖼️ 庫存圖牆", "➕ 進貨 (限)", "➖ 銷貨 (限)", "❌ 刪除 (限)", "✏️ 編輯 (限)"])

# Tab 1: 庫存圖牆 (修正顯示問題)
with tab1:
    st.header("庫存總覽")
    df = get_inventory_df()
    
    if not df.empty:
        col_search, col_refresh = st.columns([4, 1])
        with col_search:
            search_query = st.text_input("🔍 搜尋商品", "", placeholder="例如：123、紅色...")
        with col_refresh:
            st.write(""); st.write("")
            if st.button("🔄 重新整理", key="refresh_tab1"): st.rerun()

        if search_query:
            mask = df['商品名稱'].str.contains(search_query, case=False) | \
                   df['備註'].astype(str).str.contains(search_query, case=False)
            df_display = df[mask].copy()
        else:
            df_display = df.copy()

        if not df_display.empty:
            st.subheader(f"📋 清單 (共 {len(df_display)} 筆)")
            
            df_display['圖片連結'] = df_display['圖片連結'].astype(str).str.strip().replace('nan', '')
            df_display['主圖'] = df_display['圖片連結'].apply(lambda x: x.split(',')[0] if x else "")

            # 為避免重複名稱導致的 key error，建議 selectbox 使用 unique 值
            # 這裡我們處理顯示
            
            st.dataframe(
                df_display,
                column_config={
                    "商品名稱": st.column_config.TextColumn("商品名稱"),
                    "主圖": st.column_config.ImageColumn("圖片(首張)", width="small"),
                    "單價": st.column_config.NumberColumn(format="$%d"),
                    "備註": st.column_config.TextColumn("備註", width="medium"),
                },
                column_order=["商品名稱", "主圖", "數量", "單價", "備註"],
                use_container_width=True,
                hide_index=True
            )
            
            st.divider()
            col_sel, col_img = st.columns([1, 2])
            with col_sel:
                # 取得商品列表 (去重複)
                unique_products = df_display['商品名稱'].unique().tolist()
                selected_product = st.selectbox("選擇商品查看詳情", unique_products, key="tab1_select")
                
                # 關鍵修正：使用 iloc[-1] 取「最後一筆」(最新的一筆)，而不是 iloc[0]
                # 這樣就算資料庫裡有舊的重複資料，這裡也會顯示最新的
                product_data = df[df['商品名稱'] == selected_product].iloc[-1]
                
                st.info(f"**庫存**: {product_data['數量']} | **單價**: ${product_data['單價']}")
                st.text_area("備註內容", value=product_data.get('備註',''), disabled=True, key="tab1_remark")
                
            with col_img:
                raw_urls = str(product_data.get('圖片連結', '')).strip()
                if raw_urls:
                    url_list = [u.strip() for u in raw_urls.split(',') if u.strip()]
                    if url_list:
                        st.write(f"📸 共 {len(url_list)} 張圖片：")
                        st.image(url_list, width=200) 
                    else:
                        st.info("🖼️ 無圖片")
                else:
                    st.info("🖼️ 無圖片")
        else:
            st.warning("無符合資料")
    else:
        st.info("無資料")
        if st.button("🔄 重新整理", key="refresh_empty"): st.rerun()

# Tab 2: 進貨 (多圖 + 強化搜尋)
with tab2:
    st.header("商品進貨")
    if not st.session_state["is_admin"]: show_login_block()

    with st.form("add_form"):
        p_name = st.text_input("商品名稱 (ID)")
        c1, c2 = st.columns(2)
        p_qty = c1.number_input("數量", 1, value=10)
        p_price = c2.number_input("單價", 0, value=100)
        p_remarks = st.text_area("備註 (選填)")
        
        st.write("📸 圖片設定")
        p_files = st.file_uploader("方式 A：上傳 (可多選)", type=['png','jpg','jpeg'], accept_multiple_files=True)
        p_url_input = st.text_input("方式 B：貼上連結 (逗號隔開)", placeholder="https://...")

        if st.form_submit_button("確認進貨", type="primary"):
            if p_name:
                final_urls_list = []
                if p_url_input:
                    final_urls_list.extend([u.strip() for u in p_url_input.split(',') if u.strip()])
                if p_files:
                    with st.spinner(f"正在上傳 {len(p_files)} 張圖片..."):
                        for f in p_files:
                            u = upload_image_to_imgbb(f)
                            if u: final_urls_list.append(u)
                
                with st.spinner("寫入資料庫..."):
                    add_product(p_name, p_qty, p_price, final_urls_list, p_remarks)
            else:
                st.warning("請輸入名稱")

# Tab 3: 銷貨
with tab3:
    st.header("商品銷貨")
    if not st.session_state["is_admin"]: show_login_block()
    df = get_inventory_df()
    if not df.empty:
        with st.form("sell_form"):
            s_name = st.selectbox("選擇商品", df['商品名稱'].unique().tolist(), key="sell_select")
            s_qty = st.number_input("數量", 1)
            if st.form_submit_button("銷貨"): sell_product(s_name, s_qty)
    else:
