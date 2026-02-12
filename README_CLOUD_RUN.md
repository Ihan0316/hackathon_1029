# Cloud Run 배포 가이드 (초보자용)

이 프로젝트는 FastAPI(`main.py`) 기반입니다. 아래 순서대로 따라 하면 누구나 배포 가능합니다.

## 0) 준비물

- 구글 계정
- 로컬 설치: `gcloud` CLI, (선택) `docker`
  - macOS: `brew install --cask google-cloud-sdk` 후 `exec -l $SHELL`
  - 설치 확인: `gcloud --version`
- Python은 로컬에서 필수는 아니지만, 로컬 테스트하려면 `python3`, `pip` 필요

## 1) GCP 프로젝트/결제 설정 (최초 1회)

```bash
# 로그인
gcloud auth login

# 프로젝트 생성(또는 기존 프로젝트 사용)
PROJECT_ID="your-project-id"  # 고유한 ID로 교체
gcloud projects create "$PROJECT_ID"

# 현재 프로젝트로 지정
gcloud config set project "$PROJECT_ID"

# 지역 설정 (예: 서울)
gcloud config set run/region asia-northeast3

# 필요한 API 활성화
gcloud services enable \
  run.googleapis.com \
  cloudbuild.googleapis.com \
  artifactregistry.googleapis.com
```

- 결제 계정 연결: GCP 콘솔 → Billing → 프로젝트에 결제 계정 연결(무료 할당량 사용도 Billing 연결이 필요함)

## 2) 로컬에서 빠른 동작 확인(선택)

```bash
# 의존성 설치
pip install -r requirements.txt

# 로컬 실행 (http://127.0.0.1:8000)
export GOOGLE_API_KEY="YOUR_API_KEY"
uvicorn main:app --host 0.0.0.0 --port 8000
```

- 브라우저에서 `http://127.0.0.1:8000/` 접속 → `main.html`이 보여야 정상

## 3) 가장 쉬운 배포: 소스에서 바로 배포(자동 빌드)

Docker를 몰라도 됩니다. 현재 폴더를 그대로 올려 빌드·배포합니다.

```bash
SERVICE_NAME="tong-yeokgi"

gcloud run deploy "$SERVICE_NAME" \
  --source . \
  --allow-unauthenticated \
  --set-env-vars GOOGLE_API_KEY="YOUR_API_KEY" \
  --port 8080
```

- 완료되면 콘솔에 **Service URL**이 표시됩니다. 해당 URL로 누구나 접속 가능
- 재배포는 같은 명령 다시 실행

## 4) (선택) Docker 이미지로 배포

커스텀 이미지가 필요할 때 사용합니다. 이 리포에는 이미 `Dockerfile`이 있습니다.

```bash
REGION="asia-northeast3"
REPO="cloud-run-source-deploy"
IMAGE="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO}/tong-yeokgi:latest"

# (최초 1회) Artifact Registry 리포지토리 생성
gcloud artifacts repositories create "$REPO" \
  --repository-format=docker \
  --location="$REGION" \
  --description="Docker repo for Cloud Run"

# Docker 빌드/푸시
gcloud auth configure-docker "${REGION}-docker.pkg.dev"
docker build -t "$IMAGE" .
docker push "$IMAGE"

# Cloud Run 배포
gcloud run deploy tong-yeokgi \
  --image "$IMAGE" \
  --allow-unauthenticated \
  --set-env-vars GOOGLE_API_KEY="YOUR_API_KEY" \
  --port 8080
```

## 5) 환경변수/비밀 관리

- 간단히는 `--set-env-vars KEY=value`로 설정
- UI에서도 수정 가능: GCP 콘솔 → Cloud Run → 서비스 → 편집/배포 → 환경변수
- 보안상 민감 값은 Secret Manager 사용 권장(필요 시 추후 확장)

## 6) 운영 팁

- 추가 환경변수: `--set-env-vars ADMIN_TOKEN=admin` 등 복수 지정 가능
- 로그 보기:

```bash
gcloud logs tail --project "$PROJECT_ID" --service "$SERVICE_NAME" --platform managed
```

- 지역/리전 변경 시: `gcloud config set run/region <region>`
- 커스텀 도메인: Cloud Run 콘솔 → Custom Domains → 도메인 매핑 가이드 따라 DNS 설정

## 7) 비용/무료 할당량

- Cloud Run은 월 무료 할당량이 있습니다(정책/지역에 따라 변동 가능)
- 소규모 트래픽은 무료 내에서 충분, 초과 시 과금 → 콘솔 Billing에서 사용량 확인

## 8) 문제 해결(트러블슈팅)

- 404/빈 화면: `main.py`의 `/` 핸들러가 `main.html`을 반환합니다. 배포 URL 뒤에 `/`로 접속해 보세요.
- 500/시작 실패: `GOOGLE_API_KEY` 누락 또는 잘못된 키 → 환경변수 재확인
- 권한 오류: Billing 미연결이거나 API 미활성화일 수 있음 → 1단계를 재검토
- CORS: `main.py`에 기본 CORS 허용이 되어 있습니다. 외부 프론트에서 호출 시에도 대개 동작합니다.
- 포트: Cloud Run은 내부적으로 `PORT`를 주지만, 우리 컨테이너는 8080으로 청취하도록 이미 설정되어 있습니다.

## 9) 확인 체크리스트

- [ ] `gcloud --version` 확인
- [ ] 프로젝트 생성/선택 완료, Billing 연결
- [ ] `GOOGLE_API_KEY` 준비
- [ ] `gcloud run deploy ... --source .` 완료 및 URL 확인
- [ ] URL 접속 시 `main.html` 출력
