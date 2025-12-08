import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# --- 設定區 ---
# 這裡填寫您的 Google Sheet 檔案名稱
SPREADSHEET_NAME = "inventory_system"

# --- 連線設定 ---
def get_worksheet():
    """連線到 Google Sheets 並回傳工作表物件"""
    # 定義需要的權限範圍
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    
    # 從 Streamlit Secrets 讀取憑證 (部署時使用)
    # 本地測試時，您可以直接指定 json 檔案路徑，但在雲端部署建議用 secrets
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
        st.error(f"❌ 找不到名稱為 '{SPREADSHEET_NAME}' 的試算表，請確認名稱正確且已共用給服務帳號。")
        return None

# --- 核心功能函數 ---

def get_inventory_df():
    """取得目前所有庫存資料"""
    sheet = get_worksheet()
    if sheet:
        data = sheet.get_all_records()
        return pd.DataFrame(data)
    return pd.DataFrame()

def add_product(name, quantity, price):
    """進貨：新增或更新商品"""
    sheet = get_worksheet()
    if not sheet: return

    # 使用 findall 搜尋，找不到會回傳空清單，不會報錯
    cell_list = sheet.findall(name)
    
    if cell_list:
        # 找到商品 -> 更新 (取第一個找到的結果)
        cell = cell_list[0]
        
        # 取得目前數量 (假設數量在第 2 欄)
        current_qty = int(sheet.cell(cell.row, 2).value)
        new_qty = current_qty + quantity
        
        # 更新數量與單價
        sheet.update_cell(cell.row, 2, new_qty)
        sheet.update_cell(cell.row, 3, price)
        
        st.success(f"✅ 已更新 '{name}'。新庫存: {new_qty}, 最新單價: {price}")
    else:
        # 沒找到商品 -> 新增一行
        sheet.append_row([name, quantity, price])
        st.success(f"🆕 已新增商品 '{name}'。庫存: {quantity}, 單價: {price}")

def sell_product(name, quantity):
    """銷貨：扣除庫存"""
    sheet = get_worksheet()
    if not sheet: return

    # 使用 findall 搜尋
    cell_list = sheet.findall(name)
    
    if cell_list:
        cell = cell_list[0]
        current_qty = int(sheet.cell(cell.row, 2).value)
        
        if current_qty >= quantity:
            new_qty = current_qty - quantity
            sheet.update_cell(cell.row, 2, new_qty)
            st.success(f"💰 成功售出 {quantity} 個 '{name}'。剩餘庫存: {new_qty}")
        else:
            st.error(f"❌ 庫存不足！'{name}' 目前只有 {current_qty} 個。")
    else:
        st.error(f"❌ 找不到商品 '{name}'。")


# --- 網頁介面設計 ---

st.set_page_config(page_title="雲端進銷存系統", layout="centered")
st.title("☁️ Google Sheets 進銷存系統")

tab1, tab2, tab3 = st.tabs(["📊 庫存總覽", "➕ 進貨 (入庫)", "➖ 銷貨 (出庫)"])

with tab1:
    st.header("庫存清單")
    df = get_inventory_df()
    
    if not df.empty:
        # 確保欄位是數字格式，避免字串計算錯誤
        df['數量'] = pd.to_numeric(df['數量'], errors='coerce').fillna(0)
        df['單價'] = pd.to_numeric(df['單價'], errors='coerce').fillna(0)
        
        st.dataframe(df, use_container_width=True)
        
        total_items = df['數量'].sum()
        total_value = (df['數量'] * df['單價']).sum()
        col1, col2 = st.columns(2)
        col1.metric("總庫存數量", f"{int(total_items)}")
        col2.metric("庫存總價值", f"${int(total_value):,}")
    else:
        st.info("目前沒有資料，或無法讀取試算表。")
    
    if st.button("重新整理資料"):
        st.rerun()

with tab2:
    st.header("商品進貨登記")
    with st.form("add_form"):
        p_name = st.text_input("商品名稱")
        p_qty = st.number_input("進貨數量", min_value=1, value=10)
        p_price = st.number_input("單價", min_value=0, value=100)
        submitted = st.form_submit_button("確認進貨")
        
        if submitted:
            if p_name:
                with st.spinner("正在寫入 Google Sheets..."):
                    add_product(p_name, p_qty, p_price)
            else:
                st.warning("請輸入商品名稱")

with tab3:
    st.header("商品銷貨登記")
    df = get_inventory_df()
    if not df.empty:
        product_list = df['商品名稱'].tolist()
        with st.form("sell_form"):
            s_name = st.selectbox("選擇商品", product_list)
            s_qty = st.number_input("銷售數量", min_value=1, value=1)
            submitted_sell = st.form_submit_button("確認銷貨")
            
            if submitted_sell:
                with st.spinner("正在更新庫存..."):
                    sell_product(s_name, s_qty)
    else:
        st.warning("目前無庫存可供銷售。")
