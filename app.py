import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import requests
import base64

# --- 設定區 ---
SPREADSHEET_NAME = "inventory_system"
IMGBB_API_KEY = "a9e1ead23aa6fb34478cf7a16adaf34b" 

# --- 連線設定 (快取版) ---
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

# --- 核心功能 ---
def get_inventory_df():
    sheet = get_worksheet()
    if sheet:
        data = sheet.get_all_records()
        df = pd.DataFrame(data)
        if '圖片連結' not in df.columns: df['圖片連結'] = ""
        if '備註' not in df.columns: df['備註'] = ""
        return df
    return pd.DataFrame()

def add_product(name, quantity, price, image_url, remarks):
    sheet = get_worksheet()
    if not sheet: return
    clean_url = str(image_url).strip()
    if len(clean_url) > 2000: st.error("❌ 網址太長"); return
    cell_list = sheet.findall(name)
    if cell_list:
        cell = cell_list[0]
        sheet.update_cell(cell.row, 2, int(sheet.cell(cell.row, 2).value) + quantity)
        sheet.update_cell(cell.row, 3, price)
        if clean_url: sheet.update_cell(cell.row, 4, clean_url)
        if remarks: sheet.update_cell(cell.row, 5, remarks)
        st.success(f"✅ 更新 '{name}'")
    else:
        sheet.append_row([name, quantity, price, clean_url, remarks])
        st.success(f"🆕 新增 '{name}'")

def sell_product(name, quantity):
    sheet = get_worksheet()
    if not sheet: return
    cell_list = sheet.findall(name)
    if cell_list:
        cell = cell_list[0]
        curr = int(sheet.cell(cell.row, 2).value)
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
    cell_list = sheet.findall(name)
    if cell_list:
        sheet.delete_rows(cell_list[0].row)
        st.success(f"🗑️ 已刪除")

def update_product_info(name, new_qty, new_price, new_url, new_remarks):
    sheet = get_worksheet()
    if not sheet: return
    clean_url = str(new_url).strip()
    if len(clean_url) > 2000: st.error("❌ 連結太長"); return
    cell_list = sheet.findall(name)
    if cell_list:
        cell = cell_list[0]
        sheet.update_cell(cell.row, 2, new_qty)
        sheet.update_cell(cell.row, 3, new_price)
        sheet.update_cell(cell.row, 4, clean_url)
        sheet.update_cell(cell.row, 5, new_remarks)
        st.success(f"✅ 已更新資料")

# --- 介面設計 ---
st.set_page_config(page_title="雲端進銷存", layout="wide")
st.title("☁️ 視覺化進銷存系統")

tab1, tab2, tab3, tab4, tab5 = st.tabs(["🖼️ 庫存圖牆", "➕ 進貨", "➖ 銷貨", "❌ 刪除", "✏️ 編輯資料"])

# Tab 1: 庫存圖牆 (加入搜尋功能)
with tab1:
    st.header("庫存總覽")
    df = get_inventory_df()
    
    if not df.empty:
        # --- 🔍 搜尋區塊 ---
        col_search, col_refresh = st.columns([4, 1])
        with col_search:
            search_query = st.text_input("🔍 搜尋商品 (輸入名稱或備註關鍵字)", "", placeholder="例如：紅色、iPhone...")
        with col_refresh:
            st.write("") # 排版用
            st.write("") 
            if st.button("🔄 重新整理", key="refresh_tab1"):
                st.rerun()

        # 篩選資料邏輯
        if search_query:
            # 不分大小寫搜尋 (名稱 或 備註)
            mask = df['商品名稱'].astype(str).str.contains(search_query, case=False) | \
                   df['備註'].astype(str).str.contains(search_query, case=False)
            df_display = df[mask]
        else:
            df_display = df

        # --- 顯示區塊 ---
        if not df_display.empty:
            st.subheader(f"📋 庫存清單 (共 {len(df_display)} 筆)")
            
            # 資料處理
            df_display['圖片連結'] = df_display['圖片連結'].astype(str).str.strip().replace('nan', '')
            df_display['備註'] = df_display['備註'].astype(str).replace('nan', '')

            st.dataframe(
                df_display,
                column_config={
                    "圖片連結": st.column_config.ImageColumn("圖片", width="small"),
                    "單價": st.column_config.NumberColumn(format="$%d"),
                    "備註": st.column_config.TextColumn("備註", width="medium"),
                },
                use_container_width=True,
                hide_index=True
            )
            
            st.divider()
            
            # 詳細資料區 (只顯示篩選後的結果)
            col_sel, col_img = st.columns([1, 2])
            with col_sel:
                selected_product = st.selectbox("選擇商品查看詳情", df_display['商品名稱'].tolist(), key="tab1_select")
                
                # 從原始 df 抓資料比較安全
                product_data = df[df['商品名稱'] == selected_product].iloc[0]
                
                st.info(f"**庫存**: {product_data['數量']} | **單價**: ${product_data['單價']}")
                st.text_area("備註內容", value=product_data.get('備註',''), disabled=True, key="tab1_remark")
                
            with col_img:
                img_url = str(product_data.get('圖片連結', '')).strip()
                if img_url and len(img_url)>10:
                    try: st.image(img_url, width=400)
                    except: st.error("圖片載入失敗")
        else:
            st.warning(f"找不到符合「{search_query}」的商品。")
            
    else:
        st.info("目前無資料")
        if st.button("🔄 重新整理", key="refresh_empty"): st.rerun()

