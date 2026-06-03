import streamlit as st
import pandas as pd
import io
import json
import requests
import base64

# --- ページ設定 ---
st.set_page_config(page_title="RECEIPT-AI", layout="wide")

# --- 絶対に消えない情報（セッション固定） ---
if "api_key" not in st.session_state: st.session_state["api_key"] = ""
if "model_id" not in st.session_state: st.session_state["model_id"] = "gemini-1.5-flash"

# --- 常駐エリア（何が起きてもここに鎮座する） ---
st.title("RECEIPT-AI: FAST-SCANNER")
with st.sidebar:
    st.subheader("⚙️ 接続設定")
    st.markdown("[APIキーの発行はこちら](https://aistudio.google.com/app/apikey)")
    st.session_state["api_key"] = st.text_input("API Key", type="password", value=st.session_state["api_key"])
    st.session_state["model_id"] = st.text_input("Model ID", value=st.session_state["model_id"])
    st.divider()
    st.caption("※ここにキーとモデル名を入れておけば、画面が更新されても消えません。")

# --- メイン動作エリア ---
uploaded_files = st.file_uploader("Upload Receipts", accept_multiple_files=True)

if st.button("RUN SCAN"):
    if not st.session_state["api_key"] or not uploaded_files:
        st.error("APIキーと画像を確認してください。")
        st.stop()

    all_data = []
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{st.session_state['model_id']}:generateContent"

    for file in uploaded_files:
        try:
            image_b64 = base64.b64encode(file.read()).decode("utf-8")
            payload = {
                "contents": [{"parts": [
                    {"text": "Extract receipt data as JSON."},
                    {"inline_data": {"mime_type": "image/jpeg", "data": image_b64}}
                ]}],
                "generationConfig": {"response_mime_type": "application/json"}
            }

            response = requests.post(url, params={"key": st.session_state["api_key"]}, json=payload)
            
            if response.status_code == 200:
                res = response.json()
                text = res['candidates'][0]['content']['parts'][0]['text']
                data = json.loads(text.replace("```json", "").replace("```", "").strip())
                all_data.extend(data if isinstance(data, list) else [data])
                st.write(f"✅ {file.name}")
            else:
                st.error(f"❌ {file.name}: {response.status_code}")
        except Exception as e:
            st.error(f"❌ {file.name}: {str(e)[:30]}")

    if all_data:
        df = pd.DataFrame(all_data)
        buffer = io.BytesIO()
        df.to_excel(buffer, index=False)
        st.download_button("📥 DOWNLOAD RESULT", buffer.getvalue(), "receipts.xlsx")
