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

# スマホの画面潰れを防ぐためのカスタムCSSスタイル（文字重なり防止）
st.markdown("""
<style>
    /* テーブル全体の文字サイズをスマホ用に調整し、折り返しを防ぐ */
    .styled-table {
        width: 100%;
        border-collapse: collapse;
        font-size: 14px;
        min-width: 400px;
    }
    .styled-table th, .styled-table td {
        padding: 8px;
        border: 1px solid #ddd;
        text-align: left;
        white-space: nowrap; /* 文字が縦に潰れて重なるのを防ぐ */
    }
    /* スマホで横スクロールを強制的に有効化 */
    .table-container {
        overflow-x: auto !important;
        -webkit-overflow-scrolling: touch;
        margin-bottom: 20px;
        border: 1px solid #ccc;
    }
</style>
""", unsafe_allow_html=True)

# --- 状態をガッチリ固定するセッションの初期化 ---
if "api_key" not in st.session_state:
    st.session_state["api_key"] = ""

# --- 2. サイドバーの設定（PC用） ---
st.sidebar.header("🔑 初期設定（PC用）")
st.sidebar.markdown("※スマホの方はメイン画面の入力欄をご利用ください。")

st.sidebar.subheader("1️⃣ キー発行サイトを開く")
st.sidebar.link_button(
    "👉 無料APIキーを今すぐ取得する",
    "https://aistudio.google.com/app/apikey",
    type="primary",
    use_container_width=True
)

st.sidebar.subheader("2️⃣ ここに貼り付ける")
input_key_sidebar = st.sidebar.text_input(
    "サイドバー用入力欄",
    type="password",
    value=st.session_state["api_key"],
    key="key_sidebar"
)
if input_key_sidebar:
    st.session_state["api_key"] = input_key_sidebar.strip()

st.sidebar.divider()
st.sidebar.subheader("🛡️ セキュリティ方針")
st.sidebar.caption("データは処理完了後にサーバーのメモリから即座に完全消去されます。")


# --- 3. メイン画面のUI ---
st.title("🚀 レシート一括仕分けシステム PRO")
st.markdown("複数のレシートを一括で読み込み、AIが自動で店舗名、日付、金額、品目を判別してExcel化します。")

# 【一部しかない問題の解決】スマホでサイドバーが隠れてもいいように、メイン画面にも入力欄を配置
st.info("💡 **【重要】スキャンを始める前に**\n\nまずは下のボタンから無料のAPIキーを取得し、入力欄に貼り付けてください。")

col1, col2 = st.columns([1, 1])
with col1:
    st.link_button(
        "✨ 1発で取得！無料APIキー発行サイトへ",
        "https://aistudio.google.com/app/apikey",
        type="primary",
        use_container_width=True
    )
with col2:
    input_key_main = st.text_input(
        "🔑 取得したAPIキーをここに貼り付け👇",
        type="password",
        value=st.session_state["api_key"],
        placeholder="AQ. から始まるキーを貼り付け",
        key="key_main"
    )
    if input_key_main:
        st.session_state["api_key"] = input_key_main.strip()

st.divider()

# ファイルアップローダー
uploaded_files = st.file_uploader(
    "レシートの画像（JPEG/PNG）またはPDFを選択（複数選択可）",
    type=["png", "jpg", "jpeg", "pdf"],
    accept_multiple_files=True
)

if st.button("一括スキャン開始", type="primary", use_container_width=True):
    
    cleaned_api_key = st.session_state["api_key"]
    
    if not cleaned_api_key:
        st.error("❌ APIキーが入力されていません。上の欄に貼り付けてください。")
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
        与えられた画像またはPDFが「領収書・レシート」である場合は、以下の4つの情報を正確に抽出してください。
        出力は必ず、以下のフォーマット通りの有効なJSON配列（生データのみ）にしてください。文字装飾（```json などのMarkdown）は絶対に付けないでください。
        複数の品目がある場合は品目ごとにデータ（オブジェクト）を分けてください。

        [
          {
            "店舗名": "〇〇株式会社",
            "日付": "2026-03-24",
            "金額": 1500,
            "品目": "文房具代"
          }
        ]

        重要：もし、与えられた画像が領収書やレシートではない場合、または文字が全く読めない場合は、説明文などは一切出力せず、ただ空の配列「 [] 」のみを出力してください。
        """
        
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
                        ]
                    )
                    break
                except Exception as api_err:
                    if "503" in str(api_err) or "unavailable" in str(api_err).lower():
                        if attempt < max_retries - 1:
                            st.warning(f"⚠️ サーバー混雑中。自動再試行します... ({attempt + 1}/{max_retries})")
                            time.sleep(1.5)
                            continue
                    raise api_err
            
            if not response:
                st.error(f"❌ {file.name} の処理中にタイムアウトしました。")
                continue

            res_text = response.text.strip()
            
            if res_text.startswith("```"):
                res_text = res_text.split("```")[1]
                if res_text.startswith("json"):
                    res_text = res_text[4:]
            res_text = res_text.strip("`").strip()
            
            try:
                json_data = json.loads(res_text)
                
                if not json_data:
                    st.warning(f"⚠️ {file.name} はレシート画像ではないためスキップしました。")
                else:
                    df = pd.DataFrame(json_data)
                    all_data.append(df)
                    st.success(f"✅ {file.name} の解析成功！")
                
            except Exception as parse_err:
                st.warning(f"⚠️ {file.name} のデータ変換に失敗しました。")
                continue
                
            finally:
                del file_bytes
                gc.collect()
            
            progress_bar.progress((index + 1) / len(uploaded_files))
            
        status_text.text("✨ すべてのファイルの解析処理を終了しました。")
        
        if all_data:
            final_df = pd.concat(all_data, ignore_index=True)
            
            st.subheader("📊 解析結果プレビュー")
            
            # 【重なり・スクロールバグの解決】HTMLとCSSを使って、スマホでも絶対に潰れない横スクロール表を出力
            html_table = final_df.to_html(classes='styled-table', index=False)
            st.markdown(f'<div class="table-container">{html_table}</div>', unsafe_allow_html=True)
            
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
            st.error("❌ 有効なレシート画像が1枚もありませんでした。")
            
    except Exception as e:
        if "503" in str(e) or "unavailable" in str(e).lower():
            st.error("❌ Googleのサーバーが混雑しています。少し時間を空けて再度お試しください。")
        else:
            st.error("❌ 通信エラーが発生したか、APIキーが無効です。")
        with st.expander("詳細なエラーログ"):
            st.code(str(e))
            
    finally:
        gc.collect()
