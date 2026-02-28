# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 프로젝트 개요

HiPass 영수증 웹 서비스. 최근 2주간 HiPass 고속도로 통행 영수증을 자동 캡처하여 웹에서 조회·다운로드할 수 있는 Docker 기반 서비스. Synology NAS에서 운영.

## 실행 방법

```bash
# 1. 환경변수 파일 준비
cp .env.example .env
# .env 에 실제 HiPass 자격증명 입력

# 2. 빌드 및 실행
docker compose up --build

# 3. 접속
http://localhost:8007
```

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
07_hipass/
  docker-compose.yml
  .env.example
  .gitignore
  CLAUDE.md
  backend/
    Dockerfile
    requirements.txt
    app/
      __init__.py
      main.py       # FastAPI 앱, 라우트, lifespan, 스케줄러 연결
      config.py     # 환경변수 로드
      scraper.py    # Playwright async: 로그인 → 날짜별 캡처, 캡처 로그
      scheduler.py  # APScheduler: 매일 자동 캡처 + 오래된 파일 삭제
      templates/
        index.html  # Jinja2: 날짜별 스크린샷 목록 + 다운로드
      static/
        style.css
    screenshots/    # 볼륨 마운트, PNG 저장
```

## 환경변수 (.env)

| 변수 | 설명 | 기본값 |
|------|------|--------|
| `HIPASS_ID` | HiPass 로그인 아이디 | 필수 |
| `HIPASS_PW` | HiPass 로그인 비밀번호 | 필수 |
| `ECD_NO` | 차량/카드 식별자 | 빈 문자열 |
| `PORT` | 호스트 포트 | 8007 |
| `SCHEDULE_HOUR` | 매일 자동 캡처 시각 (0-23) | 6 |
| `RETENTION_DAYS` | 보관 기간 (일) | 14 |

## API 엔드포인트

| Method | Path | 설명 |
|--------|------|------|
| GET | `/` | HTML 메인 페이지 |
| GET | `/health` | 헬스체크 |
| GET | `/api/screenshots` | 스크린샷 목록 JSON |
| POST | `/api/refresh` | 수동 캡처 시작 → `{job_id}` 반환 |
| GET | `/api/status/{job_id}` | 캡처 진행 상태 폴링 |
| GET | `/api/logs` | 최근 캡처 세션 로그 |
| GET | `/screenshots/{filename}` | PNG 파일 다운로드 |

## 핵심 모듈

| 모듈 | 역할 |
|------|------|
| `config.py` | 환경변수 로드, 경로 상수 |
| `scraper.py::login()` | HiPass 로그인 (async Playwright) |
| `scraper.py::navigate_to_lookup()` | 통행내역 조회 페이지 이동 |
| `scraper.py::capture_date()` | 날짜별 팝업 스크린샷 캡처 |
| `scraper.py::capture_last_n_days()` | N일치 일괄 캡처 + 진행 콜백 |
| `scheduler.py::delete_old_screenshots()` | 보관 기간 초과 PNG 삭제 |
| `scheduler.py::scheduled_capture()` | 스케줄 실행 함수 |

## 기존 코드 (hipass_hwp_integrated.py)

Windows 전용 데스크탑 앱 원본. 참조용으로 보관. 웹 서비스와 별개로 독립 실행 가능.

## Playwright CSS 셀렉터 (HiPass)

- 로그인 ID: `#per_user_id`
- 로그인 PW: `#per_passwd`
- 로그인 버튼: `#per_login`
- 차량 선택: `#ecd_no`
- 조회 시작일: `#sDate_view`
- 조회 종료일: `#eDate_view`
- 조회 버튼: `#lookupBtn a`
- 결과 iframe: `if_main_post` (name 속성)
- 영수증 팝업 버튼: `#billAll`
- 팝업 캡처 대상: `.popup_content`

## 포트

- 호스트: **8007**, 컨테이너 내부: **8000**
