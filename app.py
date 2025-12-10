import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# --- 設定區 ---
SPREADSHEET_NAME = "inventory_system"

# --- 連線設定 ---
def get_worksheet():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    try:
        creds_dict = dict(st.secrets["gcp_service_account"])
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    except Exception:
        # 本地測試用 (若無 secrets 則報錯)
        st.error("❌ 無法讀取憑證，請檢查 .streamlit/secrets.toml 設定")
        return None
    client = gspread.authorize(creds)
    try:
        sheet = client.open(SPREADSHEET_NAME).sheet1
        return sheet
    except gspread.exceptions.SpreadsheetNotFound:
        st.error(f"❌ 找不到試算表 '{SPREADSHEET_NAME}'")
        return None

# --- 輔助函數：處理圖片連結 ---
def process_image_url(url):
    """
    將 Google Drive 的分享連結轉換為可直接顯示的圖片連結。
    """
    if not url: return ""
    url = str(url).strip()
    
    # 處理 Google Drive 連結
    if "drive.google.com" in url and "/d/" in url:
        try:
            file_id = url.split("/d/")[1].split("/")[0]
            return f"https://drive.google.com/thumbnail?id={file_id}&sz=w1000"
        except:
            return url
    return url

# --- 核心功能函數 ---

def get_inventory_df():
    sheet = get_worksheet()
    if sheet:
        data = sheet.get_all_records()
        df = pd.DataFrame(data)
        # 確保有圖片連結欄位
        if '圖片連結' not in df.columns:
            df['圖片連結'] = ""
        return df
    return pd.DataFrame()

def add_product(name, quantity, price, image_url):
    """進貨 (若存在則更新數量/價格/圖片)"""
    sheet = get_worksheet()
    if not sheet: return

    final_img_url = process_image_url(image_url)
    cell_list = sheet.findall(name)
    
    if cell_list:
        # 更新
        cell = cell_list[0]
        current_qty = int(sheet.cell(cell.row, 2).value)
        new_qty = current_qty + quantity
        
        sheet.update_cell(cell.row, 2, new_qty)
        sheet.update_cell(cell.row, 3, price)
        sheet.update_cell(cell.row, 4, final_img_url)
        st.success(f"✅ 已更新 '{name}'。")
    else:
        # 新增
        sheet.append_row([name, quantity, price, final_img_url])
        st.success(f"🆕 已新增 '{name}'。")

def sell_product(name, quantity):
    """銷貨"""
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
    """刪除"""
    sheet = get_worksheet()
    if not sheet: return
    cell_list = sheet.findall(name)
    if cell_list:
        sheet.delete_rows(cell_list[0].row)
        st.success(f"🗑️ 已刪除 '{name}'")
    else:
        st.error(f"❌ 找不到商品")

def update_product_image(name, new_url):
    """單獨更新商品圖片"""
    sheet = get_worksheet()
    if not sheet: return

    cell_list = sheet.findall(name)
    if cell_list:
        cell = cell_list[0]
        final_img_url = process_image_url(new_url)
        # 更新第 4 欄 (圖片連結)
        sheet.update_cell(cell.row, 4, final_img_url)
        st.success(f"🖼️ 已更新 '{name}' 的圖片連結！")
    else:
        st.error(f"❌ 找不到商品 '{name}'")

# --- 網頁介面設計 ---

st.set_page_config(page_title="雲端進銷存(含圖)", layout="wide")
st.title("☁️ 視覺化進銷存系統")

# 定義 5 個分頁
tab1, tab2, tab3, tab4, tab5 = st.tabs(["🖼️ 庫存圖牆", "➕ 進貨", "➖ 銷貨", "❌ 刪除", "✏️ 編輯資料"])

# Tab 1: 庫存圖牆 (無變動)
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

# Tab 2: 進貨 (無變動)
with tab2:
    st.header("商品進貨")
    with st.form("add_form"):
        p_name = st.text_input("商品名稱")
        c1, c2 = st.columns(2)
        with c1: p_qty = st.number_input("進貨數量", 1, value=10)
        with c2: p_price = st.number_input("單價", 0, value=100)
        p_img = st.text_input("圖片連結 (選填)")
        if st.form_submit_button("確認"):
            if p_name:
                add_product(p_name, p_qty, p_price, p_img)
            else:
                st.warning("請輸入名稱")

# Tab 3: 銷貨 (無變動)
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

# Tab 4: 刪除 (無變動)
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

# Tab 5: 新增的編輯功能
with tab5:
    st.header("✏️ 編輯商品資料")
    df = get_inventory_df()
    
    if not df.empty:
        # 下拉選單選擇商品
        edit_name = st.selectbox("選擇要編輯圖片的商品", df['商品名稱'].tolist(), key="edit_select")
        
        # 取得該商品目前的連結
        current_data = df[df['商品名稱'] == edit_name].iloc[0]
        current_url = current_data.get('圖片連結', '')
        
        st.write("---")
        col_old, col_new = st.columns(2)
        
        with col_old:
            st.subheader("原本的圖片")
            if current_url:
                st.image(current_url, width=200)
                st.text("目前連結：")
                st.code(current_url)
            else:
                st.info("目前沒有設定圖片")

        with col_new:
            st.subheader("設定新圖片")
            with st.form("update_img_form"):
                new_img_url = st.text_input("請輸入新的圖片連結")
                submitted_update = st.form_submit_button("更新圖片")
                
                if submitted_update:
                    if new_img_url:
                        with st.spinner("正在更新..."):
                            update_product_image(edit_name, new_img_url)
                            st.rerun() # 成功後刷新頁面
                    else:
                        st.warning("連結不能為空")
    else:
        st.info("目前沒有商品資料可編輯。")
