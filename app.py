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
        # 本地測試用
        # creds = ServiceAccountCredentials.from_json_keyfile_name('credentials.json', scope)
        st.error("❌ 無法讀取憑證，請檢查 secrets 設定")
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
    如果是一般圖片網址則直接回傳。
    """
    if not url: return ""
    url = str(url).strip()
    
    # 處理 Google Drive 連結
    if "drive.google.com" in url and "/d/" in url:
        # 提取 file ID
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
        # 確保有圖片連結欄位，如果沒有就補上空字串
        if '圖片連結' not in df.columns:
            df['圖片連結'] = ""
        return df
    return pd.DataFrame()

def add_product(name, quantity, price, image_url):
    sheet = get_worksheet()
    if not sheet: return

    # 處理圖片連結 (確保格式正確)
    final_img_url = process_image_url(image_url)

    cell_list = sheet.findall(name)
    
    if cell_list:
        # 更新
        cell = cell_list[0]
        current_qty = int(sheet.cell(cell.row, 2).value)
        new_qty = current_qty + quantity
        
        sheet.update_cell(cell.row, 2, new_qty)
        sheet.update_cell(cell.row, 3, price)
        sheet.update_cell(cell.row, 4, final_img_url) # 更新圖片欄位 (第4欄)
        
        st.success(f"✅ 已更新 '{name}'。")
    else:
        # 新增 (注意順序：名稱, 數量, 單價, 圖片連結)
        sheet.append_row([name, quantity, price, final_img_url])
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

# --- 網頁介面設計 ---

st.set_page_config(page_title="雲端進銷存(含圖)", layout="wide") # 改成 wide 模式以容納圖片
st.title("☁️ 視覺化進銷存系統")

tab1, tab2, tab3, tab4 = st.tabs(["🖼️ 庫存圖牆", "➕ 進貨", "➖ 銷貨", "❌ 刪除"])

with tab1:
    st.header("庫存總覽")
    df = get_inventory_df()
    
    if not df.empty:
        # 1. 顯示帶有縮圖的表格
        st.subheader("📋 庫存清單")
        
        # 設定欄位顯示格式
        st.dataframe(
            df,
            column_config={
                "圖片連結": st.column_config.ImageColumn(
                    "商品圖片", help="商品預覽圖", width="small"
                ),
                "單價": st.column_config.NumberColumn(format="$%d"),
            },
            use_container_width=True,
            hide_index=True
        )

        # 2. 點擊查看大圖區域
        st.divider()
        st.subheader("🔍 查看商品大圖")
        
        # 建立兩欄佈局：左邊選單，右邊秀圖
        col_sel, col_img = st.columns([1, 2])
        
        with col_sel:
            selected_product = st.selectbox("請選擇要查看的商品：", df['商品名稱'].tolist())
            
            # 找到該商品的詳細資料
            product_data = df[df['商品名稱'] == selected_product].iloc[0]
            st.info(f"**庫存**: {product_data['數量']} | **單價**: ${product_data['單價']}")

        with col_img:
            img_url = product_data.get('圖片連結', '')
            if img_url:
                st.image(img_url, caption=selected_product, width=400)
            else:
                st.write("🖼️ 此商品尚未設定圖片")
                
    else:
        st.info("目前沒有資料。")
    
    if st.button("🔄 重新整理"):
        st.rerun()

with tab2:
    st.header("商品進貨 (含圖片設定)")
    with st.form("add_form"):
        p_name = st.text_input("商品名稱")
        col1, col2 = st.columns(2)
        with col1:
            p_qty = st.number_input("進貨數量", min_value=1, value=10)
        with col2:
            p_price = st.number_input("單價", min_value=0, value=100)
        
        # 新增圖片連結輸入框
        p_img = st.text_input("圖片連結 (支援 Google Drive 分享連結或一般圖片網址)")
        st.caption("💡 提示：若使用 Google Drive，請開啟「任何知道連結的人都能檢視」權限。")
        
        submitted = st.form_submit_button("確認進貨 / 更新")
        
        if submitted:
            if p_name:
                with st.spinner("寫入中..."):
                    add_product(p_name, p_qty, p_price, p_img)
            else:
                st.warning("請輸入名稱")

with tab3:
    st.header("商品銷貨")
    df = get_inventory_df()
    if not df.empty:
        with st.form("sell_form"):
            s_name = st.selectbox("選擇商品", df['商品名稱'].tolist())
            s_qty = st.number_input("銷售數量", min_value=1, value=1)
            if st.form_submit_button("確認銷貨"):
                sell_product(s_name, s_qty)
    else:
        st.warning("無庫存")

with tab4:
    st.header("刪除商品")
    df = get_inventory_df()
    if not df.empty:
        with st.form("delete_form"):
            d_name = st.selectbox("刪除商品", df['商品名稱'].tolist())
            confirm = st.checkbox("確認刪除")
            if st.form_submit_button("執行刪除"):
                if confirm:
                    delete_product(d_name)
                    st.rerun()
                else:
                    st.error("請勾選確認")
