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

# --- 核心功能 (加入分類欄位) ---

def get_inventory_df():
    sheet = get_worksheet()
    if sheet:
        data = sheet.get_all_records()
        df = pd.DataFrame(data)
        
        # 資料清洗
        if '商品名稱' in df.columns: df['商品名稱'] = df['商品名稱'].astype(str).str.strip()
        if '圖片連結' not in df.columns: df['圖片連結'] = ""
        if '備註' not in df.columns: df['備註'] = ""
        if '分類' not in df.columns: df['分類'] = "未分類" # 新增分類欄位防呆
        
        # 處理分類的空白或 NaN
        df['分類'] = df['分類'].astype(str).replace('', '未分類').replace('nan', '未分類')
        
        return df
    return pd.DataFrame()

def find_product_cell(sheet, name):
    target_name = str(name).strip()
    try:
        col_values = sheet.col_values(1)
        str_values = [str(v).strip() for v in col_values]
        if target_name in str_values:
            all_indices = [i for i, x in enumerate(str_values) if x == target_name]
            last_index = all_indices[-1]
            return sheet.cell(last_index + 1, 1)
        return None
    except Exception as e:
        st.error(f"搜尋錯誤: {e}")
        return None

def add_product(name, quantity, price, image_urls, remarks, category):
    sheet = get_worksheet()
    if not sheet: return
    name_str = str(name).strip()
    cat_str = str(category).strip()
    if not cat_str: cat_str = "未分類"
    
    if isinstance(image_urls, list):
        final_url_str = ",".join(image_urls)
    else:
        final_url_str = str(image_urls).strip()

    if len(final_url_str) > 4000: st.error("❌ 網址太長"); return

    cell = find_product_cell(sheet, name_str)
    
    if cell:
        # 更新 (Col 1=名, 2=數, 3=價, 4=圖, 5=備, 6=類)
        sheet.update_cell(cell.row, 2, int(sheet.cell(cell.row, 2).value) + quantity)
        sheet.update_cell(cell.row, 3, price)
        if final_url_str: sheet.update_cell(cell.row, 4, final_url_str)
        if remarks: sheet.update_cell(cell.row, 5, remarks)
        sheet.update_cell(cell.row, 6, cat_str) # 更新分類
        st.success(f"✅ 更新 '{name_str}' (分類: {cat_str})")
    else:
        # 新增
        sheet.append_row([name_str, quantity, price, final_url_str, remarks, cat_str])
        st.success(f"🆕 新增 '{name_str}' (分類: {cat_str})")

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

def update_product_info(name, new_qty, new_price, new_url_str, new_remarks, new_cat):
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
        sheet.update_cell(cell.row, 6, new_cat)
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

