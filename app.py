import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import requests
import base64

# --- 設定區 ---
SPREADSHEET_NAME = "inventory_system"
IMGBB_API_KEY = "a9e1ead23aa6fb34478cf7a16adaf34b" 

# --- 連線設定 (改良版：加入快取機制防斷線) ---

@st.cache_resource(ttl=600)  # 設定快取，讓連線保持 10 分鐘，不用一直重登
def get_gspread_client():
    """
    只執行一次登入動作，並將連線物件暫存在記憶體中。
    """
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
    """從快取中取得連線，並開啟試算表"""
    client = get_gspread_client()
    if not client: return None
    
    try:
        sheet = client.open(SPREADSHEET_NAME).sheet1
        return sheet
    except gspread.exceptions.SpreadsheetNotFound:
        st.error(f"❌ 找不到試算表 '{SPREADSHEET_NAME}'")
        return None
    except gspread.exceptions.APIError:
        st.warning("⚠️ Google API 連線忙碌中，請稍等 1 分鐘後再試...")
        # 清除快取，下次重試新的連線
        st.cache_resource.clear()
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

# --- 核心功能函數 ---

def get_inventory_df():
    sheet = get_worksheet()
    if sheet:
        data = sheet.get_all_records()
        df = pd.DataFrame(data)
        # 確保必要欄位存在
        if '圖片連結' not in df.columns: df['圖片連結'] = ""
        if '備註' not in df.columns: df['備註'] = "" # 新增備註欄位防呆
        return df
    return pd.DataFrame()

def add_product(name, quantity, price, image_url, remarks):
    """新增或更新商品 (包含備註)"""
    sheet = get_worksheet()
    if not sheet: return

    clean_url = str(image_url).strip()
    if len(clean_url) > 2000:
        st.error("❌ 網址太長")
        return

    cell_list = sheet.findall(name)
    if cell_list:
        # 更新現有商品
        cell = cell_list[0]
        # 更新數量(2), 單價(3), 圖片(4), 備註(5)
        current_qty = int(sheet.cell(cell.row, 2).value)
        sheet.update_cell(cell.row, 2, current_qty + quantity)
        sheet.update_cell(cell.row, 3, price)
        if clean_url:
            sheet.update_cell(cell.row, 4, clean_url)
        # 如果使用者有填寫備註，就更新備註；沒填則保留原樣或是更新為空？
        # 這裡的邏輯設定為：如果有填寫才更新，這樣比較安全
        if remarks:
            sheet.update_cell(cell.row, 5, remarks)
            
        st.success(f"✅ 已更新 '{name}' 的庫存與資訊。")
    else:
        # 新增全新商品
        # 欄位順序：名稱, 數量, 單價, 圖片連結, 備註
        sheet.append_row([name, quantity, price, clean_url, remarks])
        st.success(f"🆕 已新增 '{name}'。")

def sell_product(name, quantity):
    sheet = get_worksheet()
    if not sheet: return
    cell_list = sheet.findall(name)
    if cell_list:
        cell = cell_list[0]
        current = int(sheet.cell(cell.row, 2).value)
        if current >= quantity:
            sheet.update_cell(cell.row, 2, current - quantity)
            st.success(f"💰 售出 {quantity} 個 '{name}'。")
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

def update_product_info(name, new_qty, new_price, new_url, new_remarks):
    """全方位更新 (包含備註)"""
    sheet = get_worksheet()
    if not sheet: return

    clean_url = str(new_url).strip()
    if len(clean_url) > 2000:
        st.error("❌ 連結太長")
        return

    cell_list = sheet.findall(name)
    if cell_list:
        cell = cell_list[0]
        # 批次更新：數量(2), 單價(3), 圖片(4), 備註(5)
        sheet.update_cell(cell.row, 2, new_qty)
        sheet.update_cell(cell.row, 3, new_price)
        sheet.update_cell(cell.row, 4, clean_url)
        sheet.update_cell(cell.row, 5, new_remarks)
        
        st.success(f"✅ 商品 '{name}' 資料已更新！")
    else:
        st.error(f"❌ 找不到商品")

# --- 介面設計 ---

st.set_page_config(page_title="雲端進銷存", layout="wide")
st.title("☁️ 視覺化進銷存系統")

tab1, tab2, tab3, tab4, tab5 = st.tabs(["🖼️ 庫存圖牆", "➕ 進貨", "➖ 銷貨", "❌ 刪除", "✏️ 編輯資料"])

# Tab 1: 庫存圖牆
with tab1:
    st.header("庫存總覽")
    df = get_inventory_df()
    if not df.empty:
        st.subheader("📋 庫存清單")
        
        df['圖片連結'] = df['圖片連結'].astype(str).str.strip().replace('nan', '')
        # 處理備註的 NaN
        df['備註'] = df['備註'].astype(str).replace('nan', '')

        st.dataframe(
            df,
            column_config={
                "圖片連結": st.column_config.ImageColumn("圖片", width="small"),
                "單價": st.column_config.NumberColumn(format="$%d"),
                "備註": st.column_config.TextColumn("備註說明", width="medium"),
            },
            use_container_width=True,
            hide_index=True
        )
        
        st.divider()
        st.subheader("🔍 商品詳細資訊")
        
        col_sel, col_img = st.columns([1, 2])
        with col_sel:
            selected_product = st.selectbox("選擇商品", df['商品名稱'].tolist())
            product_data = df[df['商品名稱'] == selected_product].iloc[0]
            
            st.info(f"""
            **庫存**: {product_data['數量']}
            **單價**: ${product_data['單價']}
            """)
            # 顯示備註
            remarks_text = product_data.get('備註', '無')
            st.text_area("📝 備註內容", value=remarks_text, disabled=True)
            
        with col_img:
            img_url = str(product_data.get('圖片連結', '')).strip()
            if img_url and len(img_url) > 10:
                try:
                    st.image(img_url, caption=selected_product, width=400)
                except:
                    st.error("無法載入圖片")
            else:
                st.info("🖼️ 無圖片")
    else:
        st.info("無資料")
    if st.button("🔄 重新整理"): st.rerun()

