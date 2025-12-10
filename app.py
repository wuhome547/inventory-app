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
def get_worksheet():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    try:
        creds_dict = dict(st.secrets["gcp_service_account"])
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    except Exception:
        st.error("❌ 無法讀取憑證，請檢查 secrets 設定")
        return None
    client = gspread.authorize(creds)
    try:
        sheet = client.open(SPREADSHEET_NAME).sheet1
        return sheet
    except gspread.exceptions.SpreadsheetNotFound:
        st.error(f"❌ 找不到試算表 '{SPREADSHEET_NAME}'")
        return None

# --- ImgBB 上傳函式 ---
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

# --- 核心功能 ---
def get_inventory_df():
    sheet = get_worksheet()
    if sheet:
        data = sheet.get_all_records()
        df = pd.DataFrame(data)
        if '圖片連結' not in df.columns:
            df['圖片連結'] = ""
        return df
    return pd.DataFrame()

def add_product(name, quantity, price, image_url):
    sheet = get_worksheet()
    if not sheet: return
    # 簡單清理網址
    clean_url = str(image_url).strip()
    if len(clean_url) > 2000:
        st.error("❌ 網址太長")
        return

    cell_list = sheet.findall(name)
    if cell_list:
        cell = cell_list[0]
        sheet.update_cell(cell.row, 2, int(sheet.cell(cell.row, 2).value) + quantity)
        sheet.update_cell(cell.row, 3, price)
        if clean_url:
            sheet.update_cell(cell.row, 4, clean_url)
        st.success(f"✅ 更新 '{name}'")
    else:
        sheet.append_row([name, quantity, price, clean_url])
        st.success(f"🆕 新增 '{name}'")

def sell_product(name, quantity):
    sheet = get_worksheet()
    if not sheet: return
    cell_list = sheet.findall(name)
    if cell_list:
        cell = cell_list[0]
        current = int(sheet.cell(cell.row, 2).value)
        if current >= quantity:
            sheet.update_cell(cell.row, 2, current - quantity)
            st.success(f"💰 售出 {quantity} 個")
        else:
            st.error("❌ 庫存不足")
    else:
        st.error("❌ 找不到商品")

def delete_product(name):
    sheet = get_worksheet()
    if not sheet: return
    cell_list = sheet.findall(name)
    if cell_list:
        sheet.delete_rows(cell_list[0].row)
        st.success(f"🗑️ 已刪除")
def update_product_info(name, new_qty, new_price, new_url):
    """
    全方位更新商品資料：數量、價格、圖片
    """
    sheet = get_worksheet()
    if not sheet: return

    clean_url = str(new_url).strip()
    if len(clean_url) > 2000:
        st.error("❌ 圖片連結太長，無法儲存。")
        return

    cell_list = sheet.findall(name)
    if cell_list:
        cell = cell_list[0]
        # 批次更新比較快，也比較省 API 配額
        # 假設欄位順序：商品名稱(1), 數量(2), 單價(3), 圖片連結(4)
        sheet.update_cell(cell.row, 2, new_qty)
        sheet.update_cell(cell.row, 3, new_price)
        sheet.update_cell(cell.row, 4, clean_url)
        
        st.success(f"✅ 商品 '{name}' 資料已更新！")
    else:
        st.error(f"❌ 找不到商品 '{name}'")

def update_product_image(name, new_url):
    sheet = get_worksheet()
    if not sheet: return
    clean_url = str(new_url).strip()
    cell_list = sheet.findall(name)
    if cell_list:
        sheet.update_cell(cell_list[0].row, 4, clean_url)
        st.success(f"🖼️ 更新成功")
    else:
        st.error(f"❌ 找不到商品")

# --- 介面 ---
st.set_page_config(page_title="雲端進銷存", layout="wide")
st.title("☁️ 視覺化進銷存系統")

tab1, tab2, tab3, tab4, tab5 = st.tabs(["🖼️ 庫存圖牆", "➕ 進貨", "➖ 銷貨", "❌ 刪除", "✏️ 編輯資料"])

