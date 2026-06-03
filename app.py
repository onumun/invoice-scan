import streamlit as st
import pandas as pd
import io
import json
import requests
import base64
import sys

# --- ページ設定 ---
st.set_config = st.set_page_config(page_title="RECEIPT-AI PRO", layout="wide")

# --- セッションステートの永続化 ---
if "api_key" not in st.session_state: st.session_state["api_key"] = ""
if "model_id" not in st.session_state: st.session_state["model_id"] = "gemini-1.5-flash"

# --- UI構築：機能とガイドをサイドバーに集約 ---
st.title("RECEIPT-AI: PROFESSIONAL SCANNER")

with st.sidebar:
    st.subheader("⚙️ 設定パネル")
    st.markdown("APIキーは [Google AI Studio](https://aistudio.google.com/app/apikey) で取得してください。")
    
    # セッションステートと直接連携する入力欄
    key_input = st.text_input("API Key", type="password", value=st.session_state["api_key"])
    model_input = st.text_input("Model ID", value=st.session_state["model_id"])
    
    st.session_state["api_key"] = key_input
    st.session_state["model_id"] = model_input
    
    st.divider()
    st.info("このサイドバーの設定は、ボタンを押しても消えません。")

# --- メインロジック ---
uploaded_files = st.file_uploader("レシート画像をアップロードしてください", accept_multiple_files=True)

if st.button("RUN SCAN"):
    if not st.session_state["api_key"] or not uploaded_files:
        st.error("APIキーとファイルを確認してください。")
        st.stop()

    all_data = []
    # 確実なモデルエンドポイント構築
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{st.session_state['model_id']}:generateContent"

    for file in uploaded_files:
        try:
            # バイナリをbase64へ
            file_content = file.read()
            image_b64 = base64.b64encode(file_content).decode("utf-8")
            
            # APIへのリクエスト
            payload = {
                "contents": [{"parts": [
                    {"text": "Extract all receipt data (Store name, Date, Total Amount, Items) as a clean JSON array."},
                    {"inline_data": {"mime_type": "image/jpeg", "data": image_b64}}
                ]}],
                "generationConfig": {"response_mime_type": "application/json"}
            }

            response = requests.post(url, params={"key": st.session_state['api_key']}, json=payload)
            
            if response.status_code == 200:
                res_data = response.json()
                # 応答のパース
                raw_text = res_data['candidates'][0]['content']['parts'][0]['text']
                clean_text = raw_text.replace("```json", "").replace("```", "").strip()
                data = json.loads(clean_text)
                all_data.extend(data if isinstance(data, list) else [data])
                st.success(f"✅ Success: {file.name}")
            else:
                # 404などのエラーを、Streamlitがクラッシュしない安全な文字列に変換
                err_msg = str(response.status_code) + ": " + response.text.encode('ascii', 'ignore').decode('ascii')
                st.error(f"❌ API Error: {err_msg[:100]}")
        
        except Exception as e:
            # システムエラーも完全にASCIIへ変換
            safe_e = str(e).encode('ascii', 'ignore').decode('ascii')
            st.error(f"❌ Logic Error: {safe_e[:100]}")

    # 結果の出力
    if all_data:
        df = pd.DataFrame(all_data)
        st.dataframe(df)
        
        buffer = io.BytesIO()
        df.to_excel(buffer, index=False)
        st.download_button("📥 DOWNLOAD EXCEL", buffer.getvalue(), "receipt_data.xlsx")
