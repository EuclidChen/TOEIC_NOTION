import os
import pandas as pd
import time
import json
from dotenv import load_dotenv
from notion_client import Client
from openai import OpenAI
import streamlit as st
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
import matplotlib.pyplot as plt

# 載入 .env 環境變數
load_dotenv()

NOTION_TOKEN = os.getenv("NOTION_TOKEN")
DATABASE_ID = os.getenv("NOTION_DATABASE_ID")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

client = OpenAI(api_key=OPENAI_API_KEY)
notion = Client(auth=NOTION_TOKEN)

st.set_page_config(page_title="多益單字工具整合", layout="wide")
st.title("🧠 多益單字記憶工具整合平台")

# 建立分頁
tabs = st.tabs(["📤 單字上傳", "📅 今日複習", "📊 單字統計", "📈 每日新增單字"])

#📤 單字上傳
with tabs[0]:
    st.header("📤 單字上傳功能")

    # -- 新：使用 st.form(clear_on_submit=True) --
    with st.form("upload_form", clear_on_submit=True):
        words_input = st.text_area(
            "請輸入單字（可多個，請用逗號或換行分隔）",
            key="words_input",
            placeholder="例如：allocate, consolidate, substantial",
            height=150
        )
        submit = st.form_submit_button("🚀 產生並上傳")

    status_container = st.container()          # 動態訊息顯示
    success_list, fail_list = [], []           # 成功／失敗紀錄

    # 只有按下按鈕且輸入非空時才繼續
    if submit and words_input:
        vocab_list = [w.strip()
                      for w in words_input.replace("\n", ",").split(",")
                      if w.strip()]

        # ---------- GPT 產生資訊 ----------
        def generate_word_info(word: str) -> dict | None:
            prompt = f"""
請針對多益單字「{word}」產出以下內容：

1. 詞性與中文意思（例如：n. 飛機）
2. 記憶錨點（用聯想、拆字、諧音、情境等方式讓人記得單字）
3. 與 TOEIC 相關的例句（3 句，每句附上中文翻譯）
4. 一個 YouTube 歌詞或影片連結（與此單字有情境連結）
5. 語意網路（列出 2~3 個同義詞＋說明差異＋常見詞組＋3個搭配例句）

請用以下 JSON 格式輸出，所有欄位必須為純文字：
{{
  "Word": "{word}",
  "Part of Speech": "",
  "Chinese": "",
  "Anchor": "",
  "Video": "",
  "Semantic": "",
  "Example1": "",
  "Example2": "",
  "Example3": "",
  "Review": "D2,D4,D7,D14,D30"
}}
"""
            try:
                res = client.chat.completions.create(
                    model="gpt-4",             # 速度較快，視需要改回 gpt-4
                    messages=[
                        {"role": "system",
                         "content": "你是多益單字記憶設計專家，擅長幫助記憶與語意聯想。"},
                        {"role": "user", "content": prompt}
                    ],
                    temperature=0.7,
                )
                content = res.choices[0].message.content
                return json.loads(content.strip())
            except Exception as e:
                fail_list.append((word, f"GPT 生成失敗：{e}"))
                return None
        # ------------------------------------

        data = []
        for word in vocab_list:
            status_container.info(f"🔍 正在處理：{word}")
            result = generate_word_info(word)
            if result:
                data.append(result)
            time.sleep(1.5)   # 避免過度呼叫

        # ---------- 若有成功資料 ----------
        if data:
            df = pd.DataFrame(data)

            # 1) 先存成 CSV
            timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
            output_dir = os.path.join(os.path.dirname(__file__), "outputs")
            os.makedirs(output_dir, exist_ok=True)
            output_path = os.path.join(output_dir,
                                       f"output_today_{timestamp}.csv")
            df.to_csv(output_path, index=False, encoding="utf-8-sig")
            status_container.success(f"📁 CSV 已儲存：{output_path}")

            # 2) 逐筆寫入 Notion
            for row in data:
                try:
                    notion.pages.create(
                        parent={"database_id": DATABASE_ID},
                        properties={
                            "Word": {
                                "title": [{"text": {"content": row["Word"]}}]},
                            "Part of Speech": {
                                "select": {"name": row["Part of Speech"]}},
                            "Chinese": {
                                "rich_text": [{"text": {
                                    "content": row["Chinese"]}}]},
                            "Anchor": {
                                "rich_text": [{"text": {
                                    "content": row["Anchor"]}}]},
                            "Video": {"url": row["Video"]},
                            "Semantic": {
                                "rich_text": [{"text": {
                                    "content": row["Semantic"].replace(". ", ".\n")}}]},
                            "Example 1": {
                                "rich_text": [{"text": {
                                    "content": row["Example1"]}}]},
                            "Example 2": {
                                "rich_text": [{"text": {
                                    "content": row["Example2"]}}]},
                            "Example 3": {
                                "rich_text": [{"text": {
                                    "content": row["Example3"]}}]},
                            "Review": {
                                "multi_select": [{"name": t.strip()}
                                                 for t in row["Review"].split(",")]}
                        }
                    )
                    success_list.append(row["Word"])
                except Exception as e:
                    fail_list.append((row["Word"], f"上傳失敗：{e}"))

            # 3) 結果摘要
            with st.expander("📈 執行結果總結", expanded=True):
                st.markdown(f"### ✅ 成功上傳：{len(success_list)} 筆")
                for w in success_list:
                    st.markdown(f"- {w}")

                if fail_list:
                    st.markdown(f"### ❌ 發生錯誤：{len(fail_list)} 筆")
                    for w, err in fail_list:
                        st.markdown(f"- {w}：{err}")
        else:
            st.warning("⚠️ 沒有任何資料產出！")