# --- 修正後的 Tab 1 ---
with tab1:
    st.header("庫存總覽")
    df = get_inventory_df()
    if not df.empty:
        st.subheader("📋 庫存清單")
        
        # 1. 處理網址：轉字串 -> 去空白 -> 處理 NaN
        df['圖片連結'] = df['圖片連結'].astype(str).str.strip().replace('nan', '')

        st.dataframe(
            df,
            column_config={
                "圖片連結": st.column_config.ImageColumn("圖片", width="small"),
                "單價": st.column_config.NumberColumn(format="$%d"),
            },
            use_container_width=True,
            hide_index=True
        )
        
        st.divider()
        st.subheader("🔍 查看商品大圖 (偵錯模式)")
        
        col_sel, col_img = st.columns([1, 2])
        with col_sel:
            selected_product = st.selectbox("選擇商品", df['商品名稱'].tolist())
            product_data = df[df['商品名稱'] == selected_product].iloc[0]
            st.info(f"庫存: {product_data['數量']} | 單價: ${product_data['單價']}")
            
        with col_img:
            # 取得並清理網址
            raw_url = str(product_data.get('圖片連結', ''))
            img_url = raw_url.strip()
            
            # 顯示判斷邏輯
            if img_url and len(img_url) > 10:
                try:
                    st.image(img_url, caption=selected_product, width=400)
                except Exception as e:
                    st.error("圖片載入失敗，網址可能無效。")
                    st.text(f"錯誤網址: {img_url}")
            else:
                st.warning("⚠️ 無法顯示圖片")
                st.write("目前資料庫中的內容為：")
                st.code(f"[{raw_url}]") # 用中括號包起來，看有沒有空白
                st.caption("如果是空的代表沒資料；如果有網址但沒顯示，請確認那是直接連結 (jpg/png)。")
    else:
        st.info("無資料")
    if st.button("🔄 重新整理"): st.rerun()

# Tab 2: 進貨 (優化版：同時顯示連結與上傳)
with tab2:
    st.header("商品進貨")
    with st.form("add_form"):
        p_name = st.text_input("商品名稱")
        c1, c2 = st.columns(2)
        with c1: p_qty = st.number_input("進貨數量", 1, value=10)
        with c2: p_price = st.number_input("單價", 0, value=100)
        
        st.divider()
        st.write("📸 **圖片設定 (擇一填寫，若兩者皆有則以「上傳」為優先)**")
        
        # 1. 直接顯示網址輸入框
        p_img_url = st.text_input("方式 A：貼上圖片連結 (ImgBB / Google Drive)", placeholder="https://...")
        
        st.caption("--- 或 ---")
        
        # 2. 直接顯示上傳按鈕
        p_uploaded_file = st.file_uploader("方式 B：從本機上傳圖片", type=['png', 'jpg', 'jpeg'])

        submitted = st.form_submit_button("確認進貨 / 更新", type="primary")
        
        if submitted:
            if p_name:
                final_url = p_img_url # 預設使用輸入框的網址
                
                # 邏輯判斷：如果有上傳檔案，就執行上傳並覆蓋掉網址
                if p_uploaded_file is not None:
                    with st.spinner("正在上傳圖片到 ImgBB..."):
                        imgbb_link = upload_image_to_imgbb(p_uploaded_file)
                        if imgbb_link:
                            final_url = imgbb_link
                        else:
                            st.stop() # 上傳失敗就停止
                            
                with st.spinner("寫入資料庫..."):
                    add_product(p_name, p_qty, p_price, final_url)
            else:
                st.warning("請輸入商品名稱")

with tab3:
    st.header("銷貨")
    df = get_inventory_df()
    if not df.empty:
        with st.form("sell"):
            name = st.selectbox("商品", df['商品名稱'].tolist())
            qty = st.number_input("數量", 1)
            if st.form_submit_button("銷貨"): sell_product(name, qty)
