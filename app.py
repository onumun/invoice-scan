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

def clean_json_string(raw_text: str) -> str:
    """UTF-8を維持しつつ、JSON配列部分のみを抽出"""
    match = re.search(r'\[.*\]', raw_text, re.DOTALL)
    if match: return match.group(0)
    match_dict = re.search(r'\{.*\}', raw_text, re.DOTALL)
    if match_dict: return "[" + match_dict.group(0) + "]"
    return "[]"

def process_file(client, file) -> List[Dict[str, Any]]:
    # ファイルを一度読み込んでバッファ確保
    file_bytes = file.getvalue()
    mime = "application/pdf" if file.name.lower().endswith('.pdf') else "image/jpeg"
    
    prompt = """
    領収書から全ての有効情報を抽出し、日本語のJSON配列のみで出力せよ。
    必須：店舗名、日付、金額、品目。
    その他：登録番号、電話番号、住所など記載あれば全項目抽出。
    通貨記号やカンマは除去。解説不要。
    """
    
    for attempt in range(5):
        try:
            response = client.models.generate_content(
                model='gemini-2.5-flash',
                contents=[types.Part.from_bytes(data=file_bytes, mime_type=mime), prompt],
                config=types.GenerateContentConfig(response_mime_type="application/json")
            )
            # 文字コードを意識してパース
            json_str = clean_json_string(response.text)
            data = json.loads(json_str) 
            return data if isinstance(data, list) else [data]
        except Exception as e:
            if "429" in str(e):
                time.sleep(20 * (attempt + 1))
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
        st.error("入力不足")
        st.stop()

    client = genai.Client(api_key=api_key)
    all_data = []
    
    for file in uploaded_files:
        try:
            results = process_file(client, file)
            for res in results:
                all_data.append(res)
            st.success(f"解析成功: {file.name}")
        except Exception as e:
            st.error(f"{file.name} 解析失敗: {e}")

    if all_data:
        df = pd.DataFrame(all_data)
        # 列の整理と型強制（UTF-8で統一）
        base_cols = ["店舗名", "日付", "金額", "品目"]
        cols = base_cols + [c for c in df.columns if c not in base_cols]
        df = df[cols].fillna("")

        for col in df.columns:
            df[col] = df[col].apply(lambda x: ", ".join(x) if isinstance(x, list) else str(x))
            
        st.table(df)
        
        # ダウンロード時の文字化け対策（utf-8-sigをExcelで指定）
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
            df.to_excel(writer, index=False)
        
        st.download_button("Excelダウンロード", buffer.getvalue(), "receipts.xlsx")
