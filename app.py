import streamlit as st
import pandas as pd
import numpy as np
import io
import re
import base64
from datetime import datetime
from PIL import Image, ImageOps, ImageFilter

import pytesseract

# =====================================================================================
# RECEIPT-AI (LOCAL / NO-API EDITION)
# ---------------------------------------------------------------------------
# 元コードは Gemini API (LLM Vision) にレシート画像を送信して構造化 JSON を
# 得ていましたが、本バージョンは外部 AI API を一切呼び出さず、
#   1) ローカル OCR (Tesseract, 日本語学習データ) で文字を読み取り
#   2) 正規表現 + ルールベースの日本の領収書フォーマット知識
# だけで同等のスキーマを再現します。
#
# 精度についての正直な注意:
#   LLM Vision (Gemini など) は文脈を理解して欠落・かすれた文字を推測したり、
#   表形式の崩れたレイアウトも柔軟に解釈できます。
#   ルールベースの OCR パーサーは「典型的なレイアウトの整った印字レシート」
#   では高精度になりますが、手書き文字・极端に歪んだレイアウト・非定型の
#   フォーマットでは抽出漏れ・誤抽出が増えます。
#   本ツールでは「読み取れない・存在しない項目は空欄にする」というルールを
#   徹底し、誤った数値を"推測"して埋めることは避けています。
# =====================================================================================

st.set_page_config(
    page_title="RECEIPT-AI: LOCAL SCANNER (NO API)",
    layout="centered",  # スマホでの表示崩れを防ぐため centered に変更
)

st.title("RECEIPT-AI: LOCAL SCANNER (No External API)")
st.caption(
    "外部 AI API (Gemini 等) を使わず、ローカル OCR (Tesseract) + ルールベース解析だけで"
    "領収書 / レシート画像から構造化データを抽出します。"
)

with st.sidebar:
    st.subheader("設定パネル")
    ocr_lang = st.selectbox("OCR 言語", ["jpn+eng", "jpn", "eng"], index=0)
    upscale = st.slider("画像拡大率（OCR精度向上用）", 1.0, 3.0, 2.0, 0.5)
    binarize_thresh = st.slider("二値化しきい値（0=自動/大津の方法）", 0, 255, 0, 1)
    show_raw_text = st.checkbox("OCR生テキストも表示する", value=False)
    st.markdown("---")
    st.markdown(
        "**デプロイ時の注意（Streamlit Cloud等）**\n\n"
        "`packages.txt` に以下を追加してください:\n\n"
        "```\ntesseract-ocr\ntesseract-ocr-jpn\n```\n\n"
        "`requirements.txt` には以下が必要です:\n\n"
        "```\nstreamlit\npandas\nnumpy\npillow\npytesseract\nopenpyxl\n```"
    )

# ------------------------------------------------------------------
# 画像前処理
# ------------------------------------------------------------------
def preprocess_image(img: Image.Image, upscale: float, thresh: int, target_long_side: int = 1800) -> Image.Image:
    img = ImageOps.exif_transpose(img)  # スマホ写真の回転情報(EXIF)を正しい向きに補正
    img = img.convert("L")  # グレースケール

    w, h = img.size
    long_side = max(w, h)

    if long_side > target_long_side:
        # スマホカメラの高解像度写真は処理が重くなるため、長辺を基準サイズまで縮小
        scale = target_long_side / long_side
        img = img.resize((max(1, int(w * scale)), max(1, int(h * scale))), Image.LANCZOS)
    elif upscale and upscale != 1.0:
        # 元画像が小さい（低解像度スキャン等）場合のみ拡大してOCR精度を上げる
        img = img.resize((int(w * upscale), int(h * upscale)), Image.LANCZOS)

    img = img.filter(ImageFilter.MedianFilter(size=3))  # ノイズ除去

    arr = np.array(img)
    if thresh and thresh > 0:
        arr = np.where(arr > thresh, 255, 0).astype("uint8")
    else:
        # 大津の方法（外部ライブラリなしの簡易実装）
        hist, _ = np.histogram(arr, bins=256, range=(0, 256))
        total = arr.size
        sum_all = np.dot(np.arange(256), hist)
        sum_b, w_b, max_var, best_t = 0.0, 0, 0.0, 128
        for t in range(256):
            w_b += hist[t]
            if w_b == 0:
                continue
            w_f = total - w_b
            if w_f == 0:
                break
            sum_b += t * hist[t]
            m_b = sum_b / w_b
            m_f = (sum_all - sum_b) / w_f
            var_between = w_b * w_f * (m_b - m_f) ** 2
            if var_between > max_var:
                max_var = var_between
                best_t = t
        arr = np.where(arr > best_t, 255, 0).astype("uint8")

    return Image.fromarray(arr)


def ocr_image(img: Image.Image, lang: str) -> str:
    config = "--oem 3 --psm 6"
    return pytesseract.image_to_string(img, lang=lang, config=config)


# ------------------------------------------------------------------
# フィールド抽出（ルールベース）
# ------------------------------------------------------------------
NUM_RE = r"[\d,，]+"

