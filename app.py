import streamlit as st
import pandas as pd
import io
import json
import requests
import base64

# --- ページ設定 ---
st.set_page_config(page_title="最新AI対応 レシート仕分けエンジン", layout="wide")

# セッション管理（絶対に消えない設計）
if "api_key" not in st.session_state: st.session_state["api_key"] = ""
if "model_name" not in st.session_state: st.session_state["model_name"] = "gemini-3.5-flash"

st.title("🚀 最新AI対応 レシート仕分けエンジン")

# --- 設定エリア ---
col1, col2 = st.columns(2)
with col1:
    api_key = st.text_input("API Key", type="password", value=st.session_state["api_key"])
with col2:
    model_name = st.text_input("Model ID (最新を確認: gemini-3.5-flash 等)", value=st.session_state["model_name"])

st.session_state["api_key"] = api_key
st.session_state["model_name"] = model_name

uploaded_files = st.file_uploader("レシート画像をアップロード", accept_multiple_files=True)

if st.button("Start Processing"):
    if not api_key or not uploaded_files:
        st.error("APIキーとファイルをセットしてくれ")
        st.stop()

    all_data = []
    # 正しいエンドポイント構成
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent"
    
    for file in uploaded_files:
        try:
            image_b64 = base64.b64encode(file.read()).decode("utf-8")
            payload = {
                "contents": [{"parts": [
                    {"text": "Extract receipt data into JSON."},
                    {"inline_data": {"mime_type": "image/jpeg", "data": image_b64}}
                ]}],
                "generationConfig": {"response_mime_type": "application/json"}
            }

            response = requests.post(url, params={"key": api_key}, json=payload)
            
            if response.status_code == 200:
                res_data = response.json()
                text = res_data['candidates'][0]['content']['parts'][0]['text']
                clean_text = text.replace("```json", "").replace("```", "").strip()
                data = json.loads(clean_text)
                all_data.extend(data if isinstance(data, list) else [data])
                st.success(f"✅ Success: {file.name}")
            else:
                st.error(f"❌ Error {response.status_code}: {response.text[:100]}")
        except Exception as e:
            st.error(f"❌ Error: {str(e)[:100]}")

    if all_data:
        df = pd.DataFrame(all_data)
        buffer = io.BytesIO()
        df.to_excel(buffer, index=False)
        st.download_button("📥 Excel Download", buffer.getvalue(), "result.xlsx")
