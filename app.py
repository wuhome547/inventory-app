import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials

st.title("🕵️ Google Sheets 連線診斷器")

try:
    # 1. 取得憑證
    creds_dict = dict(st.secrets["gcp_service_account"])
    email = creds_dict.get("client_email", "未知")
    
    st.info(f"🤖 目前使用的機器人 Email:\n\n`{email}`")
    st.write("---")

    # 2. 嘗試連線
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    client = gspread.authorize(creds)
    
    st.write("正在掃描機器人看得到的檔案...")
    
    # 3. 列出所有檔案
    all_sheets = client.openall()
    sheet_names = [s.title for s in all_sheets]
    
    if sheet_names:
        st.success(f"✅ 連線成功！機器人目前看得到 {len(sheet_names)} 個檔案：")
        st.json(sheet_names)
        
        target_name = "inventory_system" # 您的目標檔名
        if target_name in sheet_names:
            st.balloons()
            st.write(f"🎉 恭喜！找到了 `{target_name}`。請切換回原本的程式碼即可。")
        else:
            st.error(f"❌ 找不到 `{target_name}`！")
            st.warning("請確認您的 Google Sheet 名稱是否與程式碼中的 `SPREADSHEET_NAME` 完全一致（包含大小寫）。")
    else:
        st.warning("⚠️ 連線成功，但機器人「看不到任何檔案」。請確認您有將 Google Sheet 共用給上面的 Email。")

except Exception as e:
    st.error(f"❌ 連線發生錯誤 (API Error): {e}")
    st.write("這通常代表 API 未啟用，或 Secrets 設定檔格式有誤。")
