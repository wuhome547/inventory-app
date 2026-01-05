import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import requests
import base64
import re

# --- 設定區 ---
SPREADSHEET_NAME = "inventory_system"
IMGBB_API_KEY = "請將您的 ImgBB API Key 貼在這裡" 
CATEGORY_SEPARATOR = " > " # 重要：這是層級分隔符號

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

def get_worksheet(sheet_name="sheet1"):
    client = get_gspread_client()
    if not client: return None
    try:
        if sheet_name == "sheet1":
            return client.open(SPREADSHEET_NAME).sheet1
        else:
            return client.open(SPREADSHEET_NAME).worksheet(sheet_name)
    except gspread.exceptions.WorksheetNotFound:
        if sheet_name == "vendors":
            try:
                sh = client.open(SPREADSHEET_NAME)
                new_ws = sh.add_worksheet(title="vendors", rows="100", cols="10")
                new_ws.append_row(["廠商名稱", "聯絡人", "電話", "地址", "備註"])
                st.toast("已自動建立 'vendors' 分頁！")
                return new_ws
            except: return None
        return None
    except Exception:
        st.cache_resource.clear()
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

# --- 核心功能 ---

def get_inventory_df():
    sheet = get_worksheet("sheet1")
    if sheet:
        data = sheet.get_all_records()
        df = pd.DataFrame(data)
        
        # 🛡️ 強力清洗：先全部轉字串，避免數字型態干擾
        for col in df.columns:
            df[col] = df[col].astype(str).str.strip()
            
        # 確保必要欄位存在
        if '圖片連結' not in df.columns: df['圖片連結'] = ""
        if '備註' not in df.columns: df['備註'] = ""
        if '分類' not in df.columns: df['分類'] = "未分類"
        if '廠商' not in df.columns: df['廠商'] = ""
        
        # 標準化分類格式
        df['分類'] = df['分類'].replace(r'\s*>\s*', CATEGORY_SEPARATOR, regex=True)
        
        # 處理空值
        df['分類'] = df['分類'].replace(['', 'nan', 'None'], '未分類')
        df['廠商'] = df['廠商'].replace(['nan', 'None'], '')
        
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
    except: return None

def sync_vendor_if_new(vendor_name):
    if not vendor_name: return
    v_name = str(vendor_name).strip()
    if not v_name: return
    try:
        ws = get_worksheet("vendors")
        if not ws: return
        existing_vendors = ws.col_values(1)
        if v_name not in existing_vendors:
            ws.append_row([v_name, "", "", "", "由系統自動同步新增"])
            st.toast(f"✅ 已將 '{v_name}' 自動加入廠商通訊錄！")
    except: pass

def add_product(name, quantity, price, image_urls, remarks, category, supplier):
    sheet = get_worksheet("sheet1")
    if not sheet: return
    name_str = str(name).strip()
    
    cat_str = str(category).strip()
    cat_str = re.sub(r'\s*>\s*', CATEGORY_SEPARATOR, cat_str)
    if not cat_str: cat_str = "未分類"
    
    supp_str = str(supplier).strip()
    sync_vendor_if_new(supp_str)
    
    if isinstance(image_urls, list): final_url_str = ",".join(image_urls)
    else: final_url_str = str(image_urls).strip()
    if len(final_url_str) > 4000: st.error("❌ 網址太長"); return

    cell = find_product_cell(sheet, name_str)
    if cell:
        sheet.update_cell(cell.row, 2, int(sheet.cell(cell.row, 2).value) + quantity)
        sheet.update_cell(cell.row, 3, price)
        if final_url_str: sheet.update_cell(cell.row, 4, final_url_str)
        if remarks: sheet.update_cell(cell.row, 5, remarks)
        sheet.update_cell(cell.row, 6, cat_str)
        sheet.update_cell(cell.row, 7, supp_str)
        st.success(f"✅ 更新 '{name_str}'")
    else:
        sheet.append_row([name_str, quantity, price, final_url_str, remarks, cat_str, supp_str])
        st.success(f"🆕 新增 '{name_str}'")

def sell_product(name, quantity):
    sheet = get_worksheet("sheet1")
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
    sheet = get_worksheet("sheet1")
    if not sheet: return
    cell = find_product_cell(sheet, name)
    if cell:
        sheet.delete_rows(cell.row)
        st.success(f"🗑️ 已刪除")
    else:
        st.error(f"❌ 找不到商品")