# 📅 今日複習
with tabs[1]:
    st.header("📅 今日應複習單字")
    if st.button("📅 今天要複習哪些單字？"):
        tz_tw = ZoneInfo("Asia/Taipei")
        today = datetime.now(tz=tz_tw).replace(hour=0, minute=0, second=0, microsecond=0)
        notion_data = notion.databases.query(database_id=DATABASE_ID)
        results = notion_data["results"]

        words_due = []

        for page in results:
            props = page["properties"]
            title = props["Word"]["title"][0]["text"]["content"] if props["Word"]["title"] else ""
            review_tags = [tag["name"] for tag in props["Review"]["multi_select"]]
            created_time = datetime.fromisoformat(page["created_time"].replace("Z", "+00:00")).astimezone(tz_tw).replace(hour=0, minute=0, second=0, microsecond=0)
            day_diff = (today - created_time).days
            tag_today = f"D{day_diff}"
            if tag_today in review_tags:
                words_due.append((title, tag_today))

        if words_due:
            st.subheader("✅ 今日應複習：")
            for word, tag in words_due:
                st.markdown(f"- **{word}**（標註：{tag}）")
        else:
            st.info("今天沒有符合的複習單字 ✅")

# 📊 單字統計看板
with tabs[2]:
    st.header("📊 單字統計看板")
    try:
        notion_data = notion.databases.query(database_id=DATABASE_ID)
        results = notion_data["results"]
        st.markdown(f"**目前總共有 {len(results)} 筆單字**")
        tag_counter = {"D2": 0, "D4": 0, "D7": 0, "D14": 0, "D30": 0}
        for page in results:
            tags = page["properties"]["Review"]["multi_select"]
            for tag in tags:
                if tag["name"] in tag_counter:
                    tag_counter[tag["name"]] += 1
        for tag, count in tag_counter.items():
            st.markdown(f"- {tag}：{count} 筆")
    except Exception as e:
        st.error(f"統計資料讀取失敗：{e}")

# 📈 每日新增單字
with tabs[3]:
    st.header("📈 每日新增單字數量")
    try:
        tz_tw = ZoneInfo("Asia/Taipei")
        results = notion.databases.query(database_id=DATABASE_ID)["results"]
        date_counts = {}
        for page in results:
            created_time = datetime.fromisoformat(page["created_time"].replace("Z", "+00:00"))
            local_date = created_time.astimezone(tz_tw).date()
            date_counts[local_date] = date_counts.get(local_date, 0) + 1

        df = pd.DataFrame(list(date_counts.items()), columns=["Date", "Count"]).sort_values("Date")
        df["Date"] = pd.to_datetime(df["Date"])

        st.bar_chart(data=df, x="Date", y="Count")
        st.success("✅ 成功產出每日新增統計圖")
    except Exception as e:
        st.error(f"❌ 發生錯誤：{e}")
