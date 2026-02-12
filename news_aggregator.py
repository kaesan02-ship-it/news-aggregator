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

# 2. RSS 피드 목록
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
    print("Step 2: Summarizing with Gemini (Strictly Data-Driven)...")
    if not news_items: return ""
    genai.configure(api_key=GEMINI_API_KEY.strip())
    
    available_models = []
    try:
        for m in genai.list_models():
            if 'generateContent' in m.supported_generation_methods:
                available_models.append(m.name.replace('models/', ''))
    except: return ""

    targets = ['gemini-1.5-flash', 'gemini-2.0-flash', 'gemini-pro']
    test_queue = [m for m in targets if m in available_models] + [m for m in available_models if m not in targets]

    # [데이터 기반] 외부 지식 배제 및 뉴스 데이터 충실 요약 프롬프트
    prompt = f"""당신은 제공된 정보에만 기반하여 객관적으로 요약하는 전문 뉴스 큐레이터입니다.
현재 시점({datetime.now().strftime('%Y-%m-%d')})의 최신 뉴스들을 바탕으로 브리핑을 작성해 주세요.

요청 사항:
1. **[데이터 중심 요약]** 당신의 외부 지식이나 과거 정보를 절대 섞지 마세요. 제공된 '뉴스 데이터'에 적힌 인물의 성함과 직함을 그대로 사용하여 요약하세요. 
2. **[섹션별 3건 선정]** 아래 카테고리별로 가장 중요한 뉴스 '딱 3건씩'만 선정하세요. (총 12건)
3. **[출력 양식]** 메시지 분할 전송을 위해 아래 구분자를 반드시 포함하세요.

---SECTION: GENERAL---
(국내 시사 3건, 해외 시사 3건)
- **[카테고리] 뉴스제목**
  요약: 제공된 뉴스 내용 기반 1~2줄 요약
  원문: [원문보기](링크)

---SECTION: TECH---
(국내 IT 3건, 해외 IT 3건)
형식 동일

뉴스 데이터:
"""
    for item in news_items:
        prompt += f"- [{item['category']}] {item['title']} (링크: {item['link']})\n"

    for model_name in test_queue:
        try:
            model = genai.GenerativeModel(model_name)
            return model.generate_content(prompt).text
        except: continue
    return ""

def send_to_discord(full_content):
    print("Step 3: Sending to Discord (Multi-Message)...")
    if not DISCORD_WEBHOOK_URL or not full_content: return
    
    parts = full_content.split("---SECTION: ")
    for part in parts:
        if not part.strip(): continue
        
        header = ""
        if "GENERAL" in part:
            header = "📢 **오늘의 주요 시사 브리핑 (국내/해외)**\n\n"
            clean_content = part.replace("GENERAL---", "").strip()
        elif "TECH" in part:
            header = "🤖 **오늘의 IT/AI 및 핵심 트렌드 (국내/해외)**\n\n"
            clean_content = part.replace("TECH---", "").strip()
        else:
            header = "📝 **기타 소식**\n\n"
            clean_content = part.strip()
            
        data = {"content": header + clean_content, "username": "AI 뉴스 큐레이터"}
        try:
            requests.post(DISCORD_WEBHOOK_URL.strip(), json=data, timeout=15)
        except: print("Send error")

if __name__ == "__main__":
    try:
        news = fetch_latest_news()
        summary = summarize_with_gemini(news)
        send_to_discord(summary)
    except:
        traceback.print_exc()
        sys.exit(1)
