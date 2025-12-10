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
        st.error("❌ 無法讀取憑證，請檢查 .streamlit/secrets.toml 設定")
        return None
    client = gspread.authorize(creds)
    try:
        sheet = client.open(SPREADSHEET_NAME).sheet1
        return sheet
    except gspread.exceptions.SpreadsheetNotFound:
        st.error(f"❌ 找不到試算表 '{SPREADSHEET_NAME}'")
        return None

# --- ImgBB 上傳函式 (修正版) ---
def upload_image_to_imgbb(uploaded_file):
    if not IMGBB_API_KEY or IMGBB_API_KEY.startswith("請將"):
        st.error("⚠️ 請先在程式碼中設定 IMGBB_API_KEY")
        return ""

    try:
        image_content = uploaded_file.read()
        b64_image = base64.b64encode(image_content)
        
        payload = {
            "key": IMGBB_API_KEY,
            "image": b64_image,
        }
        
        # 使用 POST 上傳
        response = requests.post("https://api.imgbb.com/1/upload", data=payload)
        result = response.json()
        
        if result["status"] == 200:
            # 改用 'url' (直接連結)，通常是 .jpg/.png 結尾，最穩定
            return result["data"]["url"]
        else:
            st.error(f"ImgBB 上傳失敗: {result.get('error', {}).get('message')}")
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

    # 簡單驗證網址長度，避免寫入 Base64
    if len(str(image_url)) > 2000:
        st.error("❌ 圖片連結太長，無法儲存！請使用網址而非 Base64 編碼。")
        return

    cell_list = sheet.findall(name)
    if cell_list:
        cell = cell_list[0]
        sheet.update_cell(cell.row, 2, int(sheet.cell(cell.row, 2).value) + quantity)
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
        st.success(f"🗑️ 已刪除 '{name}'")

def update_product_image(name, new_url):
    sheet = get_worksheet()
    if not sheet: return
    if len(str(new_url)) > 2000:
        st.error("❌ 連結太長，請確認是否為有效網址。")
        return
    cell_list = sheet.findall(name)
    if cell_list:
        sheet.update_cell(cell_list[0].row, 4, new_url)
        st.success(f"🖼️ 已更新 '{name}'")
    else:
        st.error(f"❌ 找不到 '{name}'")

# --- 網頁介面 ---

st.set_page_config(page_title="雲端進銷存", layout="wide")
st.title("☁️ 視覺化進銷存系統")

tab1, tab2, tab3, tab4, tab5 = st.tabs(["🖼️ 庫存圖牆", "➕ 進貨", "➖ 銷貨", "❌ 刪除", "✏️ 編輯資料"])

with tab1:
    st.header("庫存總覽")
    df = get_inventory_df()
    if not df.empty:
        st.subheader("📋 庫存清單")
        
        # --- 關鍵修正：資料清理 ---
        # 1. 轉成字串
        df['圖片連結'] = df['圖片連結'].astype(str)
        # 2. 如果連結太長(超過500字)或不是http開頭，就清空，避免報錯
        mask_bad_url = (df['圖片連結'].str.len() > 500) | (~df['圖片連結'].str.startswith('http'))
        df.loc[mask_bad_url, '圖片連結'] = ""
        # ------------------------

        st.dataframe(
            df,
            column_config={
                "圖片連結": st.column_config.ImageColumn("圖片", width="small"),
                "單價": st.column_config.NumberColumn(format="$%d"),
            },
            use_container_width=True,
            hide_index=True
        )
        
        # 下方查看大圖區域 (同樣加入保護機制)
        st.divider()
        col_sel, col_img = st.columns([1, 2])
        with col_sel:
            selected_product = st.selectbox("查看大圖", df['商品名稱'].tolist())
            product_data = df[df['商品名稱'] == selected_product].iloc[0]
            st.info(f"庫存: {product_data['數量']} | 單價: ${product_data['單價']}")
        with col_img:
            img_url = str(product_data.get('圖片連結', ''))
            # 只有當網址正常時才顯示
            if img_url and img_url.startswith('http') and len(img_url) < 500:
                st.image(img_url, caption=selected_product, width=400)
            else:
                st.write("🖼️ 無圖片或連結格式錯誤")
    else:
        st.info("無資料")
    if st.button("🔄 重新整理"): st.rerun()

# (Tab 2, 3, 4, 5 的介面邏輯與之前相同，為節省篇幅省略，請保留您原本的程式碼，或是告知我需要完整版)
# 如果您直接複製貼上，請確保下面的 Tab 2~5 也有包含進去
# 為方便您，以下補上簡化的 Tab 2~5 結構，請替換您原本的對應區塊：

with tab2:
    st.header("進貨")
    with st.form("add_form"):
        p_name = st.text_input("名稱")
        c1, c2 = st.columns(2)
        p_qty = c1.number_input("數量", 1, value=10)
        p_price = c2.number_input("單價", 0, value=100)
        
        img_src = st.radio("圖片", ["連結", "上傳 (ImgBB)"], horizontal=True)
        p_url, p_file = "", None
        if img_src == "連結": p_url = st.text_input("網址")
        else: p_file = st.file_uploader("上傳", type=['png','jpg'])
        
        if st.form_submit_button("確認"):
            if p_file:
                with st.spinner("上傳中..."):
                    url = upload_image_to_imgbb(p_file)
                    if url: p_url = url
            if p_name: add_product(p_name, p_qty, p_price, p_url)

with tab3:
    st.header("銷貨")
    df = get_inventory_df()
    if not df.empty:
        with st.form("sell"):
            s_name = st.selectbox("商品", df['商品名稱'].tolist())
            s_qty = st.number_input("數量", 1)
            if st.form_submit_button("銷貨"): sell_product(s_name, s_qty)

with tab4:
    st.header("刪除")
    if not df.empty:
        with st.form("del"):
            d_name = st.selectbox("商品", df['商品名稱'].tolist())
            if st.form_submit_button("刪除") and st.checkbox("確認"):
                delete_product(d_name); st.rerun()

with tab5:
    st.header("編輯")
    if not df.empty:
        e_name = st.selectbox("編輯對象", df['商品名稱'].tolist(), key="e_sel")
        curr = df[df['商品名稱']==e_name].iloc[0].get('圖片連結','')
        st.image(curr, width=150) if curr and len(str(curr))<500 else None
        
        with st.form("upd_img"):
            src = st.radio("來源", ["連結", "上傳"], horizontal=True)
            n_url, n_file = "", None
            if src == "連結": n_url = st.text_input("新網址")
            else: n_file = st.file_uploader("新圖片", type=['png','jpg'])
            
            if st.form_submit_button("更新"):
                if n_file:
                    with st.spinner("上傳中..."):
                        u = upload_image_to_imgbb(n_file)
                        if u: n_url = u
                if n_url: update_product_image(e_name, n_url); st.rerun()
