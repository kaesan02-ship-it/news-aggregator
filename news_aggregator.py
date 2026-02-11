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

# 2. 세분화된 RSS 피드 목록 (국내/해외/시사/IT)
RSS_FEEDS = {
    "KR_General": [
        "https://fs.jtbc.co.kr/RSS/newsflash.xml",
        "https://www.hani.co.kr/rss/",
        "https://rss.donga.com/total.xml",
    ],
    "Global_General": [
        "https://www.reutersagency.com/feed/?best-topics=top-news&post_type=best",
        "http://feeds.bbci.co.uk/news/world/rss.xml",
    ],
    "KR_Tech": [
        "https://m.etnews.com/news/section_rss.html?id1=20",
        "https://www.zdnet.co.kr/rss/all.xml",
        "https://www.techm.kr/rss/all.xml",
    ],
    "Global_Tech": [
        "https://openai.com/news/rss.xml",
        "https://deepmind.google/blog/rss.xml",
        "https://techcrunch.com/category/artificial-intelligence/feed/",
        "https://www.theverge.com/ai-artificial-intelligence/rss/index.xml",
        "https://www.unite.ai/feed/",
        "https://www.aitidbits.com/rss",
    ]
}

def fetch_latest_news():
    print("Step 1: Fetching news...")
    news_items = []
    now = datetime.now(timezone.utc)
    lookback = now - timedelta(days=2)
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
    return news_items

def summarize_with_gemini(news_items):
    print("Step 2: Summarizing with Gemini (Discord Optimized)...")
    if not news_items: return "뉴스가 없습니다."
    if not GEMINI_API_KEY: return "API 키가 설정되지 않았습니다."
    
    genai.configure(api_key=GEMINI_API_KEY.strip())
    
    available_models = []
    try:
        for m in genai.list_models():
            if 'generateContent' in m.supported_generation_methods:
                available_models.append(m.name.replace('models/', ''))
    except Exception as e: return f"API 모델 리스트 확보 실패: {e}"

    targets = ['gemini-1.5-flash', 'gemini-2.0-flash', 'gemini-pro']
    test_queue = [m for m in targets if m in available_models] + [m for m in available_models if m not in targets]

    # [핵심] 간소화된 1~2줄 요약 양식
    prompt = f"""당신은 전문 뉴스 큐레이터입니다. 아래 뉴스 목록을 바탕으로 '오늘의 핵심 브리핑'을 작성해 주세요.

요청 사항:
1. 다음 4가지 섹션별로 가장 중요한 뉴스 3~4건씩 선정하세요.
   - 🇰🇷 국내 주요 시사 (KR_General)
   - 🌎 해외 주요 시사 (Global_General)
   - 💻 국내 IT/AI 소식 (KR_Tech)
   - 🤖 해외 IT/AI 트렌드 (Global_Tech - 바이브 코딩 등 최신 이슈 포함)
2. 각 뉴스 형식: 
   - **[제목]** (이모지 포함)
   - 요약: 1~2줄의 핵심 설명
   - 원문: [원문보기](링크)
3. 전체 내용이 디스코드 글자 수 제한(2000자)을 넘지 않도록 간결하게 작성하세요. 불필요한 서론/결론은 뺍니다.

뉴스 데이터:
"""
    for item in news_items:
        prompt += f"- [{item['category']}] {item['title']} (링크: {item['link']})\n"

    for model_name in test_queue:
        try:
            print(f"Attempting model: {model_name}")
            model = genai.GenerativeModel(model_name)
            return model.generate_content(prompt).text
        except: continue
    return "모든 모델 시도 실패."

def send_to_discord(content):
    print("Step 3: Sending to Discord...")
    if not DISCORD_WEBHOOK_URL: return
    
    # 디스코드 제한 대응 (여전히 2000자 제한은 있으나 요약이 짧아져서 덜 잘릴 겁니다)
    if len(content) > 1950:
        content = content[:1900] + "\n\n...(디스코드 제한으로 하단 생략)"

    data = {"content": "📢 **오늘의 핵심 뉴스 브리핑**\n\n" + content, "username": "AI 뉴스 큐레이터"}
    try:
        requests.post(DISCORD_WEBHOOK_URL.strip(), json=data, timeout=15)
        print("Success!")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    try:
        news = fetch_latest_news()
        summary = summarize_with_gemini(news)
        send_to_discord(summary)
    except Exception:
        traceback.print_exc()
        sys.exit(1)
