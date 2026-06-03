import streamlit as st
import pandas as pd
import io
import gc
import json
import time
from google import genai
from google.genai import types
from pydantic import BaseModel  # 正しいインポートに修正

# --- 1. ページ全体の初期設定 ---
st.set_page_config(
    page_title="爆速レシート一括仕分けシステム PRO",
    page_icon="🚀",
    layout="wide"
)

# スマホ画面でのスクロール保証
st.markdown("""
<style>
    div[data-testid="stTable"] {
        overflow-x: auto !important;
        -webkit-overflow-scrolling: touch;
    }
    div[data-testid="stTable"] table {
        min-width: 500px !important;
    }
</style>
""", unsafe_allow_html=True)

if "api_key" not in st.session_state:
    st.session_state["api_key"] = ""

# --- 2. サイドバーの設定 ---
st.sidebar.header("🔑 初期設定（PC用）")
input_key_sidebar = st.sidebar.text_input(
    "サイドバー用入力欄",
    type="password",
    value=st.session_state["api_key"],
    key="key_sidebar"
)
if input_key_sidebar:
    st.session_state["api_key"] = input_key_sidebar.strip()

# --- 3. メイン画面のUI ---
st.title("🚀 レシート一括仕分けシステム PRO")

col1, col2 = st.columns([1, 1])
with col1:
    st.link_button(
        "✨ 無料APIキー発行サイトへ",
        "https://aistudio.google.com/app/apikey",
        type="primary",
        use_container_width=True
    )
with col2:
    input_key_main = st.text_input(
        "🔑 取得したAPIキーをここに貼り付け",
        type="password",
        value=st.session_state["api_key"],
        placeholder="AQ. から始まるキーを貼り付け",
        key="key_main"
    )
    if input_key_main:
        st.session_state["api_key"] = input_key_main.strip()

st.divider()

uploaded_files = st.file_uploader(
    "レシートの画像（JPEG/PNG）またはPDFを選択（複数選択可）",
    type=["png", "jpg", "jpeg", "pdf"],
    accept_multiple_files=True
)

if st.button("一括スキャン開始", type="primary", use_container_width=True):
    
    cleaned_api_key = st.session_state["api_key"]
    
    if not cleaned_api_key:
        st.error("❌ APIキーが入力されていません。")
        st.stop()
        
    if not uploaded_files:
        st.warning("⚠️ スキャンするファイルを1つ以上アップロードしてください。")
        st.stop()

    all_data = []
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    try:
        client = genai.Client(api_key=cleaned_api_key)
        
        # PydanticのBaseModelを正しく継承
        class ReceiptItem(BaseModel):
            店舗名: str
            日付: str
            金額: int
            品目: str

        prompt = "与えられた画像またはPDFから、店舗名、日付（YYYY-MM-DD形式）、金額（数値のみ）、品目をすべて抽出してください。複数の品目がある場合はそれぞれ分けてリストにしてください。"
        
        for index, file in enumerate(uploaded_files):
            status_text.text(f"📄 処理中 ({index + 1}/{len(uploaded_files)}): {file.name} ...")
            
            file_bytes = file.read()
            mime_type = "application/pdf" if file.name.lower().endswith('.pdf') else "image/jpeg"
            
            max_retries = 3
            response = None
            
            for attempt in range(max_retries):
                try:
                    response = client.models.generate_content(
                        model='gemini-2.5-flash',
                        contents=[
                            types.Part.from_bytes(
                                data=file_bytes,
                                mime_type=mime_type,
                            ),
                            prompt
                        ],
                        config=types.GenerateContentConfig(
                            response_mime_type="application/json",
                            response_schema=list[ReceiptItem],
                        ),
                    )
                    break
                except Exception as api_err:
                    if "503" in str(api_err) or "unavailable" in str(api_err).lower():
                        if attempt < max_retries - 1:
                            time.sleep(1.5)
                            continue
                    raise api_err
            
            if not response:
                continue

            res_text = response.text.strip()
            
            try:
                json_data = json.loads(res_text)
                if json_data:
                    df = pd.DataFrame(json_data)
                    df = df[["店舗名", "日付", "金額", "品目"]]
                    all_data.append(df)
                
            except Exception:
                continue
                
            finally:
                del file_bytes
                gc.collect()
            
            progress_bar.progress((index + 1) / len(uploaded_files))
            
        status_text.text("✨ 解析処理を終了しました。")
        
        if all_data:
            final_df = pd.concat(all_data, ignore_index=True)
            st.subheader("📊 解析結果プレビュー")
            st.table(final_df)
            
            excel_buffer = io.BytesIO()
            with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
                final_df.to_excel(writer, index=False, sheet_name='レシート仕分け結果')
            
            st.download_button(
                label="📥 仕分け結果をExcelでダウンロード",
                data=excel_buffer.getvalue(),
                file_name="レシート一括仕分け結果.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                type="primary",
                use_container_width=True
            )
            del excel_buffer
            del final_df
            gc.collect()
        else:
            st.error("❌ 有効なデータを抽出できませんでした。")
            
    except Exception as e:
        st.error("❌ エラーが発生しました。")
        with st.expander("詳細なエラーログ"):
            st.code(str(e))
            
    finally:
        gc.collect()
