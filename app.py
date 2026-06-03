import streamlit as st
import pandas as pd
import io
import gc
import json
import time
from google import genai
from google.genai import types

# --- 1. ページ全体の初期設定 ---
st.set_page_config(
    page_title="爆速レシート一括仕分けシステム PRO",
    page_icon="🚀",
    layout="wide"
)

st.markdown("""
<style>
    div[data-testid="stTable"] {
        overflow-x: auto !important;
        -webkit-overflow-scrolling: touch;
    }
    div[data-testid="stTable"] table {
        min-width: 800px !important;
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
        
        prompt = """
        与えられた領収書・レシート・請求書の画像またはPDFから、データ分析や会計処理に必要なすべての有効な情報を漏れなく抽出してください。
        
        【必須項目】
        ・店舗名
        ・日付（YYYY-MM-DD形式、不明な場合は画像記載の通り）
        ・金額（合計金額、数値のみ）
        ・品目（購入内容や但し書きの内容）
        
        【動的追加項目】
        上記以外にも、画像内に「登録番号（インボイス番号、Tから始まる13桁の番号）」「電話番号」「住所」「税率内訳（10%対象、8%対象など）」「割引額」などの記載がある場合は、それらもすべて個別のキーとして動的に追加し、漏れなく含めてください。
        
        出力は必ず、オブジェクトを要素とするJSON配列形式（[]で囲まれた形式）のみとしてください。
        """
        
        for index, file in enumerate(uploaded_files):
            status_text.text(f"📄 処理中 ({index + 1}/{len(uploaded_files)}): {file.name} ...")
            
            file_bytes = file.read()
            mime_type = "application/pdf" if file.name.lower().endswith('.pdf') else "image/jpeg"
            
            max_retries = 3
            response = None
            
            for attempt in range(max_retries):
                try:
                    # モデル名を 2.0-flash に修正
                    response = client.models.generate_content(
                        model='gemini-2.0-flash',
                        contents=[
                            types.Part.from_bytes(
                                data=file_bytes,
                                mime_type=mime_type,
                            ),
                            prompt
                        ],
                        config=types.GenerateContentConfig(
                            response_mime_type="application/json"
                        )
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
                    if isinstance(json_data, dict):
                        json_data = [json_data]
                        
                    df = pd.DataFrame(json_data)
                    all_data.append(df)
                    st.success(f"✅ {file.name} の解析に成功しました。")
                
            except Exception as parse_e:
                st.warning(f"⚠️ {file.name} のデータ処理でエラーが発生しました。")
                continue
                
            finally:
                gc.collect()
            
            progress_bar.progress((index + 1) / len(uploaded_files))
            
        status_text.text("✨ 解析処理を終了しました。")
        
        if all_data:
            final_df = pd.concat(all_data, ignore_index=True, sort=False)
            base_cols = ["店舗名", "日付", "金額", "品目"]
            existing_base_cols = [c for c in base_cols if c in final_df.columns]
            other_cols = [c for c in final_df.columns if c not in base_cols]
            final_df = final_df[existing_base_cols + other_cols]
            final_df = final_df.fillna("")
            
            st.subheader("📊 解析結果プレビュー（全項目自動表記）")
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
        else:
            st.error("❌ 有効なデータを抽出できませんでした。")
            
    except Exception as e:
        st.error("❌ システムエラーが発生しました。")
        with st.expander("詳細なエラーログ"):
            st.code(str(e))
            
    finally:
        gc.collect()
