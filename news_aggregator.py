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

# 2. 세분화된 RSS 피드 목록 (AI 트렌드 소스 보강)
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
    "Global_Tech": [ # 해외 IT/AI (최신 트렌드 및 바이브 코딩 등 이슈 포함)
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
    return news_items

def summarize_with_gemini(news_items):
    print("Step 2: Summarizing with Gemini (Table + Trends focus)...")
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

    targets = ['gemini-1.5-flash', 'gemini-1.5-flash-latest', 'gemini-2.0-flash', 'gemini-pro']
    test_queue = [m for m in targets if m in available_models] + [m for m in available_models if m not in targets]

    # [중요] 표 양식 및 바이브 코딩 등 트렌드 강조 프롬프트
    prompt = f"""당신은 전문 뉴스 큐레이터입니다. 아래 제공된 뉴스 목록을 바탕으로 '오늘의 핵심 브리핑'을 작성해 주세요.

요청 사항:
1. **[표 양식 요약]** 맨 처음에 전체 뉴스를 한눈에 볼 수 있는 마크다운 '표(Table)'를 만드세요. 
   - 열 구성: 섹션, 핵심 키워드, 주요 메시지(한 줄 요약)
2. **[AI 트렌드 집중]** AI 분야의 기술적 이슈(예: 바이브 코딩(Vibe Coding), AI 프로그래밍 동향, 모델 업데이트 등)를 매우 비중 있게 다뤄주세요.
3. **[카테고리별 상세]** 표 아래에는 다음 4가지 섹션별로 상세 요약(각 3~5건)을 작성하세요.
   - 🇰🇷 국내 주요 시사 (KR_General)
   - 🌎 해외 주요 시사 (Global_General)
   - 💻 국내 IT/AI 소식 (KR_Tech)
   - 🤖 해외 IT/AI 및 최신 트렌드 (Global_Tech)
4. 각 상세 소식 끝에는 반드시 [원문보기](링크)를 포함하세요.
5. 전문적이면서도 통찰력 있는 한국어로 작성하세요.

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
    if not DISCORD_WEBHOOK_URL: return
    
    # 디스코드 메시지 길이 제한 대응
    if len(content) > 1900:
        content = content[:1850] + "\n\n...(내용이 길어 일부 생략되었습니다)"

    data = {"content": "📢 **오늘의 뉴스 요약 및 AI 트렌드 브리핑**\n\n" + content, "username": "AI 뉴스 비서"}
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
