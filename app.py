import os
import json
import io
import pandas as pd
from google import genai
from google.genai import types
from pydantic import BaseModel, Field
from typing import List
import streamlit as st

if "GEMINI_API_KEY" in st.secrets:
    GOOGLE_API_KEY = st.secrets["GEMINI_API_KEY"]
else:
    GOOGLE_API_KEY = ""

class InvoiceItem(BaseModel):
    item_name: str = Field(description="品目名・内容。")
    amount: int = Field(description="その明細の金額（数値のみ）")
    account_title: str = Field(description="その内容から推測される日本の一般的な勘定科目（通信費、接待交際費、消耗品費など）")

class InvoiceSummary(BaseModel):
    company_name: str = Field(description="請求元の会社名")
    date: str = Field(description="日付（YYYY/MM/DD形式）")
    invoice_number: str = Field(description="Tから始まる13桁の適格請求書発行事業者登録番号。ない場合は'対象外'")
    total_amount: int = Field(description="請求書の合計金額（数値のみ）")
    items: List[InvoiceItem] = Field(description="PDF内に記載されている個々の明細一覧")

st.title("🚀 爆速レシート一括仕分けシステム")
st.write("スマホやPCから写真・PDFをドロップするだけで、全自動でExcelにします。")

uploaded_files = st.file_uploader(
    "レシートや領収書の写真・PDFを選択（複数一括OK）", 
    type=["pdf", "png", "jpg", "jpeg"], 
    accept_multiple_files=True
)

if uploaded_files:
    if not GOOGLE_API_KEY:
        st.error("❌ APIキーが設定されていません。StreamlitのSecretsに GEMINI_API_KEY を設定してください。")
    elif st.button("🔥 一括スキャン開始", type="primary"):
        client = genai.Client(api_key=GOOGLE_API_KEY)
        all_data = []
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        for idx, file in enumerate(uploaded_files):
            status_text.write(f"⏳ 処理中 ({idx+1}/{len(uploaded_files)}): {file.name}")
            try:
                temp_path = f"temp_{file.name}"
                with open(temp_path, "wb") as f:
                    f.write(file.getbuffer())
                uploaded_file = client.files.upload(file=temp_path)
                
                prompt = "添付されたファイルから、指定されたスキーマに従ってすべての情報を漏れなく抽出してください。"
                response = client.models.generate_content(
                    model='gemini-2.5-flash',
                    contents=[uploaded_file, prompt],
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        response_schema=InvoiceSummary,
                    )
                )
                client.files.delete(name=uploaded_file.name)
                os.remove(temp_path)
                
                res_json = json.loads(response.text)
                for item in res_json.get("items", []):
                    all_data.append({
                        "ファイル名": file.name,
                        "会社名": res_json.get("company_name"),
                        "日付": res_json.get("date"),
                        "インボイス番号": res_json.get("invoice_number"),
                        "合計金額": res_json.get("total_amount"),
                        "明細・品目": item.get("item_name"),
                        "明細金額": item.get("amount"),
                        "推測勘定科目": item.get("account_title")
                    })
            except Exception as e:
                st.error(f"❌ エラー {file.name}: {e}")
            progress_bar.progress((idx + 1) / len(uploaded_files))
            
        status_text.write("✨ すべてのスキャンが完了しました！")
        if all_data:
            df = pd.DataFrame(all_data)
            st.dataframe(df)
            excel_buffer = io.BytesIO()
            with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
                df.to_excel(writer, index=False)
            st.download_button(
                label="📥 錬成されたExcelをダウンロード",
                data=excel_buffer.getvalue(),
                file_name="gemini_super_delivery.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
