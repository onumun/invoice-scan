import streamlit as st
import pandas as pd
import io
import gc
import json
import re
import time
from typing import List, Dict, Any
from google import genai
from google.genai import types

# ページ設定
st.set_page_config(page_title="プロ仕様：レシート仕分けエンジン", layout="wide")

# セッション管理
if "api_key" not in st.session_state: st.session_state["api_key"] = ""

def clean_json_string(raw_text: str) -> str:
    """AIが吐き出すゴミを削ぎ落とし、純粋なJSON文字列だけを抽出する"""
    match = re.search(r'\[.*\]', raw_text, re.DOTALL)
    if match: return match.group(0)
    match_dict = re.search(r'\{.*\}', raw_text, re.DOTALL)
    if match_dict: return "[" + match_dict.group(0) + "]"
    return "[]"

def process_file(client, file) -> List[Dict[str, Any]]:
    """単一ファイルの解析とリトライロジック"""
    prompt = """
    領収書から全ての有効情報を抽出し、JSON配列のみで出力せよ。
    必須：店舗名、日付、金額、品目。
    その他：登録番号、電話番号、住所など記載あれば全項目抽出。
    通貨記号やカンマは除去した数値のみで出力。解説は不要。
    """
    for attempt in range(5):
        try:
            file_bytes = file.read()
            mime = "application/pdf" if file.name.lower().endswith('.pdf') else "image/jpeg"
            response = client.models.generate_content(
                model='gemini-2.5-flash',
                contents=[types.Part.from_bytes(data=file_bytes, mime_type=mime), prompt],
                config=types.GenerateContentConfig(response_mime_type="application/json")
            )
            data = json.loads(clean_json_string(response.text))
            return data if isinstance(data, list) else [data]
        except Exception as e:
            if "429" in str(e):
                time.sleep(20 * (attempt + 1)) # 指数バックオフ
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
        with st.spinner(f"解析中: {file.name}"):
            try:
                results = process_file(client, file)
                for res in results:
                    all_data.append(res)
            except Exception as e:
                st.error(f"{file.name} 解析失敗: {e}")

    if all_data:
        df = pd.DataFrame(all_data)
        
        # 必須項目を左へ強制移動
        base_cols = ["店舗名", "日付", "金額", "品目"]
        cols = base_cols + [c for c in df.columns if c not in base_cols]
        df = df[cols].fillna("")

        # データ型をExcel互換に強制矯正
        for col in df.columns:
            df[col] = df[col].apply(lambda x: ", ".join(x) if isinstance(x, list) else str(x))
            
        st.table(df)
        
        # ダウンロード処理
        buffer = io.BytesIO()
        df.to_excel(buffer, index=False)
        st.download_button("Excelダウンロード", buffer.getvalue(), "receipts.xlsx")
