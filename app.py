import streamlit as st
import pandas as pd
import io
import json
import re
from google import genai
from google.genai import types

# --- ページ設定 ---
st.set_page_config(page_title="爆速仕分け PRO", layout="wide")

# --- セッションステートの初期化 ---
if "api_key" not in st.session_state:
    st.session_state["api_key"] = ""

# --- UI構築 ---
st.title("🚀 レシート一括仕分け PRO")

# 運用に必要なガイドを復元
st.info("### 💡 システム運用ガイド\n"
        "1. 初回利用時：以下のボタンからGoogle AI Studioへ移動し、APIキー（`AIza...`で始まるもの）を発行してください。\n"
        "2. 2回目以降：入力したAPIキーはブラウザを更新しても自動で保持されます。")

st.link_button("🔑 無料APIキーを発行する (Google AI Studio)", "https://aistudio.google.com/app/apikey", type="primary")

st.divider()

# キー入力欄
api_key = st.text_input(
    "APIキーを入力", 
    type="password", 
    value=st.session_state["api_key"],
    placeholder="AIza... から始まるキーを貼り付けてください"
)
if api_key:
    st.session_state["api_key"] = api_key

uploaded_files = st.file_uploader(
    "レシート画像・PDFをアップロード（複数選択可）", 
    accept_multiple_files=True, 
    type=["png", "jpg", "jpeg", "pdf"]
)

if st.button("一括スキャン実行"):
    if not st.session_state["api_key"] or not uploaded_files:
        st.error("APIキーとファイルを両方セットしてください")
        st.stop()

    try:
        client = genai.Client(api_key=st.session_state["api_key"])
        all_data = []
        prompt = "この画像の領収書から全ての情報を抽出し、JSON配列のみで出力せよ。解説やMarkdownは一切不要。"

        for file in uploaded_files:
            file_bytes = file.read()
            mime = "application/pdf" if file.name.lower().endswith('.pdf') else "image/jpeg"
            
            response = client.models.generate_content(
                model='gemini-2.5-flash',
                contents=[types.Part.from_bytes(data=file_bytes, mime_type=mime), prompt],
                config=types.GenerateContentConfig(response_mime_type="application/json")
            )
            
            res = re.search(r'\[.*\]', response.text, re.DOTALL)
            if res:
                data = json.loads(res.group(0))
                df = pd.DataFrame(data if isinstance(data, list) else [data])
                all_data.append(df)

        if all_data:
            final_df = pd.concat(all_data, ignore_index=True, sort=False).fillna("")
            for col in final_df.columns:
                final_df[col] = final_df[col].apply(lambda x: ", ".join(x) if isinstance(x, list) else str(x))
                
            st.success("✨ 全ての解析が完了しました！")
            st.table(final_df)
            
            buffer = io.BytesIO()
            final_df.to_excel(buffer, index=False)
            st.download_button(
                "📥 Excelダウンロード", 
                buffer.getvalue(), 
                "result.xlsx", 
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
    except Exception as e:
        st.error(f"解析中にエラーが発生しました: {e}")
