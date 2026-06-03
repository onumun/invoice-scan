import streamlit as st
import pandas as pd
import io
import json
import re
from google import genai
from google.genai import types

# --- ページ設定 ---
st.set_page_config(page_title="爆速仕分け PRO", layout="wide")

# --- メイン処理 ---
if "api_key" not in st.session_state:
    st.session_state["api_key"] = ""

st.title("🚀 レシート一括仕分け PRO")
api_key = st.text_input("APIキー", type="password", value=st.session_state["api_key"])
st.session_state["api_key"] = api_key

uploaded_files = st.file_uploader("ファイルをアップロード", accept_multiple_files=True, type=["png", "jpg", "jpeg", "pdf"])

if st.button("一括スキャン実行"):
    if not api_key or not uploaded_files:
        st.error("キーまたはファイルが必要です")
        st.stop()

    client = genai.Client(api_key=api_key)
    all_data = []
    
    # 情報を漏らさず抽出するためのシンプルな指示
    prompt = "この画像の領収書から全ての情報を抽出し、JSON配列のみで出力せよ。解説やMarkdownは一切不要。"

    for file in uploaded_files:
        try:
            file_bytes = file.read()
            mime = "application/pdf" if file.name.lower().endswith('.pdf') else "image/jpeg"
            
            response = client.models.generate_content(
                model='gemini-2.5-flash',
                contents=[types.Part.from_bytes(data=file_bytes, mime_type=mime), prompt],
                config=types.GenerateContentConfig(response_mime_type="application/json")
            )
            
            # JSONだけを確実に抽出する正規表現
            res = re.search(r'\[.*\]', response.text, re.DOTALL)
            if res:
                data = json.loads(res.group(0))
                df = pd.DataFrame(data if isinstance(data, list) else [data])
                all_data.append(df)
            
            del file_bytes
        except Exception as e:
            st.error(f"{file.name} でエラー: {e}")

    if all_data:
        # 全データを結合（順序を維持）
        final_df = pd.concat(all_data, ignore_index=True, sort=False).fillna("")
        
        # Excel出力用に全データを文字列へ統一し、リスト構造をカンマ区切りへ補正
        for col in final_df.columns:
            final_df[col] = final_df[col].apply(lambda x: ", ".join(x) if isinstance(x, list) else str(x))
            
        st.table(final_df)
        
        buffer = io.BytesIO()
        final_df.to_excel(buffer, index=False)
        st.download_button("Excelダウンロード", buffer.getvalue(), "result.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