def _to_int(num_str: str):
    if not num_str:
        return None
    cleaned = re.sub(r"[,，円¥]", "", num_str).strip()
    if not cleaned.isdigit():
        return None
    return int(cleaned)


def parse_date(text: str) -> str:
    # 西暦: 2026年3月15日 / 2026/3/15 / 2026-03-15 / 2026.03.15
    m = re.search(r"(20\d{2})[年/\-.](\d{1,2})[月/\-.](\d{1,2})", text)
    if m:
        y, mo, d = m.groups()
        try:
            return f"{int(y):04d}/{int(mo):02d}/{int(d):02d}"
        except ValueError:
            pass

    # 令和: 令和6年3月15日 (令和1年 = 2019年)
    m = re.search(r"令和\s*(\d{1,2})年\s*(\d{1,2})月\s*(\d{1,2})日", text)
    if m:
        reiwa_y, mo, d = m.groups()
        try:
            year = 2018 + int(reiwa_y)
            return f"{year:04d}/{int(mo):02d}/{int(d):02d}"
        except ValueError:
            pass

    return ""


def parse_vendor_name(text: str) -> str:
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    # 電話番号・住所・日付・記号のみの行を除外し、最初の実質的な行を店名とみなす
    skip_patterns = [
        r"^\d{2,4}-\d{2,4}-\d{3,4}$",
        r"^(TEL|FAX|〒|℡)",
        r"^\d{3}-\d{4}",
        r"領収書|レシート|receipt",
        r"^[\-=＝ー]+$",
    ]
    for line in lines[:8]:
        if any(re.search(p, line, re.IGNORECASE) for p in skip_patterns):
            continue
        if len(line) >= 2:
            return line
    return lines[0] if lines else ""


def parse_total_amount(text: str):
    lines = text.splitlines()
    candidates = []
    total_keywords = ["合計", "御会計", "お会計", "ご請求", "総計", "total"]
    for i, line in enumerate(lines):
        low = line.lower()
        if any(k.lower() in low for k in total_keywords) and "小計" not in line:
            nums = re.findall(NUM_RE, line)
            search_lines = [line]
            if not nums and i + 1 < len(lines):
                search_lines.append(lines[i + 1])
            for sline in search_lines:
                for n in re.findall(NUM_RE, sline):
                    val = _to_int(n)
                    if val:
                        candidates.append(val)
    if candidates:
        # 複数ヒットした場合、最も大きい額を合計とみなす（税抜小計より税込合計が大きい前提）
        return max(candidates)
    return None


def parse_tax_amounts(text: str):
    tax_10 = None
    tax_8 = None
    lines = text.splitlines()
    for i, line in enumerate(lines):
        window = line + (" " + lines[i + 1] if i + 1 < len(lines) else "")
        if "10%" in window or "10％" in window:
            nums = [n for n in re.findall(NUM_RE, window) if "10" not in n]
            if nums:
                val = _to_int(nums[-1])
                if val:
                    tax_10 = val
        if ("8%" in window or "8％" in window) and "軽" in window or "8%" in window or "8％" in window:
            nums = [n for n in re.findall(NUM_RE, window) if n not in ("8",)]
            if nums:
                val = _to_int(nums[-1])
                if val:
                    tax_8 = val
    return tax_10, tax_8


ITEM_SKIP_KEYWORDS = [
    "合計", "小計", "お預", "預り", "釣", "お釣", "現金", "カード", "クレジット",
    "領収書", "レシート", "登録番号", "電話", "tel", "fax", "住所", "様", "点数",
    "税込", "税抜", "御買上", "ポイント", "残高", "対象",
]


def parse_items(text: str):
    items = []
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    for line in lines:
        low = line.lower()
        if any(k.lower() in low for k in ITEM_SKIP_KEYWORDS):
            continue
        # 行末に金額らしき数値があるか（例: "コーヒー 350" / "おにぎり　￥120"）
        m = re.search(r"(?P<name>.+?)\s*[¥￥]?\s*(?P<price>[\d,，]{2,7})\s*円?\*?[軽]?\s*$", line)
        if not m:
            continue
        name = m.group("name").strip(" ・:：*")
        price = _to_int(m.group("price"))
        if price is None or not name:
            continue
        if len(name) < 1 or price > 1_000_000:
            continue

        # 数量抽出 ( ×2 / x2 / 2個 / 2点 )
        qty = 1
        qm = re.search(r"[×xX]\s*(\d{1,3})", line)
        if not qm:
            qm = re.search(r"(\d{1,3})\s*[個点]", line)
        if qm:
            try:
                qty = int(qm.group(1))
            except ValueError:
                qty = 1

        # 軽減税率マーク（* や 軽 の記載）があれば8%、なければ10%と仮定
        tax_rate = 8 if ("軽" in line or "*" in line or "※" in line) else 10

        items.append({
            "item_name": name,
            "unit_price": price,
            "quantity": qty,
            "tax_rate": tax_rate,
        })
    return items


