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
        "https://openai.com/news/rss.xml",
        "https://deepmind.google/blog/rss.xml",
        "https://machinelearning.apple.com/rss.xml",
        "https://techcrunch.com/category/artificial-intelligence/feed/",
        "https://www.theverge.com/ai-artificial-intelligence/rss/index.xml",
    ],
    "IT/Tech": [
        "https://m.etnews.com/news/section_rss.html?id1=20", # 전자신문 IT
        "https://www.zdnet.co.kr/rss/all.xml",
        "https://feeds.feedburner.com/TheHackersNews",
    ],
    "General News": [
        "https://fs.jtbc.co.kr/RSS/newsflash.xml", # JTBC 속보
        "https://www.hani.co.kr/rss/", # 한겨레
        "https://www.reutersagency.com/feed/?best-topics=top-news&post_type=best",
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
    """뉴스 목록을 Gemini를 사용하여 요약합니다."""
    if not news_items:
        return "최근 24시간 동안의 새로운 뉴스가 없습니다."

    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel('gemini-1.5-flash-latest')

    # 프롬프트 구성
    prompt = "당신은 전문 뉴스 큐레이터입니다. 아래 제공된 뉴스 목록을 바탕으로 매일 아침 읽기 좋게 요약해 주세요.\n\n"
    prompt += "요청 사항:\n"
    prompt += "1. 카테고리별로(시사, IT, AI) 중요 소식을 그룹화하여 요약하세요.\n"
    prompt += "2. 각 주요 뉴스 뒤에 반드시 해당 뉴스의 원문 링크를 [원문보기](링크) 형식으로 포함하세요.\n"
    prompt += "3. 예시: '- [AI] OpenAI의 새로운 모델 발표 [원문보기](https://...)'\n"
    prompt += "4. 요약은 쉽고 간결한 한국어로 작성하세요.\n"
    prompt += "5. 이모지를 섞어서 가독성을 높여주세요.\n"
    prompt += "6. 마지막에는 '오늘도 좋은 하루 되세요!'라는 문구를 넣어주세요.\n\n"
    prompt += "뉴스 목록:\n"
    
    for item in news_items[:15]: # 요약 품질을 위해 개수를 약간 조정
        prompt += f"- [{item['category']}] {item['title']} (링크: {item['link']})\n"

    try:
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        return f"요약 생성 중 오류 발생: {e}"

def send_to_discord(content):
    """요약된 내용을 디스코드 웹후크로 전송합니다."""
    if not DISCORD_WEBHOOK_URL:
        print("Error: DISCORD_WEBHOOK_URL is not set.")
        return

    # 디스코드 메시지 길이 제한 (2000자) 고려
    if len(content) > 1900:
        content = content[:1800] + "\n\n(내용이 너무 길어 일부 생략되었습니다.)"

    data = {
        "content": "📢 **오늘의 뉴스 및 AI 소식 요약**\n\n" + content,
        "username": "AI 뉴스 비서"
    }
    
    response = requests.post(DISCORD_WEBHOOK_URL, json=data)
    if response.status_code == 204:
        print("Successfully sent to Discord.")
    else:
        print(f"Failed to send to Discord: {response.status_code}, {response.text}")

if __name__ == "__main__":
    print("Fetching and summarizing news...")
    news = fetch_latest_news()
    if news:
        summary = summarize_with_gemini(news)
        send_to_discord(summary)
    else:
        send_to_discord("최근 24시간 동안 주요한 뉴스 소식이 발견되지 않았습니다.")

