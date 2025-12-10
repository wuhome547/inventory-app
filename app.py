import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import requests
import base64

# --- 設定區 (請修改這裡！) ---
SPREADSHEET_NAME = "inventory_system"
IMGBB_API_KEY = "f00d3bf5394c1a4973544c46d349cb96" 

# --- 連線設定：Google Sheets ---
def get_worksheet():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    try:
        creds_dict = dict(st.secrets["gcp_service_account"])
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    except Exception:
        st.error("❌ 無法讀取憑證，請檢查 .streamlit/secrets.toml 設定")
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
    """
    將圖片上傳到 ImgBB 圖床，回傳圖片網址。
    """
    if not IMGBB_API_KEY or IMGBB_API_KEY == "請將您的 ImgBB API Key 貼在這裡":
        st.error("⚠️ 請先在程式碼中設定 IMGBB_API_KEY")
        return ""

    try:
        # ImgBB 需要將圖片轉為 base64 格式
        image_content = uploaded_file.read()
        b64_image = base64.b64encode(image_content)
        
        payload = {
            "key": IMGBB_API_KEY,
            "image": b64_image,
        }
        
        response = requests.post("https://api.imgbb.com/1/upload", data=payload)
        result = response.json()
        
        if result["status"] == 200:
            return result["data"]["url"]
        else:
            st.error(f"ImgBB 上傳失敗: {result['status']} - {result.get('error', {}).get('message')}")
            return ""
            
    except Exception as e:
        st.error(f"上傳過程發生錯誤: {e}")
        return ""

# --- 核心功能函數 ---

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

    cell_list = sheet.findall(name)
    
    if cell_list:
        cell = cell_list[0]
        current_qty = int(sheet.cell(cell.row, 2).value)
        new_qty = current_qty + quantity
        sheet.update_cell(cell.row, 2, new_qty)
        sheet.update_cell(cell.row, 3, price)
        if image_url:
            sheet.update_cell(cell.row, 4, image_url)
        st.success(f"✅ 已更新 '{name}'。")
    else:
        sheet.append_row([name, quantity, price, image_url])
        st.success(f"🆕 已新增 '{name}'。")

def sell_product(name, quantity):
    sheet = get_worksheet()
    if not sheet: return
    cell_list = sheet.findall(name)
    if cell_list:
        cell = cell_list[0]
        current_qty = int(sheet.cell(cell.row, 2).value)
        if current_qty >= quantity:
            new_qty = current_qty - quantity
            sheet.update_cell(cell.row, 2, new_qty)
            st.success(f"💰 售出 {quantity} 個 '{name}'。剩: {new_qty}")
        else:
            st.error(f"❌ 庫存不足 ({current_qty})")
    else:
        st.error(f"❌ 找不到商品")

def delete_product(name):
    sheet = get_worksheet()
    if not sheet: return
    cell_list = sheet.findall(name)
    if cell_list:
        sheet.delete_rows(cell_list[0].row)
        st.success(f"🗑️ 已刪除 '{name}'")
    else:
        st.error(f"❌ 找不到商品")

def update_product_image(name, new_url):
    sheet = get_worksheet()
    if not sheet: return
    cell_list = sheet.findall(name)
    if cell_list:
        cell = cell_list[0]
        sheet.update_cell(cell.row, 4, new_url)
        st.success(f"🖼️ 已更新 '{name}' 的圖片連結！")
    else:
        st.error(f"❌ 找不到商品 '{name}'")

# --- 網頁介面設計 ---

st.set_page_config(page_title="雲端進銷存(ImgBB版)", layout="wide")
st.title("☁️ 視覺化進銷存系統")

tab1, tab2, tab3, tab4, tab5 = st.tabs(["🖼️ 庫存圖牆", "➕ 進貨", "➖ 銷貨", "❌ 刪除", "✏️ 編輯資料"])

# Tab 1: 庫存圖牆
with tab1:
    st.header("庫存總覽")
    df = get_inventory_df()
    if not df.empty:
        st.subheader("📋 庫存清單")
        st.dataframe(
            df,
            column_config={
                "圖片連結": st.column_config.ImageColumn("商品圖片", width="small"),
                "單價": st.column_config.NumberColumn(format="$%d"),
            },
            use_container_width=True,
            hide_index=True
        )
        st.divider()
        st.subheader("🔍 查看商品大圖")
        col_sel, col_img = st.columns([1, 2])
        with col_sel:
            selected_product = st.selectbox("查看大圖-選擇商品：", df['商品名稱'].tolist())
            product_data = df[df['商品名稱'] == selected_product].iloc[0]
            st.info(f"庫存: {product_data['數量']} | 單價: ${product_data['單價']}")
        with col_img:
            img_url = product_data.get('圖片連結', '')
            if img_url:
                st.image(img_url, caption=selected_product, width=400)
            else:
                st.write("🖼️ 此商品尚未設定圖片")
    else:
        st.info("目前沒有資料。")
    if st.button("🔄 重新整理"): st.rerun()

