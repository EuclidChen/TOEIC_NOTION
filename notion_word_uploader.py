# ✅ 自動單字記憶生成 + 上傳 Notion 工具（GPT 4 新版 API）+ Web UI 介面
# 放置於：C:\Users\Euclid Chen\Documents\privacy\TOEIC

import os
import pandas as pd
import time
import json
from dotenv import load_dotenv
from notion_client import Client
from openai import OpenAI
import streamlit as st
from datetime import datetime, timedelta, timezone




# 載入 .env 環境變數
load_dotenv()

NOTION_TOKEN = os.getenv("NOTION_TOKEN")
DATABASE_ID = os.getenv("NOTION_DATABASE_ID")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

client = OpenAI(api_key=OPENAI_API_KEY)
notion = Client(auth=NOTION_TOKEN)

st.set_page_config(page_title="多益單字上傳器", layout="wide")
st.title("🧠 多益單字記憶生成器 + 自動上傳 Notion")

# 📅 顯示今日應複習單字功能
if st.button("📅 今天要複習哪些單字？"):
    today = datetime.now(timezone.utc)  # 改為 offset-aware datetime
    notion_data = notion.databases.query(database_id=DATABASE_ID)
    results = notion_data["results"]

    words_due = []

    for page in results:
        props = page["properties"]
        title = props["Word"]["title"][0]["text"]["content"] if props["Word"]["title"] else ""
        review_tags = [tag["name"] for tag in props["Review"]["multi_select"]]
        created_time = datetime.fromisoformat(page["created_time"].replace("Z", "+00:00"))
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

words_input = st.text_area("請輸入單字（可多個，請用逗號或換行分隔）")
submit = st.button("🚀 產生並上傳")

status_container = st.container()
success_list = []
fail_list = []

if submit and words_input:
    vocab_list = [w.strip() for w in words_input.replace('\n', ',').split(',') if w.strip()]

    def generate_word_info(word):
        prompt = f"""
請針對多益單字「{word}」產出以下內容：

1. 詞性與中文意思（例如：n. 飛機）
2. 記憶錨點（用聯想、拆字、諧音、情境等方式讓人記得單字）
3. 與 TOEIC 相關的例句（3 句，每句附上中文翻譯）
4. 一個 YouTube 歌詞或影片連結（與此單字有情境連結）
5. 語意網路（列出 2~3 個同義詞＋說明差異＋常見詞組＋3個搭配例句）

請用以下 JSON 格式輸出，注意所有欄位的內容必須為純文字格式：
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
                model="gpt-4",
                messages=[
                    {"role": "system", "content": "你是位多益單字記憶設計專家，擅長幫助記憶與語意聯想。"},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7,
            )
            content = res.choices[0].message.content
            result = json.loads(content.strip())
            return result
        except Exception as e:
            fail_list.append((word, f"GPT 生成失敗：{e}"))
            return None

    data = []
    for word in vocab_list:
        status_container.info(f"🔍 正在處理：{word}")
        result = generate_word_info(word)
        if result:
            data.append(result)
        time.sleep(2)

    if data:
        df = pd.DataFrame(data)
        timestamp = datetime.now().strftime("%Y%m%d%H%M")
        output_dir = os.path.join(os.path.dirname(__file__), "outputs")
        os.makedirs(output_dir, exist_ok=True)
        output_path = os.path.join(output_dir, f"output_today_{timestamp}.csv")
        df.to_csv(output_path, index=False, encoding='utf-8-sig')
        status_container.success(f"📁 CSV 已儲存：{output_path}")

        for row in data:
            try:
                notion.pages.create(
                    parent={"database_id": DATABASE_ID},
                    properties={
                        "Word": {"title": [{"text": {"content": str(row['Word'])}}]},
                        "Part of Speech": {"select": {"name": str(row['Part of Speech'])}},
                        "Chinese": {"rich_text": [{"text": {"content": str(row['Chinese'])}}]},
                        "Anchor": {"rich_text": [{"text": {"content": str(row['Anchor'])}}]},
                        "Video": {"url": str(row['Video'])},
                        "Semantic": {"rich_text": [{"text": {"content": str(row['Semantic']).replace('. ', '.\n')}}]},
                        "Example 1": {"rich_text": [{"text": {"content": str(row['Example1'])}}]},
                        "Example 2": {"rich_text": [{"text": {"content": str(row['Example2'])}}]},
                        "Example 3": {"rich_text": [{"text": {"content": str(row['Example3'])}}]},
                        "Review": {"multi_select": [{"name": tag.strip()} for tag in row['Review'].split(',')]}
                    }
                )
                success_list.append(row['Word'])
            except Exception as e:
                fail_list.append((row['Word'], f"上傳失敗：{e}"))

        with st.expander("📈 執行結果總結", expanded=True):
            st.markdown(f"### ✅ 成功上傳：{len(success_list)} 筆")
            for word in success_list:
                st.markdown(f"- {word}")

            if fail_list:
                st.markdown(f"### ❌ 發生錯誤：{len(fail_list)} 筆")
                for word, err in fail_list:
                    st.markdown(f"- {word}：{err}")
    else:
        st.warning("⚠️ 沒有任何資料產出！")