def update_product_info(old_name, new_name, new_qty, new_price, new_url_str, new_remarks, new_cat, new_supp):
    sheet = get_worksheet("sheet1")
    if not sheet: return
    clean_url_str = str(new_url_str).strip()
    if len(clean_url_str) > 4000: st.error("❌ 連結太長"); return
    
    cat_clean = re.sub(r'\s*>\s*', CATEGORY_SEPARATOR, str(new_cat).strip())
    
    sync_vendor_if_new(new_supp)
    cell = find_product_cell(sheet, old_name)
    if cell:
        sheet.update_cell(cell.row, 1, new_name)
        sheet.update_cell(cell.row, 2, new_qty)
        sheet.update_cell(cell.row, 3, new_price)
        sheet.update_cell(cell.row, 4, clean_url_str)
        sheet.update_cell(cell.row, 5, new_remarks)
        sheet.update_cell(cell.row, 6, cat_clean)
        sheet.update_cell(cell.row, 7, new_supp)
        st.success(f"✅ 更新成功！")
    else:
        st.error(f"❌ 找不到商品")

def get_vendors_df():
    sheet = get_worksheet("vendors")
    if sheet: return pd.DataFrame(sheet.get_all_records())
    return pd.DataFrame()

def add_vendor(name, contact, phone, address, remarks):
    sheet = get_worksheet("vendors")
    if not sheet: return
    name_str = str(name).strip()
    try:
        sheet.append_row([name_str, contact, phone, address, remarks])
        st.success(f"🏭 已成功新增廠商：'{name_str}'")
    except Exception as e:
        st.error(f"新增失敗: {e}")

def delete_vendor(name):
    sheet = get_worksheet("vendors")
    if not sheet: return
    target = str(name).strip()
    try:
        vals = sheet.col_values(1)
        if target in vals:
            sheet.delete_rows(vals.index(target)+1)
            st.success("已刪除")
    except: st.error("刪除失敗")

def update_vendor(old_name, new_contact, new_phone, new_addr, new_rem):
    sheet = get_worksheet("vendors")
    if not sheet: return
    target = str(old_name).strip()
    try:
        vals = sheet.col_values(1)
        if target in vals:
            row_idx = vals.index(target) + 1
            sheet.update_cell(row_idx, 2, new_contact)
            sheet.update_cell(row_idx, 3, new_phone)
            sheet.update_cell(row_idx, 4, new_addr)
            sheet.update_cell(row_idx, 5, new_rem)
            st.success(f"✅ 廠商 '{target}' 更新成功")
        else:
            st.error("❌ 找不到該廠商")
    except Exception as e:
        st.error(f"更新失敗: {e}")

# --- 介面設計 ---
st.set_page_config(page_title="雲端進銷存", layout="wide")

if "is_admin" not in st.session_state: st.session_state["is_admin"] = False
if "low_stock_limit" not in st.session_state: st.session_state["low_stock_limit"] = 1

with st.sidebar:
    st.header("👤 用戶登入")
    if not st.session_state["is_admin"]:
        st.text_input("輸入管理員密碼", type="password", key="password_input", on_change=check_password)
        st.info("💡 未登入僅能瀏覽")
    else:
        st.success("✅ 已登入")
        st.divider()
        st.subheader("⚙️ 系統設定")
        st.session_state["low_stock_limit"] = st.slider(
            "🔴 低庫存警告門檻", 1, 100, st.session_state["low_stock_limit"]
        )
        st.caption("低於此數值將顯示紅色警告")
        st.divider()
        if st.button("登出"): logout()

st.title("☁️ 視覺化進銷存系統")

tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs(["🖼️ 庫存圖牆", "➕ 進貨 (限)", "➖ 銷貨 (限)", "❌ 刪除 (限)", "✏️ 編輯 (限)", "🏭 廠商名錄 (限)"])

