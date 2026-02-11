import os
import feedparser
import requests
import google.generativeai as genai
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv

# 환경 변수 로드 (로컬 테스트용)
load_dotenv()

# 설정
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# RSS 피드 목록 (더 다양하고 활발한 소스 추가)
RSS_FEEDS = {
    "AI News": [
        "[https://openai.com/news/rss.xml](https://openai.com/news/rss.xml)",
        "[https://deepmind.google/blog/rss.xml](https://deepmind.google/blog/rss.xml)",
        "[https://machinelearning.apple.com/rss.xml](https://machinelearning.apple.com/rss.xml)",
        "[https://techcrunch.com/category/artificial-intelligence/feed/](https://techcrunch.com/category/artificial-intelligence/feed/)",
        "[https://www.theverge.com/ai-artificial-intelligence/rss/index.xml](https://www.theverge.com/ai-artificial-intelligence/rss/index.xml)",
    ],
    "IT/Tech": [
        "[https://m.etnews.com/news/section_rss.html?id1=20](https://m.etnews.com/news/section_rss.html?id1=20)", # 전자신문 IT
        "[https://www.zdnet.co.kr/rss/all.xml](https://www.zdnet.co.kr/rss/all.xml)",
        "[https://feeds.feedburner.com/TheHackersNews](https://feeds.feedburner.com/TheHackersNews)",
    ],
    "General News": [
        "[https://fs.jtbc.co.kr/RSS/newsflash.xml](https://fs.jtbc.co.kr/RSS/newsflash.xml)", # JTBC 속보
        "[https://www.hani.co.kr/rss/](https://www.hani.co.kr/rss/)", # 한겨레
        "[https://www.reutersagency.com/feed/?best-topics=top-news&post_type=best](https://www.reutersagency.com/feed/?best-topics=top-news&post_type=best)",
    ]
}

def fetch_latest_news():
    """뉴스를 RSS에서 수집합니다. 기본 24시간, 없으면 48시간까지 확장합니다."""
    news_items = []
    now = datetime.now(timezone.utc)
    
    # 두 번 시도 (24시간 -> 48시간)
    for lookback_days in [1, 2]:
        yesterday = now - timedelta(days=lookback_days)
        news_items = [] # 초기화

        for category, urls in RSS_FEEDS.items():
            for url in urls:
                try:
                    feed = feedparser.parse(url)
                    for entry in feed.entries:
                        published = entry.get("published_parsed") or entry.get("updated_parsed")
                        if published:
                            dt = datetime(*published[:6], tzinfo=timezone.utc)
                            if dt > yesterday:
                                news_items.append({
                                    "category": category,
                                    "title": entry.title,
                                    "description": entry.get("description", ""),
                                    "link": entry.link
                                })
                except:
                    continue
        
        if news_items:
            break
    
    return news_items

def summarize_with_gemini(news_items):
    """현재 API 키에서 사용 가능한 모델을 자동으로 찾아 요약을 시도합니다."""
    if not news_items:
        return "최근 24시간 동안의 새로운 뉴스가 없습니다."

    genai.configure(api_key=GEMINI_API_KEY)
    
    # 1. 사용 가능한 모델 목록 가져오기
    available_models = []
    try:
        for m in genai.list_models():
            if 'generateContent' in m.supported_generation_methods:
                # 'models/' 접두사 제거한 순수 이름 추가
                name = m.name.replace('models/', '')
                available_models.append(name)
    except Exception as e:
        return f"가용 모델 목록을
