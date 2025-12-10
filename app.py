import streamlit as st
from google.oauth2 import service_account
from googleapiclient.discovery import build

st.set_page_config(page_title="雲端權限檢測器", page_icon="🔍")
st.title("🔍 Google Drive 權限檢測器")

# 1. 讀取並顯示服務帳號資訊
try:
    creds_dict = dict(st.secrets["gcp_service_account"])
    client_email = creds_dict.get('client_email', '無法讀取')
    
    st.info(f"🤖 **機器人 (服務帳號) Email:**\n\n`{client_email}`")
    st.warning("👉 請回到 Google Drive，確認此 Email 是否在資料夾的「共用名單」中，且權限為「編輯者」？")
    
except Exception as e:
    st.error(f"❌ 無法讀取 Secrets，請檢查設定: {e}")
    st.stop()

# 2. 輸入資料夾 ID 進行測試
folder_id = st.text_input("📂 請貼上您的資料夾 ID 進行測試", value="")

if st.button("開始檢測"):
    if not folder_id:
        st.warning("請輸入 ID")
    else:
        try:
            # 建立連線
            creds = service_account.Credentials.from_service_account_info(
                creds_dict, scopes=['https://www.googleapis.com/auth/drive']
            )
            service = build('drive', 'v3', credentials=creds)

            # 嘗試抓取資料夾資訊
            st.write("正在連線到 Google Drive...")
            file = service.files().get(
                fileId=folder_id,
                fields='id, name, mimeType, capabilities, owners'
            ).execute()

            # --- 診斷報告 ---
            st.success(f"✅ 成功找到物件：**{file.get('name')}**")
            
            # 檢查 1: 是不是資料夾？
            mime_type = file.get('mimeType')
            if mime_type != 'application/vnd.google-apps.folder':
                st.error(f"❌ 錯誤：這是一個「檔案」({mime_type})，不是「資料夾」！\n\n機器人無法把圖片塞進另一個檔案裡，請確認您複製的是資料夾的 ID。")
                st.stop()
            else:
                st.write("✅ 格式正確：這是一個資料夾。")

            # 檢查 2: 有沒有寫入權限？
            caps = file.get('capabilities', {})
            can_add = caps.get('canAddChildren', False)
            
            if can_add:
                st.balloons()
                st.success("🎉 **驗證通過！** 機器人擁有此資料夾的寫入權限。")
                st.write("如果現在程式還是不能跑，請確認您的 app.py 是否有儲存並重新部署。")
            else:
                st.error("🚫 **權限不足！**")
                st.markdown(f"""
                機器人看得到這個資料夾，但是**無法上傳檔案**。
                
                **可能原因：**
                1. 您只給了 **「檢視者 (Viewer)」** 權限。
                2. 請將 `{client_email}` 的權限改為 **「編輯者 (Editor)」**。
                """)

        except Exception as e:
            st.error(f"❌ **無法存取資料夾**")
            st.code(str(e))
            st.markdown("""
            **常見原因：**
            1. **ID 錯誤**：ID 通常是一串亂碼，不包含網址。
            2. **完全沒共用**：機器人完全被擋在門外，請確認有將資料夾共用給上面的 Email。
            """)
