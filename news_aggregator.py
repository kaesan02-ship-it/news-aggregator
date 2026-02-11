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

# 2. 세분화된 RSS 피드 목록 (국내/해외, 시사/IT)
RSS_FEEDS = {
    "KR_General": [ # 국내 시사
        "https://fs.jtbc.co.kr/RSS/newsflash.xml",
        "https://www.hani.co.kr/rss/",
        "https://rss.donga.com/total.xml",
    ],
    "Global_General": [ # 해외 시사
        "https://www.reutersagency.com/feed/?best-topics=top-news&post_type=best",
        "http://feeds.bbci.co.uk/news/world/rss.xml",
    ],
    "KR_Tech": [ # 국내 IT/AI
        "https://m.etnews.com/news/section_rss.html?id1=20",
        "https://www.zdnet.co.kr/rss/all.xml",
        "https://www.techm.kr/rss/all.xml",
    ],
    "Global_Tech": [ # 해외 IT/AI
        "https://openai.com/news/rss.xml",
        "https://deepmind.google/blog/rss.xml",
        "https://techcrunch.com/category/artificial-intelligence/feed/",
        "https://www.theverge.com/ai-artificial-intelligence/rss/index.xml",
    ]
}

def fetch_latest_news():
    print("Step 1: Fetching news from 4 categories...")
    news_items = []
    now = datetime.now(timezone.utc)
    lookback = now - timedelta(days=2) # 최근 2일치 수집

    for cat, urls in RSS_FEEDS.items():
        cat_items = 0
        for url in urls:
            try:
                feed = feedparser.parse(url)
                for entry in feed.entries:
                    pub = entry.get("published_parsed") or entry.get("updated_parsed")
                    if pub:
                        dt = datetime(*pub[:6], tzinfo=timezone.utc)
                        if dt > lookback:
                            news_items.append({"category": cat, "title": entry.title, "link": entry.link})
                            cat_items += 1
            except: continue
        print(f"- {cat}: {cat_items} items added.")
    
    print(f"Total {len(news_items)} news items found.")
    return news_items

def summarize_with_gemini(news_items):
    print("Step 2: Summarizing with Gemini (Dynamic Model Selection)...")
    if not news_items: return "뉴스가 없습니다."
    if not GEMINI_API_KEY: return "API 키가 설정되지 않았습니다."
    
    genai.configure(api_key=GEMINI_API_KEY.strip())
    
    # 가용 모델 자동 감지
    available_models = []
    try:
        for m in genai.list_models():
            if 'generateContent' in m.supported_generation_methods:
                available_models.append(m.name.replace('models/', ''))
    except Exception as e:
        return f"API 모델 리스트 확보 실패: {e}"

    # 우선순위 큐
    targets = ['gemini-1.5-flash', 'gemini-1.5-flash-latest', 'gemini-2.0-flash', 'gemini-pro']
    test_queue = [m for m in targets if m in available_models] + [m for m in available_models if m not in targets]

    # 세분화된 요약 프롬프트
    prompt = f"""당신은 전문 뉴스 큐레이터입니다. 아래 제공된 뉴스 목록을 바탕으로 '오늘의 4대 핵심 요약'을 작성해 주세요.

요청 사항:
1. 다음 4가지 섹션으로 나누어 각 섹션별로 가장 중요한 뉴스 5건씩(총 20건 이내) 선정하여 요약하세요.
   - 🇰🇷 국내 주요 시사 (KR_General 소스 활용)
   - 🌎 해외 주요 시사 (Global_General 소스 활용)
   - 💻 국내 IT/AI 소식 (KR_Tech 소스 활용)
   - 🤖 해외 IT/AI 소식 (Global_Tech 소스 활용)
2. 각 뉴스 끝에는 반드시 [원문보기](링크)를 포함하세요.
3. 섹션별로 가독성 좋게 구분하고, 제목에는 이모지를 사용하세요.
4. 다정하고 전문적인 한국어로 작성하세요.

뉴스 데이터:
"""
    for item in news_items:
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
    
    # 디스코드 메시지 길이 제한(2000자) 대응
    if len(content) > 1900:
        content = content[:1850] + "\n\n...(내용이 길어 일부 생략되었습니다)"

    data = {"content": "📢 **실시간 뉴스 및 AI 소식 맞춤형 요약**\n\n" + content, "username": "AI 뉴스 비서"}
    try:
        res = requests.post(DISCORD_WEBHOOK_URL.strip(), json=data, timeout=15)
        if res.status_code == 204: print("Discord 전송 완료!")
        else: print(f"Discord 전송 실패 ({res.status_code}): {res.text}")
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
