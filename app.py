import streamlit as st
import pandas as pd
import io
import json
import re
import time
from typing import List, Dict, Any
from google import genai
from google.genai import types

# ページ設定
st.set_page_config(page_title="レシート仕分け PRO", layout="wide")

if "api_key" not in st.session_state: st.session_state["api_key"] = ""

def process_file(client, file) -> List[Dict[str, Any]]:
    file_bytes = file.getvalue()
    mime = "application/pdf" if file.name.lower().endswith('.pdf') else "image/jpeg"
    
    # 指示を英語主体にして、JSONパースの安定性を最大化する
    prompt = "Extract all information from this receipt and output ONLY a JSON array."
    
    for attempt in range(3):
        try:
            response = client.models.generate_content(
                model='gemini-2.5-flash',
                contents=[types.Part.from_bytes(data=file_bytes, mime_type=mime), prompt],
                config=types.GenerateContentConfig(response_mime_type="application/json")
            )
            
            # JSON部分のみ抜き出す
            match = re.search(r'\[.*\]', response.text, re.DOTALL)
            json_str = match.group(0) if match else "[]"
            return json.loads(json_str)
        except Exception as e:
            if "429" in str(e):
                time.sleep(20)
                continue
            raise e
    return []

# UI
st.title("🚀 レシート仕分けエンジン PRO")
api_key = st.text_input("APIキー", type="password", value=st.session_state["api_key"])
st.session_state["api_key"] = api_key
uploaded_files = st.file_uploader("アップロード", accept_multiple_files=True, type=["png", "jpg", "jpeg", "pdf"])

if st.button("全データ解析開始"):
    if not api_key or not uploaded_files:
        st.stop()

    client = genai.Client(api_key=api_key)
    all_data = []
    
    for file in uploaded_files:
        try:
            results = process_file(client, file)
            all_data.extend(results if isinstance(results, list) else [results])
            st.write(f"✅ Success: {file.name}") # st.successを避けてシンプルな表示にする
        except Exception:
            # エラーの詳細（日本語）をUIに渡すとクラッシュするので、短く英数字のみで表示する
            st.error(f"❌ Failed to process: {file.name}")

    if all_data:
        df = pd.DataFrame(all_data).fillna("")
        st.table(df.head(10)) # 表示も控えめにして安全性を確保
        
        buffer = io.BytesIO()
        df.to_excel(buffer, index=False)
        st.download_button("📥 Download Excel", buffer.getvalue(), "result.xlsx")