# Tab 2: 進貨
with tab2:
    st.header("商品進貨")
    with st.form("add_form"):
        p_name = st.text_input("商品名稱")
        c1, c2 = st.columns(2)
        p_qty = c1.number_input("數量", 1, value=10)
        p_price = c2.number_input("單價", 0, value=100)
        p_remarks = st.text_area("備註 (選填)")
        
        st.write("📸 圖片設定")
        p_url = st.text_input("方式 A：連結", placeholder="https://...")
        st.caption("--- 或 ---")
        p_file = st.file_uploader("方式 B：上傳", type=['png','jpg'])

        if st.form_submit_button("確認進貨", type="primary"):
            if p_name:
                final = p_url
                if p_file:
                    with st.spinner("上傳中..."):
                        u = upload_image_to_imgbb(p_file)
                        if u: final = u
                with st.spinner("寫入中..."):
                    add_product(p_name, p_qty, p_price, final, p_remarks)
            else:
                st.warning("請輸入名稱")

# Tab 3: 銷貨
with tab3:
    st.header("商品銷貨")
    df = get_inventory_df()
    if not df.empty:
        with st.form("sell_form"):
            s_name = st.selectbox("選擇商品", df['商品名稱'].tolist(), key="sell_select")
            s_qty = st.number_input("數量", 1)
            if st.form_submit_button("銷貨"): sell_product(s_name, s_qty)
    else:
        st.warning("無庫存")

# Tab 4: 刪除
with tab4:
    st.header("刪除商品")
    df = get_inventory_df()
    if not df.empty:
        if "del_mode" not in st.session_state: st.session_state["del_mode"] = False
        
        c1, c2 = st.columns([3, 1])
        with c1:
            d_name = st.selectbox("選擇刪除對象", df['商品名稱'].tolist(), disabled=st.session_state["del_mode"], key="del_select")
        with c2:
            st.write(""); st.write("")
            if st.button("🗑️ 刪除", type="primary", disabled=st.session_state["del_mode"], key="del_btn_init"):
                st.session_state["del_mode"] = True
                st.session_state["del_target"] = d_name
                st.rerun()

        if st.session_state["del_mode"]:
            st.warning(f"確認刪除 **{st.session_state['del_target']}**？")
            k1, k2 = st.columns(2)
            with k1:
                if st.button("✅ 確認", use_container_width=True, key="del_confirm"):
                    delete_product(st.session_state["del_target"])
                    st.session_state["del_mode"] = False
                    st.rerun()
            with k2:
                if st.button("❌ 取消", use_container_width=True, key="del_cancel"):
                    st.session_state["del_mode"] = False
                    st.rerun()

# Tab 5: 編輯
with tab5:
    st.header("✏️ 編輯資料")
    df = get_inventory_df()
    if not df.empty:
        edit_name = st.selectbox("選擇編輯對象", df['商品名稱'].tolist(), key="edit_select")
        curr = df[df['商品名稱'] == edit_name].iloc[0]
        
        with st.form("edit_form"):
            k1, k2 = st.columns(2)
            n_qty = k1.number_input("庫存", 0, value=int(curr['數量']))
            n_price = k2.number_input("單價", 0, value=int(curr['單價']))
            n_rem = st.text_area("備註", value=str(curr.get('備註','')))
            
            st.subheader("圖片")
            c_url = str(curr.get('圖片連結','')).strip()
            if c_url: st.image(c_url, width=150)
            
            n_url = st.text_input("連結", value=c_url)
            st.caption("--- 或 ---")
            n_file = st.file_uploader("上傳新圖", type=['png','jpg'], key="edit_file")
            
            if st.form_submit_button("儲存", type="primary"):
                fin = n_url
                if n_file:
                    with st.spinner("上傳..."):
                        u = upload_image_to_imgbb(n_file)
                        if u: fin = u
                with st.spinner("更新..."):
                    update_product_info(edit_name, n_qty, n_price, fin, n_rem)
                    st.rerun()
    else:
        st.info("無資料")
