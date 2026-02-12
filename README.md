# 통(通)역기

**세대도 통하고, 지역도 통한다!**

정서·문맥 분석 기반 AI 소통 통역기. 신조어↔표준어, 사투리↔표준어를 실시간으로 변환하고, 신조어 모의고사로 재미있게 익힐 수 있는 웹 서비스입니다.

---

## 주요 기능

- **신조어 → 표준어** : MZ 신조어·줄임말을 할머니도 알아들을 표준어로 변환
- **표준어 → 신조어** : 일반 문장을 10대 톤의 신조어 문장으로 변환
- **사투리 → 표준어** : 전라도·경상도·제주 사투리를 표준어로 통역
- **표준어 → 사투리** : 표준어를 선택한 지역 사투리로 변환
- **신조어 사전** : CSV 기반 사전 + 퍼지(오타) 매칭, 관리자 추가/수정/삭제, 사용자 제안·승인
- **모의고사** : `message.json` 기반 신조어 퀴즈 (랜덤 10문항)

---

## 기술 스택

### Front-end
- **언어** : HTML, CSS, JavaScript
- **스타일** : Tailwind CSS (CDN)

### Back-end
- **프레임워크** : FastAPI
- **서버** : Uvicorn
- **언어** : Python 3.11

### AI·API
- **모델** : Google Gemini (gemini-2.5-pro)
- **SDK** : `google-generativeai`

### 데이터
- **신조어 사전** : CSV (`slang_dict.csv`) — slang, standard, explain
- **퀴즈** : JSON (`message.json`)
- **제안 큐** : JSON (`suggestions.json`)

### 배포
- **컨테이너** : Docker (Python 3.11-slim)
- **플랫폼** : Google Cloud Run

---

## 프로젝트 구조

```
hackathon_1029/
├── main.html          # 프론트엔드 (단일 페이지)
├── main.py             # FastAPI 앱 + Gemini 연동 + 사전/퀴즈/제안 API
├── requirements.txt    # Python 의존성
├── Dockerfile          # Cloud Run 배포용
├── message.json        # 모의고사 문제 데이터
├── README.md
├── README_CLOUD_RUN.md # Cloud Run 배포 가이드
└── 발표자료/           # PPT, 시연 영상
```

---

## 로컬 실행

```bash
# 의존성 설치
pip install -r requirements.txt

# API 키 설정 후 서버 실행 (기본: http://127.0.0.1:8000)
export GOOGLE_API_KEY="YOUR_GEMINI_API_KEY"
uvicorn main:app --host 0.0.0.0 --port 8000
```

브라우저에서 `http://localhost:8000/` 또는 `http://localhost:8000/main.html` 접속.

---

## API 개요

| 메서드 | 경로 | 설명 |
|--------|------|------|
| GET | `/` | 메인 HTML (`main.html`) |
| POST | `/translate` | 텍스트 변환 (mode: A/B/C/D, region 선택 가능) |
| GET | `/quiz` | 모의고사 문제 10문항 (랜덤) |
| GET | `/slang/list` | 신조어 사전 목록 |
| POST | `/slang` | 신조어 추가 (관리자: `X-Admin-Token`) |
| POST | `/suggest` | 신조어/표준어 제안 |
| GET | `/suggest/list` | 대기 중인 제안 목록 |
| POST | `/suggest/approve` | 제안 승인 (관리자) |
| POST | `/suggest/reject` | 제안 거절 |
| GET | `/health` | 헬스 체크 (Gemini 연결 확인) |

---

## 배포 (Google Cloud Run)

소스에서 바로 배포:

```bash
gcloud run deploy tong-yeokgi \
  --source . \
  --allow-unauthenticated \
  --set-env-vars GOOGLE_API_KEY="YOUR_API_KEY" \
  --port 8080
```

자세한 단계·Docker 이미지 배포·트러블슈팅은 **[README_CLOUD_RUN.md](./README_CLOUD_RUN.md)** 참고.

---

## 환경 변수

| 변수 | 필수 | 설명 |
|------|------|------|
| `GOOGLE_API_KEY` 또는 `GEMINI_API_KEY` | ✅ | Gemini API 키 |
| `ADMIN_TOKEN` | (선택) | 신조어 추가/수정/삭제·제안 승인용 (기본: `admin`) |

---

## 발표 자료

- **발표자료/**  
  - 정서·문맥 분석 기반 AI 소통 통역기 '통(通)역기' (11조) — PPT, 시연 영상

---

## 라이선스 / 기타

- 팀명: (11조) 집에 언제 가조  
- Hackathon 1029 프로젝트
