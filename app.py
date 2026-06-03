import streamlit as st
import pandas as pd
import io
import json
import requests
import base64

st.set_page_config(page_title="Final Fix", layout="wide")

# 初期化
if "api_key" not in st.session_state:
    st.session_state["api_key"] = ""

st.title("🚀 レシート仕分けエンジン PRO")
st.warning("🔑 [APIキー発行](https://aistudio.google.com/app/apikey)")

# APIキーの入力と保持
api_key = st.text_input("API Key", type="password", value=st.session_state["api_key"])
if api_key:
    st.session_state["api_key"] = api_key

uploaded_files = st.file_uploader("Upload", accept_multiple_files=True)

if st.button("Start Processing"):
    if not st.session_state["api_key"] or not uploaded_files:
        st.error("APIキーを入力し、ファイルをアップロードしてください。")
        st.stop()

    all_data = []
    # 404が出ないよう、最も標準的なURL形式へ修正
    url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent"
    headers = {"Content-Type": "application/json"}
    params = {"key": st.session_state["api_key"]}

    for file in uploaded_files:
        try:
            image_b64 = base64.b64encode(file.getvalue()).decode("utf-8")
            payload = {
                "contents": [{
                    "parts": [
                        {"text": "Extract receipt data as a JSON array. Return ONLY JSON."},
                        {"inline_data": {"mime_type": "image/jpeg", "data": image_b64}}
                    ]
                }],
                "generationConfig": {"response_mime_type": "application/json"}
            }

            # URLとキーを分離して送信
            response = requests.post(url, headers=headers, params=params, json=payload)
            
            if response.status_code == 200:
                res_data = response.json()
                text = res_data['candidates'][0]['content']['parts'][0]['text']
                clean_text = text.replace("```json", "").replace("```", "").strip()
                data = json.loads(clean_text)
                all_data.extend(data if isinstance(data, list) else [data])
                st.success(f"Success: {file.name}")
            else:
                st.error(f"Error {response.status_code}: {response.text}")
        except Exception as e:
            st.error(f"Error: {str(e)}")

    if all_data:
        df = pd.DataFrame(all_data)
        buffer = io.BytesIO()
        df.to_excel(buffer, index=False)
        st.download_button("Download Excel", buffer.getvalue(), "result.xlsx")