def extract_receipt_data(text: str) -> dict:
    return {
        "date": parse_date(text),
        "vendor_name": parse_vendor_name(text),
        "total_amount": parse_total_amount(text) or "",
        "tax_10_amount": (parse_tax_amounts(text)[0]) or "",
        "tax_8_amount": (parse_tax_amounts(text)[1]) or "",
        "items": parse_items(text),
    }


# ------------------------------------------------------------------
# UI（スマホ対応：ファイルアップロード or カメラ撮影を選択可能）
# ------------------------------------------------------------------
if "captured_photos" not in st.session_state:
    st.session_state["captured_photos"] = []  # [{"name": str, "bytes": bytes}, ...]

input_mode = st.radio(
    "画像の入力方法",
    ["📁 ファイルを選択", "📷 カメラで撮影"],
    horizontal=True,
)

uploaded_files = []

if input_mode == "📁 ファイルを選択":
    uploaded_files = st.file_uploader(
        "レシート画像をアップロード（複数選択可）",
        accept_multiple_files=True,
        type=["jpg", "jpeg", "png", "webp"],
    )
else:
    st.caption("1枚撮影するごとに下のリストに追加されます。複数枚まとめて撮影できます。")
    camera_key = f"camera_input_{len(st.session_state['captured_photos'])}"
    photo = st.camera_input("レシートを撮影", key=camera_key)
    if photo is not None:
        st.session_state["captured_photos"].append({
            "name": f"camera_{len(st.session_state['captured_photos']) + 1}.jpg",
            "bytes": photo.getvalue(),
        })
        st.rerun()

    if st.session_state["captured_photos"]:
        st.write(f"撮影済み: {len(st.session_state['captured_photos'])} 枚")
        thumb_cols = st.columns(4)
        for idx, shot in enumerate(st.session_state["captured_photos"]):
            with thumb_cols[idx % 4]:
                st.image(shot["bytes"], use_container_width=True)
                if st.button("削除", key=f"del_{idx}"):
                    st.session_state["captured_photos"].pop(idx)
                    st.rerun()
        if st.button("撮影した画像を全て削除"):
            st.session_state["captured_photos"] = []
            st.rerun()

# ファイルアップロードとカメラ撮影の両方を統合した処理対象リスト
# 各要素は {"name": str, "bytes": bytes} 形式に揃える
images_to_process = []
for f in (uploaded_files or []):
    images_to_process.append({"name": f.name, "bytes": f.getvalue()})
for shot in st.session_state["captured_photos"]:
    images_to_process.append(shot)

if images_to_process:
    st.info(f"処理対象: {len(images_to_process)} 枚")

if st.button("RUN SCAN", type="primary", use_container_width=True):
    if not images_to_process:
        st.error("画像がアップロード・撮影されていません。")
        st.stop()

    all_data = []
    progress = st.progress(0, text="処理を開始します...")

    for i, item in enumerate(images_to_process):
        name = item["name"]
        try:
            img = Image.open(io.BytesIO(item["bytes"]))
            processed = preprocess_image(img, upscale, binarize_thresh)
            text = ocr_image(processed, ocr_lang)

            if show_raw_text:
                with st.expander(f"OCR生テキスト: {name}"):
                    st.text(text)

            data = extract_receipt_data(text)
            data["ファイル名"] = name
            all_data.append(data)
            st.success(f"✅ 完了: {name}")

        except Exception as e:
            st.error(f"❌ 予期しないエラー ({name}): {e}")

        progress.progress((i + 1) / len(images_to_process), text=f"{i + 1}/{len(images_to_process)} 処理済み")

    if all_data:
        flat_rows = []
        item_rows = []
        for d in all_data:
            items = d.pop("items", [])
            flat_rows.append(d)
            for it in items:
                item_rows.append({"ファイル名": d.get("ファイル名"), **it})

        df_main = pd.DataFrame(flat_rows)
        preferred_cols = [
            "ファイル名", "date", "vendor_name", "total_amount",
            "tax_10_amount", "tax_8_amount",
        ]
        cols = [c for c in preferred_cols if c in df_main.columns] + \
               [c for c in df_main.columns if c not in preferred_cols]
        df_main = df_main[cols]

        st.subheader("抽出結果プレビュー")
        st.dataframe(df_main, use_container_width=True)

        if item_rows:
            st.subheader("明細プレビュー")
            st.dataframe(pd.DataFrame(item_rows), use_container_width=True)

        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
            df_main.to_excel(writer, index=False, sheet_name="領収書一覧")
            if item_rows:
                pd.DataFrame(item_rows).to_excel(writer, index=False, sheet_name="明細")

        st.download_button(
            "📥 EXCELをダウンロード",
            buffer.getvalue(),
            "receipt_data.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

        st.warning(
            "⚠️ 本ツールはローカルOCR＋ルールベース解析のため、AI Vision API（Gemini等）と比べて"
            "レイアウトが崩れたレシートや手書き文字、かすれた文字の認識精度は劣ります。"
            "特に品目（items）の抽出は表構造が単純な印字レシートでのみ安定して動作します。"
            "税務署への提出前に、必ず金額・日付などを原本と照合してください。"
            "本ツールは税務・法律上の助言を提供するものではありません。"
        )
    else:
        st.info("抽出できたデータがありませんでした。")