# Tab 4: 刪除 (優化確認流程)
with tab4:
    st.header("刪除商品")
    df = get_inventory_df()
    
    if not df.empty:
        # 初始化 Session State (用來記住現在是不是在確認狀態)
        if "delete_confirm_mode" not in st.session_state:
            st.session_state["delete_confirm_mode"] = False
            st.session_state["delete_target"] = None

        # 選擇商品區
        col_select, col_btn = st.columns([3, 1])
        
        with col_select:
            # 如果正在確認中，鎖定選擇框避免誤觸
            disable_select = st.session_state["delete_confirm_mode"]
            d_name = st.selectbox(
                "選擇要刪除的商品", 
                df['商品名稱'].tolist(), 
                disabled=disable_select,
                key="del_selectbox"
            )

        with col_btn:
            # 為了版面整齊，加個空白往下推
            st.write("") 
            st.write("")
            # 第一階段按鈕：申請刪除
            if st.button("🗑️ 刪除", type="primary", use_container_width=True, disabled=disable_select):
                st.session_state["delete_confirm_mode"] = True
                st.session_state["delete_target"] = d_name
                st.rerun()

        # 確認區域 (只有在按下刪除後才會顯示)
        if st.session_state["delete_confirm_mode"]:
            target = st.session_state["delete_target"]
            
            st.divider()
            st.warning(f"⚠️ 您確定要永久刪除 **「{target}」** 嗎？此動作無法復原！")
            
            # 顯示該商品圖片 (如果有)，讓使用者再次確認
            target_data = df[df['商品名稱'] == target].iloc[0]
            img_url = str(target_data.get('圖片連結', '')).strip()
            if img_url and len(img_url) > 10:
                st.image(img_url, width=150, caption="即將刪除的商品")

            c1, c2 = st.columns(2)
            with c1:
                if st.button("✅ 是，確認刪除", use_container_width=True):
                    with st.spinner(f"正在刪除 {target}..."):
                        delete_product(target)
                        # 刪除完成後，重置狀態
                        st.session_state["delete_confirm_mode"] = False
                        st.session_state["delete_target"] = None
                        st.rerun()
            
            with c2:
                if st.button("❌ 取消", use_container_width=True):
                    # 取消操作，重置狀態
                    st.session_state["delete_confirm_mode"] = False
                    st.session_state["delete_target"] = None
                    st.rerun()

    else:
        st.info("目前沒有商品可供刪除。")
        
# Tab 5: 編輯資料 (優化版：同時顯示)
with tab5:
    st.header("✏️ 編輯商品資料")
    df = get_inventory_df()
    
    if not df.empty:
        edit_name = st.selectbox("請選擇要編輯的商品", df['商品名稱'].tolist(), key="edit_select_full")
        
        # 取得目前資料
        current_data = df[df['商品名稱'] == edit_name].iloc[0]
        curr_qty = int(current_data['數量'])
        curr_price = int(current_data['單價'])
        curr_url = str(current_data.get('圖片連結', '')).strip()
        
        st.divider()
        
        with st.form("edit_full_form"):
            col_info, col_img_preview = st.columns([1, 1])
            
            with col_info:
                st.subheader("📦 基本資訊")
                new_qty = st.number_input("庫存數量", min_value=0, value=curr_qty)
                new_price = st.number_input("商品單價", min_value=0, value=curr_price)
            
            with col_img_preview:
                st.subheader("🖼️ 目前圖片")
                if curr_url and len(curr_url) < 2000:
                    st.image(curr_url, width=200)
                else:
                    st.info("尚無圖片")

            st.subheader("📸 更新圖片")
            st.caption("若不上傳新圖，也不修改連結，則會保留原圖。")
            
            # 1. 網址輸入框 (預設帶入舊網址)
            new_url_input = st.text_input("方式 A：修改圖片連結", value=curr_url)
            
            st.caption("--- 或 ---")
            
            # 2. 上傳按鈕
            new_file_upload = st.file_uploader("方式 B：上傳新圖片取代", type=['png', 'jpg', 'jpeg'])
            
            st.write("")
            submitted_edit = st.form_submit_button("💾 儲存變更", type="primary", use_container_width=True)
            
            if submitted_edit:
                final_url = new_url_input
                
                # 優先權邏輯：有上傳檔案 > 網址輸入框
                if new_file_upload:
                    with st.spinner("正在上傳新圖片..."):
                        uploaded_link = upload_image_to_imgbb(new_file_upload)
                        if uploaded_link:
                            final_url = uploaded_link
                        else:
                            st.warning("圖片上傳失敗，維持原樣。")
                
                with st.spinner("正在更新資料庫..."):
                    update_product_info(edit_name, new_qty, new_price, final_url)
                    st.rerun()

    else:
        st.info("目前沒有資料可供編輯。")
