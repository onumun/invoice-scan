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
st.set_page_config(page_title="プロ仕様：レシート仕分けエンジン", layout="wide")

# APIキー管理
if "api_key" not in st.session_state: st.session_state["api_key"] = ""

def safe_error_message(e: Exception) -> str:
    """エラーメッセージをASCII範囲外を置換して安全に表示する"""
    return str(e).encode('utf-8', errors='replace').decode('ascii', errors='replace')

def clean_json_string(raw_text: str) -> str:
    match = re.search(r'\[.*\]', raw_text, re.DOTALL)
    if match: return match.group(0)
    match_dict = re.search(r'\{.*\}', raw_text, re.DOTALL)
    if match_dict: return "[" + match_dict.group(0) + "]"
    return "[]"

def process_file(client, file) -> List[Dict[str, Any]]:
    # getvalue()でバイナリ取得
    file_bytes = file.getvalue()
    mime = "application/pdf" if file.name.lower().endswith('.pdf') else "image/jpeg"
    
    prompt = "領収書から全情報を抽出し、日本語JSON配列のみで出力せよ。"
    
    for attempt in range(3):
        try:
            response = client.models.generate_content(
                model='gemini-2.5-flash',
                contents=[types.Part.from_bytes(data=file_bytes, mime_type=mime), prompt],
                config=types.GenerateContentConfig(response_mime_type="application/json")
            )
            return json.loads(clean_json_string(response.text))
        except Exception as e:
            if "429" in str(e):
                time.sleep(20)
                continue
            raise e
    return []

# UI構築
st.title("🚀 レシート仕分けエンジン PRO")
api_key = st.text_input("APIキー", type="password", value=st.session_state["api_key"])
st.session_state["api_key"] = api_key
uploaded_files = st.file_uploader("アップロード", accept_multiple_files=True, type=["png", "jpg", "jpeg", "pdf"])

if st.button("全データ解析開始"):
    if not api_key or not uploaded_files:
        st.error("入力不足")
        st.stop()

    client = genai.Client(api_key=api_key)
    all_data = []
    
    for file in uploaded_files:
        try:
            results = process_file(client, file)
            # リスト形式を強制して結合
            if isinstance(results, dict): results = [results]
            all_data.extend(results)
            st.success(f"成功: {file.name}")
        except Exception as e:
            # ここで文字化け対策したメッセージを表示
            st.error(f"{file.name} 解析失敗: {safe_error_message(e)}")

    if all_data:
        df = pd.DataFrame(all_data)
        # 不要な列削除と整理
        df = df.fillna("")
        for col in df.columns:
            df[col] = df[col].apply(lambda x: ", ".join(x) if isinstance(x, list) else str(x))
            
        st.table(df)
        
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
            df.to_excel(writer, index=False)
        
        st.download_button("📥 Excelダウンロード", buffer.getvalue(), "result.xlsx")
