"""
Security & AI Daily News Agent
매일 아침 최신 보안/AI 뉴스 Top 10을 수집하고 한국어로 요약해 HTML 생성
"""

import feedparser
import anthropic
import json
import os
import urllib.request
import urllib.parse
from datetime import datetime, timezone, timedelta
from pathlib import Path

# ── 뉴스 소스 (RSS 피드) ──────────────────────────────────────────────
RSS_FEEDS = {
    "security": [
        ("The Hacker News",     "https://feeds.feedburner.com/TheHackersNews"),
        ("Krebs on Security",   "https://krebsonsecurity.com/feed/"),
        ("Bleeping Computer",   "https://www.bleepingcomputer.com/feed/"),
        ("Dark Reading",        "https://www.darkreading.com/rss/all.xml"),
        ("SANS Internet Storm", "https://isc.sans.edu/rssfeed_full.xml"),
    ],
    "ai": [
        ("MIT Tech Review AI",  "https://www.technologyreview.com/feed/"),
        ("VentureBeat AI",      "https://venturebeat.com/category/ai/feed/"),
        ("The Verge AI",        "https://www.theverge.com/rss/ai-artificial-intelligence/index.xml"),
        ("Ars Technica AI",     "https://feeds.arstechnica.com/arstechnica/index"),
        ("Wired AI",            "https://www.wired.com/feed/tag/ai/latest/rss"),
    ],
}

KST = timezone(timedelta(hours=9))


def fetch_articles(max_per_feed: int = 10) -> list[dict]:
    """RSS 피드에서 최근 기사 수집"""
    articles = []
    cutoff = datetime.now(KST) - timedelta(hours=36)  # 최근 36시간

    for category, feeds in RSS_FEEDS.items():
        for source_name, url in feeds:
            try:
                feed = feedparser.parse(url)
                for entry in feed.entries[:max_per_feed]:
                    # 날짜 파싱
                    pub = entry.get("published_parsed") or entry.get("updated_parsed")
                    if pub:
                        pub_dt = datetime(*pub[:6], tzinfo=timezone.utc).astimezone(KST)
                        if pub_dt < cutoff:
                            continue
                    else:
                        pub_dt = datetime.now(KST)

                    summary = entry.get("summary", "")[:800]  # 너무 길면 자름

                    articles.append({
                        "category": category,
                        "source": source_name,
                        "title": entry.get("title", "").strip(),
                        "url": entry.get("link", ""),
                        "summary": summary,
                        "published": pub_dt.strftime("%Y-%m-%d %H:%M KST"),
                    })
            except Exception as e:
                print(f"⚠️  {source_name} 수집 실패: {e}")

    print(f"✅ 총 {len(articles)}개 기사 수집 완료")
    return articles


