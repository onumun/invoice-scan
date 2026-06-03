import streamlit as st
import pandas as pd
import io
import json
import requests
import base64

# --- ページ設定 ---
st.set_page_config(page_title="レシート仕分けエンジン", layout="wide")

# --- セッションステート初期化 ---
if "my_api_key" not in st.session_state:
    st.session_state["my_api_key"] = ""

# --- 常に表示するヘッダー（キー発行場所） ---
st.title("🚀 レシート仕分けエンジン PRO")
st.warning("💡 APIキーはここで入手してください： [Google AI Studio (aistudio.google.com)](https://aistudio.google.com/app/apikey)")

# --- APIキー入力（キーを明示的に指定して保持） ---
api_key_input = st.text_input(
    "APIキーを入力してください",
    type="password",
    value=st.session_state["my_api_key"],
    key="api_key_field"
)

if api_key_input:
    st.session_state["my_api_key"] = api_key_input

uploaded_files = st.file_uploader("レシート画像をアップロード", accept_multiple_files=True)

if st.button("Start Processing"):
    current_key = st.session_state["my_api_key"]
    
    if not current_key or not uploaded_files:
        st.error("APIキーとファイルをセットしてください。")
        st.stop()

    all_data = []
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={current_key}"

    for file in uploaded_files:
        try:
            image_data = base64.b64encode(file.getvalue()).decode("utf-8")
            
            payload = {
                "contents": [{
                    "parts": [
                        {"text": "Extract all receipt data as a JSON array. Return ONLY the JSON."},
                        {"inline_data": {"mime_type": "image/jpeg", "data": image_data}}
                    ]
                }],
                "generationConfig": {"response_mime_type": "application/json"}
            }

            response = requests.post(url, json=payload)
            
            if response.status_code == 200:
                res_json = response.json()
                text = res_json['candidates'][0]['content']['parts'][0]['text']
                json_str = text.strip().replace("```json", "").replace("```", "")
                data = json.loads(json_str)
                all_data.extend(data if isinstance(data, list) else [data])
                st.write(f"✅ Success: {file.name}")
            else:
                st.error(f"❌ API Error ({response.status_code}): {file.name}")
        except Exception as e:
            st.error(f"❌ Error in {file.name}: {str(e)[:50]}")

    if all_data:
        df = pd.DataFrame(all_data)
        buffer = io.BytesIO()
        df.to_excel(buffer, index=False)
        st.download_button("Download Excel", buffer.getvalue(), "result.xlsx")
