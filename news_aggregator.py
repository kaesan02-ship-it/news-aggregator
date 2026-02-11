import os
import sys
import traceback
import feedparser
import requests
import google.generativeai as genai
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv

# 1. 환경 변수 로드
load_dotenv()
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

RSS_FEEDS = {
    "AI News": [
        "https://openai.com/news/rss.xml",
        "https://deepmind.google/blog/rss.xml",
        "https://techcrunch.com/category/artificial-intelligence/feed/",
    ],
    "IT/Tech": [
        "https://m.etnews.com/news/section_rss.html?id1=20",
        "https://www.zdnet.co.kr/rss/all.xml",
    ],
    "General": [
        "https://fs.jtbc.co.kr/RSS/newsflash.xml",
        "https://www.hani.co.kr/rss/",
    ]
}

def fetch_latest_news():
    print("Step 1: Fetching news...")
    news_items = []
    now = datetime.now(timezone.utc)
    lookback = now - timedelta(days=2) # 넉넉하게 2일치
    for cat, urls in RSS_FEEDS.items():
        for url in urls:
            try:
                feed = feedparser.parse(url)
                for entry in feed.entries:
                    pub = entry.get("published_parsed") or entry.get("updated_parsed")
                    if pub:
                        dt = datetime(*pub[:6], tzinfo=timezone.utc)
                        if dt > lookback:
                            news_items.append({"category": cat, "title": entry.title, "link": entry.link})
            except: continue
    print(f"Total {len(news_items)} news items found.")
    return news_items

def summarize_with_gemini(news_items):
    print("Step 2: Summarizing with Gemini...")
    if not news_items: return "뉴스가 없습니다."
    if not GEMINI_API_KEY: return "API 키가 설정되지 않았습니다."
    
    genai.configure(api_key=GEMINI_API_KEY.strip())
    
    try:
        available_models = [m.name.replace('models/', '') for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
        print(f"Available models: {available_models}")
    except Exception as e:
        return f"API 키 인증 오류나 권한 이슈가 의심됩니다: {e}"

    # 우선순위: 1.5-flash -> 2.0-flash -> pro
    targets = ['gemini-1.5-flash', 'gemini-1.5-flash-latest', 'gemini-2.0-flash', 'gemini-pro']
    test_queue = [m for m in targets if m in available_models] + [m for m in available_models if m not in targets]

    prompt = "오늘의 주요 뉴스들을 카테고리별로 친절하게 요약해 주세요. 각 요약 끝에는 [원문보기](링크)를 넣어주세요.\n\n"
    for item in news_items[:10]:
        prompt += f"- [{item['category']}] {item['title']} (링크: {item['link']})\n"

    for model_name in test_queue:
        try:
            print(f"Attempting model: {model_name}")
            model = genai.GenerativeModel(model_name)
            return model.generate_content(prompt).text
        except Exception as e:
            print(f"Model {model_name} failed: {e}")
            continue
    return "모든 모델 시도 실패."

def send_to_discord(content):
    print("Step 3: Sending to Discord...")
    if not DISCORD_WEBHOOK_URL:
        print("Error: DISCORD_WEBHOOK_URL is missing.")
        return
    data = {"content": content, "username": "AI 뉴스 비서"}
    try:
        res = requests.post(DISCORD_WEBHOOK_URL.strip(), json=data, timeout=10)
        if res.status_code == 204: print("Success!")
        else: print(f"Failed ({res.status_code}): {res.text}")
    except Exception as e:
        print(f"Discord 전송 중 오류 발생: {e}")

if __name__ == "__main__":
    try:
        news = fetch_latest_news()
        summary = summarize_with_gemini(news)
        send_to_discord(summary)
    except Exception:
        print("!!! 치명적 오류 발생 !!!")
        traceback.print_exc()
        sys.exit(1)
