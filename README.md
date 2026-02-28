# HiPass 영수증 자동수집

HiPass 고속도로 통행 영수증을 자동으로 캡처하여 웹에서 조회·다운로드하는 Docker 기반 서비스.

## 주요 기능

- **자동 캡처** — 매일 지정 시각에 최근 14일치 영수증 자동 수집
- **수동 캡처** — 웹 UI에서 전체 또는 특정 날짜 캡처 즉시 실행
- **미리보기/다운로드** — PNG 영수증을 브라우저에서 확인 및 저장
- **진행 상태 표시** — 캡처 진행률 실시간 폴링

## 스크린샷

| 메인 화면 |
|-----------|
| 날짜별 영수증 목록, 미리보기, 다운로드, 캡처 로그 |

## 시작하기

### 사전 요구사항

- Docker & Docker Compose

### 설치 및 실행

```bash
# 1. 저장소 클론
git clone https://github.com/mesmeriz2/hipass_receipts.git
cd hipass_receipts

# 2. 환경변수 파일 준비
cp .env.example .env
# .env 에 실제 HiPass 자격증명 입력

# 3. 빌드 및 실행
docker compose up --build -d

# 4. 접속
http://localhost:8007
```

## 환경변수

`.env` 파일에 아래 값을 설정합니다.

| 변수 | 설명 | 기본값 |
|------|------|--------|
| `HIPASS_ID` | HiPass 로그인 아이디 | **필수** |
| `HIPASS_PW` | HiPass 로그인 비밀번호 | **필수** |
| `ECD_NO` | 차량/카드 식별자 | 빈 문자열 |
| `PORT` | 호스트 포트 | `8007` |
| `SCHEDULE_HOUR` | 매일 자동 캡처 시각 (0–23) | `6` |
| `RETENTION_DAYS` | 영수증 보관 기간 (일) | `14` |

> **주의:** 비밀번호에 `#`이 포함된 경우 따옴표 없이 그대로 입력하세요.
> Docker Compose의 `env_file` 방식은 `#`을 주석으로 처리하므로, 이 서비스는 `.env`를 볼륨으로 직접 마운트하여 `python-dotenv`로 파싱합니다.

## API

| Method | Path | 설명 |
|--------|------|------|
| `GET` | `/` | 메인 HTML 페이지 |
| `GET` | `/health` | 헬스체크 |
| `GET` | `/api/screenshots` | 스크린샷 목록 JSON |
| `POST` | `/api/refresh` | 전체(14일) 캡처 시작 → `{job_id}` 반환 |
| `POST` | `/api/capture/{date}` | 단일 날짜 캡처 시작 → `{job_id}` 반환 |
| `GET` | `/api/status/{job_id}` | 캡처 진행 상태 폴링 |
| `GET` | `/api/logs` | 최근 캡처 세션 로그 |
| `GET` | `/screenshots/{filename}` | PNG 파일 다운로드 |

## 아키텍처

```
단일 Docker 컨테이너 (:8007)
  FastAPI (uvicorn)
  ├─ Jinja2 HTML 서빙 (프론트엔드)
  ├─ Playwright Chromium headless (스크래핑)
  ├─ APScheduler (매일 SCHEDULE_HOUR 시각 자동 캡처)
  └─ /app/screenshots 볼륨 (PNG 저장)
```

## 파일 구조

```
.
├── docker-compose.yml
├── .env.example
└── backend/
    ├── Dockerfile
    ├── requirements.txt
    └── app/
        ├── main.py        # FastAPI 앱, 라우트, lifespan, 스케줄러 연결
        ├── config.py      # 환경변수 로드
        ├── scraper.py     # Playwright: 로그인 → 날짜별 캡처
        ├── scheduler.py   # APScheduler: 자동 캡처 + 오래된 파일 삭제
        ├── templates/
        │   └── index.html
        └── static/
            └── style.css
```

## 라이선스

MIT
