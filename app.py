import streamlit as st
import pandas as pd
import io
import gc
import json
from google import genai
from google.genai import types

# --- 1. ページ全体の初期設定（プロっぽい外観） ---
st.set_page_config(
    page_title="爆速レシート一括仕分けシステム PRO",
    page_icon="🚀",
    layout="wide"
)

# --- 2. サイドバーの設定（ユーザー動線を1, 2, 3で完全明記） ---
st.sidebar.header("🔑 1分で完了！初期設定")
st.sidebar.markdown("""
本ツールは、あなた専用の無料AIキー（Gemini APIキー）を利用して安全に動作します。
以下の**3つのステップ**で設定が完了します。
""")

# 【項目1】キー発行サイトへの直リンク
st.sidebar.subheader("1️⃣ キー発行サイトを開く")
st.sidebar.link_button(
    "👉 無料APIキーを今すぐ取得する",
    "https://aistudio.google.com/app/apikey",
    type="primary",
    use_container_width=True
)
st.sidebar.caption("※Googleアカウント（Gmail等）へのログインが必要です。")

# 【項目2】やるべき操作の視覚的ガイド
st.sidebar.subheader("2️⃣ サイトでキーをコピーする")
st.sidebar.info("開いた画面にある青い **「Create API key」** ボタンを押し、発行されたコード（`AIzaSy...`から始まる文字列）をコピーしてください。")

# 【項目3】入力欄の明記
st.sidebar.subheader("3️⃣ ここに貼り付ける")
user_api_key = st.sidebar.text_input(
    "取得した API キーを入力👇",
    type="password",
    placeholder="AIzaSy..."
)

# --- 【プロ仕様】APIキーの自動検証ロジック ---
api_verified = False
if user_api_key:
    if not user_api_key.startswith("AIzaSy"):
        st.sidebar.error("❌ キーの形式が正しくないようです（AIzaSyから始まります）")
    else:
        try:
            # 軽量なリクエストを送信してキーの有効性を即座にテスト
            test_client = genai.Client(api_key=user_api_key)
            test_client.models.generate_content(
                model='gemini-2.5-flash',
                contents="test"
            )
            st.sidebar.success("✅ APIキーの認証に成功しました！準備完了です。")
            api_verified = True
        except Exception:
            st.sidebar.error("❌ 無効なAPIキーです。コピーミスがないか確認してください。")

# ここを修正！正しい区切り線の命令
st.sidebar.divider()

# 就活・論文の審査に耐えうるセキュリティポリシーの明記
st.sidebar.subheader("🛡️ プライバシー＆セキュリティ方針")
st.sidebar.caption("""
- **データの即時破棄**: アップロードされた画像および生成されたExcelデータは、処理完了後にサーバーのメモリから即座に完全消去されます。サーバーへの保存は一切行われません。
- **通信の安全性**: Googleの公式APIへ直接暗号化通信を行います。
- **免責事項**: 本ツールは無料のオープンソースです。無料版APIの規約上、機密性の極めて高い個人情報の入力は自己責任でお願いいたします。
""")

# --- 3. メイン画面のUI ---
st.title("🚀 爆速レシート一括仕分けシステム PRO")
st.markdown("複数のレシート画像やPDFを一括で読み込み、AIが自動で店舗名、日付、金額、品目を判別してExcel化します。")

# ファイルアップローダー（複数選択・PDF対応）
uploaded_files = st.file_uploader(
    "レシートの画像（JPEG/PNG）またはPDFを選択（複数選択可）",
    type=["png", "jpg", "jpeg", "pdf"],
    accept_multiple_files=True
)

# 一括スキャン開始ボタン
if st.button("一括スキャン開始", type="primary"):
    
    # バリデーションチェック
    if not user_api_key or not api_verified:
        st.error("❌ 画面左側のサイドバーで有効な Gemini API キーを設定してください。")
        st.stop()
        
    if not uploaded_files:
        st.warning("⚠️ スキャンするファイルを1つ以上アップロードしてください。")
        st.stop()

    all_data = []
    
    # UX向上のための進捗バー
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    try:
        client = genai.Client(api_key=user_api_key)
        
        # 厳格なプロンプト定義（異常データ排除ロジック）
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
            
            # APIリクエスト
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
            
            res_text = response.text.strip()
            
            # Markdown装飾のクレンジング処理
            if res_text.startswith("
```"):
                res_text = res_text.split("```")[1]
                if res_text.startswith("json"):
                    res_text = res_text[4:]
            res_text = res_text.strip("`").strip()
            
            try:
                json_data = json.loads(res_text)
                
                # ユーザーが発見した「混ぜ物バグ」に対応する条件分岐
                if not json_data:
                    st.warning(f"⚠️ {file.name} はレシート画像ではないと判定されたため、スキップしました。")
                else:
                    df = pd.DataFrame(json_data)
                    all_data.append(df)
                    st.success(f"✅ {file.name} の解析に成功しました！")
                
            except Exception as parse_err:
                st.warning(f"⚠️ {file.name} のデータ変換に失敗しました。")
                with st.expander(f"🔍 {file.name} のデバッグ情報"):
                    st.text("AIからの生出力:")
                    st.code(res_text)
                continue
                
            finally:
                # セキュリティと省メモリのためのリソース解放
                del file_bytes
                gc.collect()
            
            progress_bar.progress((index + 1) / len(uploaded_files))
            
        status_text.text("✨ すべてのファイルの解析処理を終了しました。")
        
        # --- 5. 結果の結合とExcel出力 ---
        if all_data:
            final_df = pd.concat(all_data, ignore_index=True)
            
            st.subheader("📊 解析結果プレビュー")
            st.dataframe(final_df, use_container_width=True)
            
            # メモリバッファ上でのExcel生成
            excel_buffer = io.BytesIO()
            with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
                final_df.to_excel(writer, index=False, sheet_name='レシート仕分け結果')
            
            st.download_button(
                label="📥 仕分け結果をExcelでダウンロード",
                data=excel_buffer.getvalue(),
                file_name="レシート一括仕分け結果.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                type="primary"
            )
            
            # 機密情報データのメモリ強制破棄
            del excel_buffer
            del final_df
            gc.collect()
            
        else:
            st.error("❌ アップロードされたファイルの中に、有効なレシート画像が1枚もありませんでした。")
            
    except Exception as e:
        st.error("❌ 通信エラーが発生しました。")
        with st.expander("詳細なエラーログ（開発者向け）"):
            st.code(str(e))
            
    finally:
        gc.collect()