# Tab 1: 庫存圖牆
with tab1:
    st.header("庫存總覽")
    df = get_inventory_df()
    
    if not df.empty:
        total_items = len(df)
        total_qty = pd.to_numeric(df['數量'], errors='coerce').fillna(0).astype(int).sum()
        total_value = (pd.to_numeric(df['數量'], errors='coerce').fillna(0) * pd.to_numeric(df['單價'], errors='coerce').fillna(0)).sum()
        limit = st.session_state["low_stock_limit"]
        low_stock_df = df[pd.to_numeric(df['數量'], errors='coerce').fillna(0) < limit]
        
        m1, m2, m3 = st.columns(3)
        m1.metric("📦 商品總數", f"{total_items} 款", f"庫存 {total_qty}")
        m2.metric("💰 總市值", f"${total_value:,.0f}")
        m3.metric(f"⚠️ 缺貨 (<{limit})", f"{len(low_stock_df)} 款", delta_color="inverse")
        if not low_stock_df.empty:
            with st.expander(f"🚨 查看 {len(low_stock_df)} 款缺貨商品"):
                st.dataframe(low_stock_df[['商品名稱', '數量', '分類', '廠商']], hide_index=True)
        
        st.divider()

        c_nav, c_search, c_refresh = st.columns([3, 2, 1])
        
        with c_nav:
            # 🛡️ Token-based 無限層級篩選 (加強版)
            subset_cats = sorted(df['分類'].unique().tolist())
            selected_path = []
            level = 0
            
            while True:
                # 找出目前層級可用的 Token
                candidates = set()
                for c in subset_cats:
                    parts = str(c).split(CATEGORY_SEPARATOR)
                    if len(parts) > level:
                        candidates.add(parts[level].strip()) # strip 很重要
                
                if not candidates: break
                
                unique_candidates = sorted(list(candidates))
                
                options = ["(全部顯示)"] + unique_candidates
                default_idx = 0
                if level == 0 and "未分類" in options: default_idx = options.index("未分類")
                
                label = "📂 選擇主分類" if level == 0 else f"📂 第 {level+1} 層子分類"
                selection = st.selectbox(label, options, index=default_idx, key=f"cat_lvl_{level}")
                
                if selection == "(全部顯示)":
                    break
                else:
                    selected_path.append(selection)
                    # 過濾 subset，讓下一圈只處理符合的商品
                    new_subset = []
                    for c in subset_cats:
                        parts = str(c).split(CATEGORY_SEPARATOR)
                        if len(parts) > level and parts[level].strip() == selection:
                            new_subset.append(c)
                    subset_cats = new_subset
                    level += 1

        with c_search:
            search_query = st.text_input("🔍 關鍵字搜尋", placeholder="名稱、分類或廠商...")
            
        with c_refresh:
            st.write(""); st.write("")
            if st.button("🔄 重新整理"): st.rerun()

        df_display = df.copy()
        
        if selected_path:
            # 組合目標路徑
            target_path_str = CATEGORY_SEPARATOR.join(selected_path)
            mask_cat = (
                (df_display['分類'] == target_path_str) | 
                (df_display['分類'].str.startswith(target_path_str + CATEGORY_SEPARATOR))
            )
            df_display = df_display[mask_cat]
        
        if search_query:
            mask = (
                df_display['商品名稱'].str.contains(search_query, case=False) | 
                df_display['廠商'].str.contains(search_query, case=False) |
                df_display['分類'].str.contains(search_query, case=False)
            )
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
                    "廠商": st.column_config.TextColumn("廠商", width="medium"),
                    "主圖": st.column_config.ImageColumn("圖片", width="small"),
                    "單價": st.column_config.NumberColumn(format="$%d"),
                    "備註": st.column_config.TextColumn("備註", width="medium"),
                },
                column_order=["分類", "商品名稱", "廠商", "主圖", "數量", "單價"],
                use_container_width=True,
                hide_index=True
            )
            
            st.divider()
            
            c_sel, c_img = st.columns([1, 2])
            with c_sel:
                unique_products = df_display['商品名稱'].unique().tolist()
                sel_prod = st.selectbox("查看詳情", unique_products, key="t1_sel")
                p_data = df[df['商品名稱'] == sel_prod].iloc[-1]
                
                st.info(f"""
                **分類**: {p_data['分類']}
                **廠商**: {p_data['廠商']}
                **庫存**: {p_data['數量']}
                **單價**: ${p_data['單價']}
                """)
                
            with c_img:
                raw_urls = str(p_data.get('圖片連結', '')).strip()
                if raw_urls:
                    urls = [u.strip() for u in raw_urls.split(',') if u.strip()]
                    if urls: st.image(urls, width=150)
        else:
            st.warning("沒有符合的商品。")
    else:
        st.info("尚無資料")

