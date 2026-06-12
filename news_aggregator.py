import os
import sys
import traceback
import re
from collections import Counter, defaultdict
from urllib.parse import urlparse
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
        "https://imnews.imbc.com/rss/news/news_00.xml",
        "https://www.khan.co.kr/rss/rssdata/total_news.xml",
        "https://www.yonhapnewstv.co.kr/browse/feed/",
        "https://www.chosun.com/arc/outboundfeeds/rss/?outputType=xml",
        "https://www.mk.co.kr/rss/30000001/",
        "https://www.hankyung.com/feed/all-news",
    ],
    "Global_General": [
        "https://www.reutersagency.com/feed/?best-topics=top-news&post_type=best",
        "http://feeds.bbci.co.uk/news/world/rss.xml",
        "https://feeds.npr.org/1004/rss.xml",
        "https://rss.nytimes.com/services/xml/rss/nyt/World.xml",
        "https://www.theguardian.com/world/rss",
        "https://www.aljazeera.com/xml/rss/all.xml",
        "https://feeds.washingtonpost.com/rss/world",
    ],
    "KR_Tech": [
        "https://m.etnews.com/news/section_rss.html?id1=20",
        "https://www.zdnet.co.kr/rss/all.xml",
        "https://www.techm.kr/rss/all.xml",
        "https://www.bloter.net/rss/allArticle.xml",
        "https://www.digitaltoday.co.kr/rss/allArticle.xml",
        "https://www.aitimes.com/rss/allArticle.xml",
        "https://byline.network/feed/",
    ],
    "Global_Tech": [
        "https://openai.com/news/rss.xml",
        "https://deepmind.google/blog/rss.xml",
        "https://techcrunch.com/category/artificial-intelligence/feed/",
        "https://www.theverge.com/ai-artificial-intelligence/rss/index.xml",
        "https://www.unite.ai/feed/",
        "https://www.aitidbits.com/rss",
        "https://www.wired.com/feed/category/business/artificial-intelligence/latest/rss",
        "https://venturebeat.com/category/ai/feed/",
        "https://www.artificialintelligence-news.com/feed/",
        "https://simonwillison.net/atom/everything/",
    ]
}

STOPWORDS = {
    "the", "and", "for", "with", "from", "this", "that", "into", "after", "over",
    "amid", "about", "says", "new", "news", "will", "are", "was", "has", "have",
    "you", "your", "its", "more", "how", "why", "what", "who", "but", "not",
    "속보", "뉴스", "오늘", "단독", "종합", "기자", "관련", "대한", "이번", "위해",
    "있는", "없는", "한다", "했다", "된다", "지난", "올해", "정부", "한국",
}

MAX_ITEMS_PER_CATEGORY = 35
DISCORD_CONTENT_LIMIT = 1900

def get_source_name(url):
    host = urlparse(url).netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    return host or "unknown"

def tokenize_title(title):
    return [
        token.lower()
        for token in re.findall(r"[A-Za-z][A-Za-z0-9-]{2,}|[가-힣]{2,}", title)
        if token.lower() not in STOPWORDS
    ]

def rank_hot_topics(news_items):
    token_counts = Counter()
    source_counts = defaultdict(Counter)

    for item in news_items:
        tokens = set(tokenize_title(item["title"]))
        token_counts.update(tokens)
        for token in tokens:
            source_counts[token][item["source"]] += 1

    for item in news_items:
        tokens = set(tokenize_title(item["title"]))
        item["topic_score"] = sum(
            token_counts[token] + len(source_counts[token]) * 2
            for token in tokens
        )

    ranked = []
    seen_links = set()
    source_quota = defaultdict(lambda: defaultdict(int))
    for item in sorted(news_items, key=lambda x: (x["topic_score"], x["published_at"]), reverse=True):
        if item["link"] in seen_links:
            continue
        if source_quota[item["category"]][item["source"]] >= 5:
            continue
        ranked.append(item)
        seen_links.add(item["link"])
        source_quota[item["category"]][item["source"]] += 1

    grouped = defaultdict(list)
    for item in ranked:
        if len(grouped[item["category"]]) < MAX_ITEMS_PER_CATEGORY:
            grouped[item["category"]].append(item)

    return [item for category in RSS_FEEDS for item in grouped[category]]