# Tab 1: 庫存圖牆 (加入分類篩選)
with tab1:
    st.header("庫存總覽")
    df = get_inventory_df()
    
    if not df.empty:
        # 1. 數據儀表板 (計算全體，不受篩選影響)
        total_items = len(df)
        total_qty = df['數量'].astype(int).sum()
        total_value = (df['數量'].astype(int) * df['單價'].astype(int)).sum()
        low_stock_df = df[df['數量'].astype(int) < 5]
        
        m1, m2, m3 = st.columns(3)
        m1.metric("📦 商品總數", f"{total_items} 款", f"庫存 {total_qty}")
        m2.metric("💰 總市值", f"${total_value:,}")
        m3.metric("⚠️ 缺貨預警", f"{len(low_stock_df)} 款", delta_color="inverse")
        if not low_stock_df.empty:
            with st.expander(f"🚨 查看 {len(low_stock_df)} 款缺貨商品"):
                st.dataframe(low_stock_df[['商品名稱', '數量', '分類']], hide_index=True)
        
        st.divider()

        # 2. 篩選器區域 (分類 + 搜尋)
        c_filter, c_search, c_refresh = st.columns([2, 3, 1])
        
        with c_filter:
            # 取得所有分類
            all_cats = ["全部"] + sorted(df['分類'].unique().tolist())
            selected_cat = st.selectbox("📂 選擇分類篩選", all_cats)
            
        with c_search:
            search_query = st.text_input("🔍 關鍵字搜尋", placeholder="商品名稱...")
            
        with c_refresh:
            st.write(""); st.write("")
            if st.button("🔄 重新整理"): st.rerun()

        # 3. 執行篩選邏輯
        df_display = df.copy()
        
        # 先篩分類
        if selected_cat != "全部":
            df_display = df_display[df_display['分類'] == selected_cat]
            
        # 再篩關鍵字
        if search_query:
            mask = df_display['商品名稱'].str.contains(search_query, case=False)
            df_display = df_display[mask]

        if not df_display.empty:
            st.subheader(f"📋 商品清單 ({len(df_display)} 筆)")
            
            df_display['圖片連結'] = df_display['圖片連結'].astype(str).str.strip().replace('nan', '')
            df_display['主圖'] = df_display['圖片連結'].apply(lambda x: x.split(',')[0] if x else "")
            
            st.dataframe(
                df_display,
                column_config={
                    "商品名稱": st.column_config.TextColumn("商品名稱"),
                    "分類": st.column_config.TextColumn("分類", width="small"),
                    "主圖": st.column_config.ImageColumn("圖片", width="small"),
                    "單價": st.column_config.NumberColumn(format="$%d"),
                    "備註": st.column_config.TextColumn("備註", width="medium"),
                },
                column_order=["分類", "商品名稱", "主圖", "數量", "單價"], # 調整順序，分類放前面
                use_container_width=True,
                hide_index=True
            )
            
            st.divider()
            
            # 詳細資料區
            c_sel, c_img = st.columns([1, 2])
            with c_sel:
                # 選單只顯示「篩選後」的商品，這樣找東西超快
                unique_products = df_display['商品名稱'].unique().tolist()
                sel_prod = st.selectbox("查看詳情", unique_products, key="t1_sel")
                
                # 取最新一筆
                p_data = df[df['商品名稱'] == sel_prod].iloc[-1]
                
                st.info(f"""
                **分類**: {p_data['分類']}
                **庫存**: {p_data['數量']}
                **單價**: ${p_data['單價']}
                """)
                # 這裡不顯示備註(已移除)
                
            with c_img:
                raw_urls = str(p_data.get('圖片連結', '')).strip()
                if raw_urls:
                    urls = [u.strip() for u in raw_urls.split(',') if u.strip()]
                    if urls: st.image(urls, width=150)
        else:
            st.warning("沒有符合的商品。")
    else:
        st.info("尚無資料")

# Tab 2: 進貨 (加入分類選擇)
with tab2:
    st.header("商品進貨")
    if not st.session_state["is_admin"]: show_login_block()

    df = get_inventory_df()
    # 取得現有分類列表，方便使用者選擇
    existing_cats = sorted(df['分類'].unique().tolist()) if not df.empty else []
    if "未分類" not in existing_cats: existing_cats.append("未分類")

    with st.form("add_form"):
        # 分類選擇邏輯
        st.write("📂 **商品分類**")
        cat_mode = st.radio("選擇方式", ["選擇現有分類", "輸入新分類"], horizontal=True, label_visibility="collapsed")
        
        p_cat = "未分類"
        if cat_mode == "選擇現有分類":
            p_cat = st.selectbox("選擇分類", existing_cats)
        else:
            p_cat = st.text_input("輸入新分類名稱", placeholder="例如：鞋子、飾品...")

        st.write("📦 **基本資料**")
        p_name = st.text_input("商品名稱 (ID)")
        c1, c2 = st.columns(2)
        p_qty = c1.number_input("數量", 1, value=10)
        p_price = c2.number_input("單價", 0, value=100)
        p_remarks = st.text_area("備註")
        
        st.write("📸 **圖片**")
        p_files = st.file_uploader("上傳", type=['png','jpg'], accept_multiple_files=True)
        p_url = st.text_input("或貼上連結")

        if st.form_submit_button("確認進貨", type="primary"):
            if p_name:
                # 確保分類有值
                if not p_cat.strip(): p_cat = "未分類"
                
                urls = []
                if p_url: urls.extend([u.strip() for u in p_url.split(',') if u.strip()])
                if p_files:
                    with st.spinner("上傳中..."):
                        for f in p_files:
                            u = upload_image_to_imgbb(f)
                            if u: urls.append(u)
                
                with st.spinner("寫入中..."):
                    add_product(p_name, p_qty, p_price, urls, p_remarks, p_cat)
            else:
                st.warning("請輸入名稱")

# Tab 3: 銷貨 (分類連動)
with tab3:
    st.header("商品銷貨")
    if not st.session_state["is_admin"]: show_login_block()
    df = get_inventory_df()
    
    if not df.empty:
        # 連動篩選機制
        all_cats = ["全部"] + sorted(df['分類'].unique().tolist())
        filter_cat = st.selectbox("先選擇分類 (可加速尋找)", all_cats, key="sell_filter")
        
        # 根據分類過濾商品列表
        if filter_cat != "全部":
            filtered_df = df[df['分類'] == filter_cat]
        else:
            filtered_df = df
            
        prod_list = filtered_df['商品名稱'].unique().tolist()
        
        if prod_list:
            with st.form("sell_form"):
                s_name = st.selectbox("選擇商品", prod_list)
                s_qty = st.number_input("數量", 1)
                if st.form_submit_button("確認銷貨", type="primary"):
                    sell_product(s_name, s_qty)
        else:
            st.warning("此分類下無商品")
    else:
        st.warning("無庫存")