# Tab 2: 進貨 (加入備註欄位)
with tab2:
    st.header("商品進貨")
    with st.form("add_form"):
        p_name = st.text_input("商品名稱")
        c1, c2 = st.columns(2)
        with c1: p_qty = st.number_input("進貨數量", 1, value=10)
        with c2: p_price = st.number_input("單價", 0, value=100)
        
        # 新增備註輸入
        p_remarks = st.text_area("📝 商品備註 (選填)", placeholder="例如：廠商A、紅色款、放在上層貨架...")

        st.divider()
        st.write("📸 圖片設定")
        p_img_url = st.text_input("方式 A：貼上連結", placeholder="https://...")
        st.caption("--- 或 ---")
        p_uploaded_file = st.file_uploader("方式 B：上傳圖片", type=['png', 'jpg', 'jpeg'])

        if st.form_submit_button("確認進貨 / 更新", type="primary"):
            if p_name:
                final_url = p_img_url
                if p_uploaded_file:
                    with st.spinner("上傳圖片中..."):
                        u = upload_image_to_imgbb(p_uploaded_file)
                        if u: final_url = u
                
                with st.spinner("寫入資料庫..."):
                    add_product(p_name, p_qty, p_price, final_url, p_remarks)
            else:
                st.warning("請輸入名稱")

# Tab 3: 銷貨 (無變動)
with tab3:
    st.header("商品銷貨")
    df = get_inventory_df()
    if not df.empty:
        with st.form("sell"):
            name = st.selectbox("商品", df['商品名稱'].tolist())
            qty = st.number_input("數量", 1)
            if st.form_submit_button("銷貨"): sell_product(name, qty)
    else:
        st.warning("無庫存")

# Tab 4: 刪除 (無變動)
with tab4:
    st.header("刪除商品")
    df = get_inventory_df()
    if not df.empty:
        if "del_mode" not in st.session_state: st.session_state["del_mode"] = False
        
        col1, col2 = st.columns([3, 1])
        with col1:
            d_name = st.selectbox("選擇商品", df['商品名稱'].tolist(), disabled=st.session_state["del_mode"])
        with col2:
            st.write(""); st.write("")
            if st.button("🗑️ 刪除", type="primary", disabled=st.session_state["del_mode"]):
                st.session_state["del_mode"] = True
                st.session_state["del_target"] = d_name
                st.rerun()

        if st.session_state["del_mode"]:
            st.warning(f"確認刪除 **{st.session_state['del_target']}**？")
            c1, c2 = st.columns(2)
            with c1:
                if st.button("✅ 確認"):
                    delete_product(st.session_state["del_target"])
                    st.session_state["del_mode"] = False
                    st.rerun()
            with c2:
                if st.button("❌ 取消"):
                    st.session_state["del_mode"] = False
                    st.rerun()

# Tab 5: 編輯 (加入備註編輯)
with tab5:
    st.header("✏️ 編輯商品資料")
    df = get_inventory_df()
    
    if not df.empty:
        edit_name = st.selectbox("選擇要編輯的商品", df['商品名稱'].tolist(), key="es")
        
        curr = df[df['商品名稱'] == edit_name].iloc[0]
        curr_qty = int(curr['數量'])
        curr_price = int(curr['單價'])
        curr_url = str(curr.get('圖片連結', '')).strip()
        curr_remarks = str(curr.get('備註', '')) # 取得目前備註

        st.divider()
        
        with st.form("edit_form"):
            c1, c2 = st.columns(2)
            with c1:
                n_qty = st.number_input("庫存", 0, value=curr_qty)
                n_price = st.number_input("單價", 0, value=curr_price)
            with c2:
                # 備註編輯區
                n_remarks = st.text_area("📝 備註", value=curr_remarks, height=100)

            st.subheader("📸 更新圖片")
            if curr_url and len(curr_url)<2000: st.image(curr_url, width=150)
            
            n_url = st.text_input("圖片連結", value=curr_url)
            st.caption("--- 或 ---")
            n_file = st.file_uploader("上傳新圖片", type=['png','jpg'])
            
            if st.form_submit_button("💾 儲存變更", type="primary"):
                final_url = n_url
                if n_file:
                    with st.spinner("上傳中..."):
                        u = upload_image_to_imgbb(n_file)
                        if u: final_url = u
                
                with st.spinner("更新中..."):
                    # 呼叫更新函式 (帶入備註)
                    update_product_info(edit_name, n_qty, n_price, final_url, n_remarks)
                    st.rerun()
    else:
        st.info("無資料")