# Tab 2: 進貨
with tab2:
    st.header("商品進貨")
    if not st.session_state["is_admin"]:
        show_login_block()
    else:
        df = get_inventory_df()
        existing_cats = sorted(df['分類'].unique().tolist()) if not df.empty else []
        if "未分類" not in existing_cats: existing_cats.insert(0, "未分類")
        
        vendors_df = get_vendors_df()
        existing_vendors = sorted(vendors_df['廠商名稱'].unique().tolist()) if not vendors_df.empty else []

        with st.form("add_form"):
            st.write("📂 **分類設定**")
            c_cat1, c_cat2 = st.columns([1, 1])
            with c_cat1:
                sel_cat_parent = st.selectbox("選擇現有分類 (父資料夾)", ["(無 / 建立新根目錄)"] + existing_cats)
            with c_cat2:
                new_sub_cat = st.text_input(
                    "建立新分類 / 子分類", 
                    placeholder="例如：鞋子 > 男鞋 > 皮鞋",
                    help="💡 萬能欄位：\n1. 輸入「鞋子」建立新根目錄\n2. 輸入「鞋子 > 男鞋」建立多層目錄\n3. 若左側已選分類，這裡輸入的名稱會自動變成子分類。"
                )

            st.write("📦 **基本資料**")
            p_name = st.text_input("商品名稱 (ID) - 必填")
            
            st.write("🏭 **廠商設定**")
            vendor_options = ["(無 / 輸入新廠商)"] + existing_vendors
            c_v1, c_v2 = st.columns([1, 1])
            with c_v1:
                sel_vendor = st.selectbox("選擇現有廠商", vendor_options)
            with c_v2:
                new_vendor = st.text_input("或輸入新廠商", placeholder="填寫此欄優先使用")
            
            c1, c2 = st.columns(2)
            p_qty = c1.number_input("數量", 1, value=10)
            p_price = c2.number_input("單價", 0, value=100)
            p_remarks = st.text_area("備註")
            
            st.write("📸 **圖片**")
            p_files = st.file_uploader("上傳 (可多選)", type=['png','jpg','jpeg'], accept_multiple_files=True)
            p_url = st.text_input("或貼上連結 (逗號隔開)")

            if st.form_submit_button("確認進貨", type="primary"):
                if p_name:
                    clean_input = new_sub_cat.strip()
                    if sel_cat_parent == "(無 / 建立新根目錄)":
                        final_cat = clean_input if clean_input else "未分類"
                    else:
                        final_cat = f"{sel_cat_parent}{CATEGORY_SEPARATOR}{clean_input}" if clean_input else sel_cat_parent
                    
                    final_cat = re.sub(r'\s*>\s*', ' > ', final_cat)
                    
                    final_supp = ""
                    if new_vendor.strip(): final_supp = new_vendor.strip()
                    elif sel_vendor != "(無 / 輸入新廠商)": final_supp = sel_vendor

                    urls = []
                    if p_url: urls.extend([u.strip() for u in p_url.split(',') if u.strip()])
                    if p_files:
                        with st.spinner("上傳中..."):
                            for f in p_files:
                                u = upload_image_to_imgbb(f)
                                if u: urls.append(u)
                    
                    with st.spinner("寫入資料庫..."):
                        add_product(p_name, p_qty, p_price, urls, p_remarks, final_cat, final_supp)
                else:
                    st.warning("請輸入名稱")

# Tab 3: 銷貨
with tab3:
    st.header("商品銷貨")
    if not st.session_state["is_admin"]:
        show_login_block()
    else:
        df = get_inventory_df()
        if not df.empty:
            all_cats = ["全部"] + sorted(df['分類'].unique().tolist())
            filter_cat = st.selectbox("先選擇分類 (可加速尋找)", all_cats, key="sell_filter")
            
            if filter_cat != "全部": filtered_df = df[df['分類'].str.startswith(filter_cat)]
            else: filtered_df = df
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

# Tab 4: 刪除
with tab4:
    st.header("刪除商品")
    if not st.session_state["is_admin"]:
        show_login_block()
    else:
        df = get_inventory_df()
        if not df.empty:
            if "del_mode" not in st.session_state: st.session_state["del_mode"] = False
            all_cats = ["全部"] + sorted(df['分類'].unique().tolist())
            filter_cat = st.selectbox("篩選分類", all_cats, key="del_filter", disabled=st.session_state["del_mode"])
            
            if filter_cat != "全部": filtered_df = df[df['分類'].str.startswith(filter_cat)]
            else: filtered_df = df
            prod_list = filtered_df['商品名稱'].unique().tolist()

            c1, c2 = st.columns([3, 1])
            with c1:
                d_name = st.selectbox("選擇商品", prod_list, disabled=st.session_state["del_mode"], key="del_sel")
            with c2:
                st.write(""); st.write("")
                if st.button("🗑️ 刪除", type="primary", disabled=st.session_state["del_mode"]):
                    st.session_state["del_mode"] = True
                    st.session_state["del_target"] = d_name
     
