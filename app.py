import streamlit as st
import pandas as pd
import io
import json
import requests
import base64

# --- ページ設定とセッション保持 ---
st.set_page_config(page_title="レシート仕分けエンジン PRO", layout="wide")

if "api_key" not in st.session_state: st.session_state["api_key"] = ""
if "model_name" not in st.session_state: st.session_state["model_name"] = "gemini-1.5-flash"

# --- UIとガイドの復元 ---
st.title("🚀 レシート仕分けエンジン PRO")
st.info("### 運用ガイド\n"
        "1. [Google AI Studio](https://aistudio.google.com/app/apikey) でAPIキーを取得してください。\n"
        "2. 下記の入力欄にキーとモデル名を入力してください。（一度入力すれば保持されます）")

col1, col2 = st.columns(2)
with col1:
    api_key = st.text_input("API Key", type="password", value=st.session_state["api_key"])
with col2:
    model_name = st.text_input("Model Name (例: gemini-1.5-flash)", value=st.session_state["model_name"])

st.session_state["api_key"] = api_key
st.session_state["model_name"] = model_name

uploaded_files = st.file_uploader("レシート画像をアップロード", accept_multiple_files=True)

if st.button("一括スキャン開始"):
    if not api_key or not uploaded_files:
        st.error("入力が不足しています。")
        st.stop()

    all_data = []
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent"
    
    for file in uploaded_files:
        try:
            # 確実なバイナリ読み込み
            image_b64 = base64.b64encode(file.read()).decode("utf-8")
            payload = {
                "contents": [{"parts": [
                    {"text": "Extract all receipt data (Store, Date, Amount, Items, Tax) into a clean JSON array."},
                    {"inline_data": {"mime_type": "image/jpeg", "data": image_b64}}
                ]}],
                "generationConfig": {"response_mime_type": "application/json"}
            }

            response = requests.post(url, params={"key": api_key}, json=payload)
            
            if response.status_code == 200:
                res_json = response.json()
                text = res_json['candidates'][0]['content']['parts'][0]['text']
                data = json.loads(text.replace("```json", "").replace("```", "").strip())
                all_data.extend(data if isinstance(data, list) else [data])
                st.write(f"✅ Success: {file.name}")
            else:
                # 404が出た場合、モデル名が違うことがこのエラー文でわかる
                st.error(f"❌ Error {response.status_code}: {response.text[:100]}")
        except Exception as e:
            st.error(f"❌ System Error: {str(e)[:100]}")

    if all_data:
        df = pd.DataFrame(all_data).fillna("")
        st.table(df)
        buffer = io.BytesIO()
        df.to_excel(buffer, index=False)
        st.download_button("📥 Excelダウンロード", buffer.getvalue(), "result.xlsx")