def select_and_summarize(articles: list[dict]) -> list[dict]:
    """Claude API로 Top 10 선정 + 한국어 요약"""
    client = anthropic.Anthropic()  # ANTHROPIC_API_KEY 환경변수 자동 사용

    # 기사 목록을 JSON으로 전달
    articles_json = json.dumps(
        [{"index": i, **a} for i, a in enumerate(articles)],
        ensure_ascii=False,
        indent=2
    )

    prompt = f"""You are a senior security and AI researcher. 
Below are {len(articles)} news articles collected in the last 36 hours.

YOUR TASK:
1. Select the TOP 10 most important/impactful articles (mix of security and AI)
2. For each selected article, provide:
   - "index": original article index number
   - "rank": 1-10
   - "category": "security" or "ai"  
   - "importance": one of "🔴 Critical" | "🟠 High" | "🟡 Medium"
   - "korean_title": Korean translation of the title
   - "korean_summary": 2-3 sentence Korean summary (concise, factual, no fluff)
   - "key_point": single most important takeaway in Korean (1 sentence)
   - "tags": list of 2-3 relevant Korean tags (e.g. ["랜섬웨어", "제로데이"])

Selection criteria:
- Novelty and breaking news
- Severity of security threats / impact of AI developments
- Relevance to enterprise and practitioners
- Avoid duplicates on same topic

TREND DETECTION (IMPORTANT):
- After selecting top 10, analyze all collected articles (not just top 10)
- Count how many articles share the same topic/keyword (e.g. ransomware, CVE, GPT, etc.)
- If a topic appears in 3 or more articles total, it is a TRENDING topic
- For trending topics: set importance to "🔴 Critical" and add "trending": true
- Add a "trending_topics" field at the end: list of {topic, count} for topics with 3+ articles

Respond ONLY with a valid JSON object with two keys:
- "top10": the array of top 10 articles
- "trending_topics": array of trending topics [{topic, count}], empty array if none

No markdown, no preamble.

ARTICLES:
{articles_json}
"""

    message = client.messages.create(
        model="claude-opus-4-5",
        max_tokens=4000,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = message.content[0].text.strip()
    # 혹시 ```json ``` 감싸진 경우 제거
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    raw = raw.strip()

    parsed = json.loads(raw)
    top10_meta = parsed.get("top10", parsed) if isinstance(parsed, dict) else parsed
    trending_topics = parsed.get("trending_topics", []) if isinstance(parsed, dict) else []

    if trending_topics:
        print(f"🚨 트렌딩 주제 감지: {[t['topic'] for t in trending_topics]}")

    # 원본 기사 정보와 병합
    result = []
    for item in sorted(top10_meta, key=lambda x: x["rank"]):
        original = articles[item["index"]]
        result.append({**original, **item})

    print(f"✅ Top 10 선정 완료")
    return result, trending_topics


def generate_html(top10: list[dict]) -> str:
    """세련된 HTML 뉴스레터 생성"""
    now_kst = datetime.now(KST).strftime("%Y년 %m월 %d일 %H:%M KST")
    today_label = datetime.now(KST).strftime("%Y.%m.%d")

    cards_html = ""
    for item in top10:
        tags_html = "".join(f'<span class="tag">{t}</span>' for t in item.get("tags", []))
        cat_label = "🔐 Security" if item["category"] == "security" else "🤖 AI"
        cat_class = "cat-security" if item["category"] == "security" else "cat-ai"
        importance = item.get("importance", "🟡 Medium")

        cards_html += f"""
        <article class="card">
            <div class="card-header">
                <div class="rank-badge">#{item['rank']}</div>
                <span class="category-badge {cat_class}">{cat_label}</span>
                <span class="importance">{importance}</span>
                <span class="source-label">{item['source']}</span>
            </div>
            <h2 class="korean-title">{item['korean_title']}</h2>
            <p class="en-title"><a href="{item['url']}" target="_blank" rel="noopener">{item['title']} ↗</a></p>
            <div class="key-point">💡 {item['key_point']}</div>
            <p class="summary">{item['korean_summary']}</p>
            <div class="card-footer">
                <div class="tags">{tags_html}</div>
                <span class="pub-time">🕐 {item['published']}</span>
            </div>
        </article>"""

    sec_count = sum(1 for i in top10 if i["category"] == "security")
    ai_count = len(top10) - sec_count

    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Security & AI Daily Brief — {today_label}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Bebas+Neue&family=Noto+Sans+KR:wght@300;400;500;700&family=JetBrains+Mono:wght@400;600&display=swap" rel="stylesheet">
<style>
  :root {{
    --bg: #0a0c10;
    --surface: #111318;
    --surface2: #181c24;
    --border: #1e2330;
    --accent-sec: #ff4d6d;
    --accent-ai: #00d4ff;
    --accent-glow-sec: rgba(255,77,109,0.15);
    --accent-glow-ai: rgba(0,212,255,0.12);
    --text-primary: #e8eaf0;
    --text-secondary: #7a8499;
    --text-muted: #4a5268;
    --gold: #ffd166;
    --green: #06d6a0;
  }}

  * {{ margin: 0; padding: 0; box-sizing: border-box; }}

  body {{
    background: var(--bg);
    color: var(--text-primary);
    font-family: 'Noto Sans KR', sans-serif;
    font-weight: 300;
    min-height: 100vh;
    background-image:
      radial-gradient(ellipse 80% 50% at 50% -20%, rgba(0,212,255,0.05) 0%, transparent 60%),
      radial-gradient(ellipse 60% 40% at 80% 100%, rgba(255,77,109,0.04) 0%, transparent 50%);
  }}

  /* ── Header ── */
  header {{
    padding: 3rem 2rem 2rem;
    max-width: 900px;
    margin: 0 auto;
    border-bottom: 1px solid var(--border);
  }}

  .header-top {{
    display: flex;
    align-items: baseline;
    gap: 1.5rem;
    flex-wrap: wrap;
  }}

  .masthead {{
    font-family: 'Bebas Neue', sans-serif;
    font-size: clamp(2.5rem, 6vw, 4.5rem);
    letter-spacing: 0.08em;
    background: linear-gradient(135deg, #fff 0%, var(--accent-ai) 60%, var(--accent-sec) 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
    line-height: 1;
  }}

  .edition-label {{
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.75rem;
    color: var(--text-muted);
    border: 1px solid var(--border);
    padding: 0.3rem 0.7rem;
    border-radius: 4px;
    letter-spacing: 0.1em;
  }}

  .header-meta {{
    margin-top: 1rem;
    display: flex;
    gap: 2rem;
    flex-wrap: wrap;
    align-items: center;
  }}

  .stat-pill {{
    display: flex;
    align-items: center;
    gap: 0.4rem;
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.78rem;
    color: var(--text-secondary);
  }}

  .dot {{
    width: 7px; height: 7px;
    border-radius: 50%;
    display: inline-block;
  }}
  .dot-sec {{ background: var(--accent-sec); box-shadow: 0 0 6px var(--accent-sec); }}
  .dot-ai  {{ background: var(--accent-ai);  box-shadow: 0 0 6px var(--accent-ai); }}

  .updated {{
    margin-left: auto;
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.7rem;
    color: var(--text-muted);
  }}

  /* ── Main Grid ── */
  main {{
    max-width: 900px;
    margin: 0 auto;
    padding: 2.5rem 2rem 4rem;
    display: flex;
    flex-direction: column;
    gap: 1.2rem;
  }}

  /* ── Card ── */
  .card {{
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 1.6rem 1.8rem;
    transition: border-color 0.2s, transform 0.2s;
    position: relative;
    overflow: hidden;
  }}

  .card::before {{
    content: '';
    position: absolute;
    top: 0; left: 0; right: 0;
    height: 2px;
    background: linear-gradient(90deg, transparent, var(--accent-ai), transparent);
    opacity: 0;
    transition: opacity 0.3s;
  }}

  .card:hover::before {{ opacity: 1; }}
  .card:hover {{ border-color: #2a3040; transform: translateY(-2px); }}

  .card-header {{
    display: flex;
    align-items: center;
    gap: 0.7rem;
    margin-bottom: 0.9rem;
    flex-wrap: wrap;
  }}

  .rank-badge {{
    font-family: 'Bebas Neue', sans-serif;
    font-size: 1.4rem;
    color: var(--text-muted);
    min-width: 2rem;
    line-height: 1;
  }}

  .card:nth-child(1) .rank-badge {{ color: var(--gold); text-shadow: 0 0 12px rgba(255,209,102,0.5); }}
  .card:nth-child(2) .rank-badge {{ color: #c0c8d8; }}
  .card:nth-child(3) .rank-badge {{ color: #cd7f32; }}

  .category-badge {{
    font-size: 0.7rem;
    font-weight: 500;
    padding: 0.25rem 0.7rem;
    border-radius: 20px;
    letter-spacing: 0.03em;
  }}

  .cat-security {{
    background: var(--accent-glow-sec);
    color: var(--accent-sec);
    border: 1px solid rgba(255,77,109,0.3);
  }}

  .cat-ai {{
    background: var(--accent-glow-ai);
    color: var(--accent-ai);
    border: 1px solid rgba(0,212,255,0.25);
  }}

  .importance {{
    font-size: 0.72rem;
    color: var(--text-muted);
    font-family: 'JetBrains Mono', monospace;
  }}

  .source-label {{
    margin-left: auto;
    font-size: 0.68rem;
    color: var(--text-muted);
    font-family: 'JetBrains Mono', monospace;
    letter-spacing: 0.05em;
  }}

  .korean-title {{
    font-size: 1.1rem;
    font-weight: 700;
    line-height: 1.5;
    margin-bottom: 0.4rem;
    color: var(--text-primary);
  }}

  .en-title {{
    margin-bottom: 0.9rem;
  }}

  .en-title a {{
    font-size: 0.78rem;
    color: var(--text-muted);
    text-decoration: none;
    font-family: 'JetBrains Mono', monospace;
    transition: color 0.2s;
  }}

  .en-title a:hover {{ color: var(--accent-ai); }}

  .key-point {{
    background: var(--surface2);
    border-left: 3px solid var(--gold);
    padding: 0.65rem 1rem;
    border-radius: 0 8px 8px 0;
    font-size: 0.85rem;
    font-weight: 500;
    color: #ccd0e0;
    margin-bottom: 0.85rem;
    line-height: 1.55;
  }}

  .summary {{
    font-size: 0.88rem;
    line-height: 1.75;
    color: var(--text-secondary);
    margin-bottom: 1rem;
  }}

  .card-footer {{
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 0.5rem;
    flex-wrap: wrap;
  }}

  .tags {{ display: flex; gap: 0.4rem; flex-wrap: wrap; }}

  .tag {{
    font-size: 0.68rem;
    padding: 0.2rem 0.6rem;
    background: var(--surface2);
    border: 1px solid var(--border);
    border-radius: 4px;
    color: var(--text-muted);
    font-family: 'JetBrains Mono', monospace;
  }}

  .pub-time {{
    font-size: 0.68rem;
    color: var(--text-muted);
    font-family: 'JetBrains Mono', monospace;
    white-space: nowrap;
  }}

  /* ── Footer ── */
  footer {{
    text-align: center;
    padding: 2rem;
    font-size: 0.72rem;
    color: var(--text-muted);
    font-family: 'JetBrains Mono', monospace;
    border-top: 1px solid var(--border);
  }}

  @media (max-width: 600px) {{
    header, main {{ padding-left: 1rem; padding-right: 1rem; }}
    .card {{ padding: 1.2rem 1.2rem; }}
    .source-label {{ display: none; }}
  }}
</style>
</head>
<body>

<header>
  <div class="header-top">
    <div class="masthead">DAILY BRIEF</div>
    <span class="edition-label">SECURITY &amp; AI · {today_label}</span>
  </div>
  <div class="header-meta">
    <div class="stat-pill"><span class="dot dot-sec"></span>{sec_count} Security</div>
    <div class="stat-pill"><span class="dot dot-ai"></span>{ai_count} AI</div>
    <div class="stat-pill">TOP 10 선정</div>
    <span class="updated">Updated {now_kst}</span>
  </div>
</header>

<main>
  {cards_html}
</main>

<footer>
  Powered by Claude AI · RSS aggregated from {sum(len(v) for v in RSS_FEEDS.values())} sources · Auto-generated daily at 08:00 KST
</footer>

</body>
</html>"""


def refresh_kakao_token() -> str:
    """리프레시 토큰으로 새 액세스 토큰 발급"""
    refresh_token = os.environ.get("KAKAO_REFRESH_TOKEN")
    if not refresh_token:
        print("⚠️  KAKAO_REFRESH_TOKEN 없음.")
        return None

    data = urllib.parse.urlencode({
        "grant_type": "refresh_token",
        "client_id": "aec4c181076bd8c64efe2730abd82efc",
        "refresh_token": refresh_token,
        "client_secret": "U9O1cGQWEllILPJWqIkQXcK0Ppehnz"
    }).encode()

    req = urllib.request.Request(
        "https://kauth.kakao.com/oauth/token",
        data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded"}
    )
    res = urllib.request.urlopen(req)
    result = json.loads(res.read())
    print("✅ 액세스 토큰 자동 갱신 완료!")
    return result.get("access_token")


def send_kakao(top10: list[dict]) -> None:
    """카카오톡 나에게 보내기로 Top 10 요약 전송"""
    token = refresh_kakao_token()
    if not token:
        token = os.environ.get("KAKAO_ACCESS_TOKEN")
    if not token:
        print("⚠️  카카오 토큰 없음. 전송 스킵.")
        return

    today = datetime.now(KST).strftime("%Y.%m.%d")
    page_url = "https://Philocreation.github.io/security-ai-brief/"

    # 메시지 본문 구성 (Top 5만 요약, 나머지는 링크로)
    lines = [f"📰 Security & AI Daily Brief\n{today}\n"]
    for item in top10[:5]:
        cat = "🔐" if item["category"] == "security" else "🤖"
        lines.append(f"{cat} #{item['rank']} {item['korean_title']}")
        lines.append(f"💡 {item['key_point']}\n")
    lines.append(f"▶ 전체 Top 10 보기: {page_url}")
    text = "\n".join(lines)

    template = {
        "object_type": "text",
        "text": text,
        "link": {
            "web_url": page_url,
            "mobile_web_url": page_url
        }
    }
    data = urllib.parse.urlencode({
        "template_object": json.dumps(template, ensure_ascii=False)
    }).encode()

    req = urllib.request.Request(
        "https://kapi.kakao.com/v2/api/talk/memo/default/send",
        data=data,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/x-www-form-urlencoded",
        }
    )
    try:
        res = urllib.request.urlopen(req)
        result = json.loads(res.read())
        if result.get("result_code") == 0:
            print("✅ 카카오톡 전송 성공!")
        else:
            print(f"⚠️  카카오톡 전송 실패: {result}")
    except Exception as e:
        print(f"⚠️  카카오톡 전송 오류: {e}")


def main():
    print("🚀 Security & AI Daily News Agent 시작")

    # 1. 기사 수집
    articles = fetch_articles()
    if not articles:
        print("❌ 수집된 기사 없음. 종료.")
        return

    # 2. Claude로 Top 10 선정 + 요약 + 트렌드 감지
    top10, trending_topics = select_and_summarize(articles)

    # 3. HTML 생성
    html = generate_html(top10)

    # 4. 저장
    out_dir = Path("docs")
    out_dir.mkdir(exist_ok=True)
    output_path = out_dir / "index.html"
    output_path.write_text(html, encoding="utf-8")
    print(f"✅ HTML 저장 완료 → {output_path}")

    # 5. 아카이브 (날짜별 보관)
    archive_dir = out_dir / "archive"
    archive_dir.mkdir(exist_ok=True)
    date_str = datetime.now(KST).strftime("%Y-%m-%d")
    archive_path = archive_dir / f"{date_str}.html"
    archive_path.write_text(html, encoding="utf-8")
    print(f"✅ 아카이브 저장 완료 → {archive_path}")

    # 6. 카카오톡 전송
    send_kakao(top10, trending_topics)


if __name__ == "__main__":
    main()