# Tab 2: 進貨
with tab2:
    st.header("商品進貨")
    with st.form("add_form"):
        p_name = st.text_input("商品名稱")
        c1, c2 = st.columns(2)
        with c1: p_qty = st.number_input("進貨數量", 1, value=10)
        with c2: p_price = st.number_input("單價", 0, value=100)
        
        st.write("---")
        st.write("📸 圖片來源")
        img_source = st.radio("選擇方式：", ["🔗 貼上連結", "📤 直接上傳 (ImgBB)"], horizontal=True)
        
        p_img_url = ""
        p_uploaded_file = None
        
        if img_source == "🔗 貼上連結":
            p_img_url = st.text_input("圖片連結")
        else:
            p_uploaded_file = st.file_uploader("上傳圖片", type=['png', 'jpg', 'jpeg'])

        submitted = st.form_submit_button("確認進貨 / 更新")
        
        if submitted:
            if p_name:
                final_url = p_img_url
                
                if p_uploaded_file is not None:
                    with st.spinner("正在上傳圖片到 ImgBB..."):
                        imgbb_link = upload_image_to_imgbb(p_uploaded_file)
                        if imgbb_link:
                            final_url = imgbb_link
                        else:
                            st.stop() # 上傳失敗就停下來
                            
                with st.spinner("寫入資料庫..."):
                    add_product(p_name, p_qty, p_price, final_url)
            else:
                st.warning("請輸入名稱")

# Tab 3: 銷貨
with tab3:
    st.header("商品銷貨")
    df = get_inventory_df()
    if not df.empty:
        with st.form("sell_form"):
            s_name = st.selectbox("銷貨-選擇商品", df['商品名稱'].tolist())
            s_qty = st.number_input("銷售數量", 1, value=1)
            if st.form_submit_button("確認銷貨"):
                sell_product(s_name, s_qty)
    else:
        st.warning("無庫存")

# Tab 4: 刪除
with tab4:
    st.header("刪除商品")
    df = get_inventory_df()
    if not df.empty:
        with st.form("delete_form"):
            d_name = st.selectbox("刪除-選擇商品", df['商品名稱'].tolist())
            confirm = st.checkbox("確認刪除")
            if st.form_submit_button("執行刪除"):
                if confirm:
                    delete_product(d_name)
                    st.rerun()
                else:
                    st.error("請勾選確認")

# Tab 5: 編輯資料
with tab5:
    st.header("✏️ 編輯商品資料")
    df = get_inventory_df()
    
    if not df.empty:
        edit_name = st.selectbox("選擇要編輯的商品", df['商品名稱'].tolist(), key="edit_select")
        current_data = df[df['商品名稱'] == edit_name].iloc[0]
        current_url = current_data.get('圖片連結', '')
        
        st.write("---")
        col_old, col_new = st.columns(2)
        
        with col_old:
            st.subheader("原本的圖片")
            if current_url:
                st.image(current_url, width=200)
            else:
                st.info("無圖片")

        with col_new:
            st.subheader("更換新圖片")
            with st.form("update_img_form"):
                img_source_edit = st.radio("來源：", ["🔗 貼上連結", "📤 直接上傳 (ImgBB)"], horizontal=True, key="edit_radio")
                
                new_img_url_edit = ""
                new_uploaded_file = None
                
                if img_source_edit == "🔗 貼上連結":
                    new_img_url_edit = st.text_input("輸入新連結")
                else:
                    new_uploaded_file = st.file_uploader("上傳新圖片", type=['png', 'jpg', 'jpeg'], key="edit_uploader")

                submitted_update = st.form_submit_button("更新圖片")
                
                if submitted_update:
                    final_url_edit = new_img_url_edit
                    
                    if new_uploaded_file:
                        with st.spinner("上傳中..."):
                            imgbb_link = upload_image_to_imgbb(new_uploaded_file)
                            if imgbb_link:
                                final_url_edit = imgbb_link
                    
                    if final_url_edit:
                        update_product_image(edit_name, final_url_edit)
                        st.rerun()
                    else:
                        st.warning("請輸入連結或上傳圖片")
    else:
        st.info("無資料")