def fetch_latest_news():
    print("Step 1: Fetching news...")
    news_items = []
    now = datetime.now(timezone.utc)
    lookback = now - timedelta(days=3)
    for cat, urls in RSS_FEEDS.items():
        for url in urls:
            try:
                feed = feedparser.parse(url)
                for entry in feed.entries:
                    pub = entry.get("published_parsed") or entry.get("updated_parsed")
                    if pub:
                        dt = datetime(*pub[:6], tzinfo=timezone.utc)
                        if dt > lookback:
                            news_items.append({
                                "category": cat,
                                "title": entry.title,
                                "link": entry.link,
                                "source": get_source_name(entry.link or url),
                                "published_at": dt,
                            })
            except Exception as exc:
                print(f"Feed error: {url} ({exc})")
                continue

    ranked_items = rank_hot_topics(news_items)
    print(f"Fetched {len(news_items)} items, selected {len(ranked_items)} hot-topic candidates.")
    return ranked_items

def summarize_with_gemini(news_items):
    print("Step 2: Summarizing with Gemini (Strictly Data-Driven)...")
    if not news_items:
        return ""
    if not GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY is missing.")
    genai.configure(api_key=GEMINI_API_KEY.strip())
    
    available_models = []
    try:
        for m in genai.list_models():
            if 'generateContent' in m.supported_generation_methods:
                available_models.append(m.name.replace('models/', ''))
    except Exception as exc:
        raise RuntimeError(f"Could not list Gemini models: {exc}") from exc

    targets = ['gemini-1.5-flash', 'gemini-2.0-flash', 'gemini-pro']
    test_queue = [m for m in targets if m in available_models] + [m for m in available_models if m not in targets]

    # [데이터 기반] 외부 지식 배제 및 뉴스 데이터 충실 요약 프롬프트
    prompt = f"""당신은 제공된 정보에만 기반하여 객관적으로 요약하는 전문 뉴스 큐레이터입니다.
현재 시점({datetime.now().strftime('%Y-%m-%d')})의 최신 뉴스들을 바탕으로 브리핑을 작성해 주세요.

요청 사항:
1. **[데이터 중심 요약]** 당신의 외부 지식이나 과거 정보를 절대 섞지 마세요. 제공된 '뉴스 데이터'에 적힌 인물의 성함과 직함을 그대로 사용하여 요약하세요. 
2. **[섹션별 3건 선정]** 아래 카테고리별로 가장 중요한 뉴스 '딱 3건씩'만 선정하세요. (총 12건)
3. **[핫토픽 우선]** 여러 매체에서 반복되는 주제, 사회적 파급력이 큰 이슈, 기술 업계의 큰 변화 신호를 우선하세요.
4. **[출력 양식]** 메시지 분할 전송을 위해 아래 구분자를 반드시 포함하세요.

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
        prompt += (
            f"- [{item['category']}] {item['title']} "
            f"(출처: {item['source']}, 핫토픽점수: {item['topic_score']}, 링크: {item['link']})\n"
        )

    for model_name in test_queue:
        try:
            model = genai.GenerativeModel(model_name)
            return model.generate_content(prompt).text
        except Exception as exc:
            print(f"Gemini model failed: {model_name} ({exc})")
            continue
    raise RuntimeError("All Gemini models failed.")

def chunk_discord_message(content, limit=DISCORD_CONTENT_LIMIT):
    chunks = []
    current = ""

    for line in content.splitlines(keepends=True):
        if len(line) > limit:
            if current:
                chunks.append(current.rstrip())
                current = ""
            for start in range(0, len(line), limit):
                chunks.append(line[start:start + limit].rstrip())
            continue

        if len(current) + len(line) > limit:
            chunks.append(current.rstrip())
            current = line
        else:
            current += line

    if current.strip():
        chunks.append(current.rstrip())
    return chunks

def send_to_discord(full_content):
    print("Step 3: Sending to Discord (Multi-Message)...")
    if not DISCORD_WEBHOOK_URL:
        raise RuntimeError("DISCORD_WEBHOOK_URL is missing.")
    if not full_content:
        raise RuntimeError("Summary content is empty.")
    
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
            
        messages = chunk_discord_message(header + clean_content)
        for index, message in enumerate(messages, start=1):
            suffix = f"\n\n({index}/{len(messages)})" if len(messages) > 1 else ""
            data = {"content": message + suffix, "username": "AI 뉴스 큐레이터"}
            response = requests.post(DISCORD_WEBHOOK_URL.strip(), json=data, timeout=15)
            response.raise_for_status()

if __name__ == "__main__":
    try:
        news = fetch_latest_news()
        summary = summarize_with_gemini(news)
        send_to_discord(summary)
    except:
        traceback.print_exc()
        sys.exit(1)