# Tab 4: 刪除 (分類連動)
with tab4:
    st.header("刪除商品")
    if not st.session_state["is_admin"]: show_login_block()
    df = get_inventory_df()
    
    if not df.empty:
        if "del_mode" not in st.session_state: st.session_state["del_mode"] = False
        
        # 連動篩選
        all_cats = ["全部"] + sorted(df['分類'].unique().tolist())
        filter_cat = st.selectbox("篩選分類", all_cats, key="del_filter", disabled=st.session_state["del_mode"])
        
        if filter_cat != "全部":
            filtered_df = df[df['分類'] == filter_cat]
        else:
            filtered_df = df
            
        prod_list = filtered_df['商品名稱'].unique().tolist()

        c1, c2 = st.columns([3, 1])
        with c1:
            d_name = st.selectbox("選擇商品", prod_list, disabled=st.session_state["del_mode"], key="del_sel")
        with c2:
            st.write(""); st.write("")
            if st.button("🗑️ 刪除", type="primary", disabled=st.session_state["del_mode"]):
                st.session_state["del_mode"] = True
                st.session_state["del_target"] = d_name
                st.rerun()
        
        if st.session_state["del_mode"]:
            st.warning(f"確認刪除 **{st.session_state['del_target']}**？")
            k1, k2 = st.columns(2)
            with k1:
                if st.button("✅ 確認"):
                    delete_product(st.session_state["del_target"])
                    st.session_state["del_mode"] = False
                    st.rerun()
            with k2:
                if st.button("❌ 取消"):
                    st.session_state["del_mode"] = False
                    st.rerun()

# Tab 5: 編輯 (分類也可編輯)
with tab5:
    st.header("✏️ 編輯資料")
    if not st.session_state["is_admin"]: show_login_block()
    df = get_inventory_df()
    
    if not df.empty:
        # 連動篩選
        all_cats = ["全部"] + sorted(df['分類'].unique().tolist())
        filter_cat = st.selectbox("篩選分類", all_cats, key="edit_filter")
        
        if filter_cat != "全部":
            filtered_df = df[df['分類'] == filter_cat]
        else:
            filtered_df = df
        
        prod_list = filtered_df['商品名稱'].unique().tolist()
        
        if prod_list:
            edit_name = st.selectbox("選擇商品", prod_list, key="edit_sel")
            curr = df[df['商品名稱'] == str(edit_name)].iloc[-1]
            
            st.divider()
            with st.form("edit_form"):
                st.write("📂 **分類設定**")
                # 讓使用者可以換分類
                curr_cat = str(curr.get('分類', '未分類'))
                # 這裡簡單一點，直接用文字框修改，或者選現有的
                # 為了彈性，我們提供一個文字框，預設填入目前的分類
                n_cat = st.text_input("分類名稱", value=curr_cat)
                
                st.write("📦 **基本資料**")
                c1, c2 = st.columns(2)
                n_qty = c1.number_input("庫存", 0, value=int(curr['數量']))
                n_price = c2.number_input("單價", 0, value=int(curr['單價']))
                n_rem = st.text_area("備註", value=str(curr.get('備註','')))
                
                st.write("📸 **圖片管理**")
                raw_urls = str(curr.get('圖片連結','')).strip()
                if raw_urls:
                    st.image([u.strip() for u in raw_urls.split(',') if u.strip()], width=100)
                n_url_str = st.text_area("圖片連結 (逗號分隔)", value=raw_urls)
                n_files = st.file_uploader("新增圖片", type=['png','jpg'], accept_multiple_files=True)
                
                if st.form_submit_button("儲存變更", type="primary"):
                    final_str = n_url_str
                    if n_files:
                        new_urls = []
                        with st.spinner("上傳中..."):
                            for f in n_files:
                                u = upload_image_to_imgbb(f)
                                if u: new_urls.append(u)
                        if new_urls:
                            if final_str.strip(): final_str += "," + ",".join(new_urls)
                            else: final_str = ",".join(new_urls)
                    
                    with st.spinner("更新中..."):
                        update_product_info(edit_name, n_qty, n_price, final_str, n_rem, n_cat)
                        st.rerun()
    else:
        st.info("無資料")
