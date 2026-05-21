# 📰 Security & AI Daily Brief

매일 오전 8시 KST, 최신 보안·AI 뉴스 Top 10을 자동으로 수집·요약해 웹으로 제공합니다.

## 구조

```
├── news_agent.py                        # 메인 에이전트
├── requirements.txt
├── .github/
│   └── workflows/
│       └── daily_brief.yml              # GitHub Actions (자동 스케줄)
└── docs/
    ├── index.html                        # 오늘의 브리핑 (GitHub Pages)
    └── archive/
        └── YYYY-MM-DD.html              # 날짜별 아카이브
```

## 세팅 방법 (5분)

### 1. 레포지토리 생성
```bash
git init security-ai-brief
cd security-ai-brief
# 파일들 복사 후
git add .
git commit -m "init"
git remote add origin https://github.com/YOUR_ID/security-ai-brief.git
git push -u origin main
```

### 2. Anthropic API Key 등록
GitHub 레포 → **Settings → Secrets and variables → Actions → New repository secret**
- Name: `ANTHROPIC_API_KEY`
- Value: `sk-ant-...`

### 3. GitHub Pages 활성화
GitHub 레포 → **Settings → Pages**
- Source: `Deploy from a branch`
- Branch: `main` / folder: `/docs`
- Save

완료! 매일 오전 8시에 자동 생성된 브리핑이 아래 주소에 올라옵니다:
```
https://YOUR_ID.github.io/security-ai-brief/
```

### 4. 로컬 테스트
```bash
pip install -r requirements.txt
export ANTHROPIC_API_KEY=sk-ant-...
python news_agent.py
# → docs/index.html 생성됨, 브라우저로 열어 확인
```

## 뉴스 소스

| 카테고리 | 소스 |
|---------|------|
| 🔐 Security | The Hacker News, Krebs on Security, Bleeping Computer, Dark Reading, SANS |
| 🤖 AI | MIT Tech Review, VentureBeat AI, The Verge AI, Ars Technica, Wired AI |

## 비용

- GitHub Actions: **무료** (월 2,000분 무료 — 하루 1회 실행 약 2분 소요)
- Claude API: **약 $0.01~0.03 / 1회** (claude-opus 기준)
  - 월 약 $0.30~0.90 수준

## 커스터마이징

`news_agent.py` 상단 `RSS_FEEDS` 딕셔너리에 원하는 RSS 주소를 추가하면 됩니다.
