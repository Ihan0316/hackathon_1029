import google.generativeai as genai
from fastapi import FastAPI, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
import os
import logging
from typing import Optional, Dict
from pathlib import Path
import csv
import re
import json

# --- 로깅 설정 ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# --- 1. 기본 설정 ---
# API 키 설정 (우선순위: 환경변수 > .env 파일 > 직접 입력)
# 방법 1: 환경변수 사용 (권장)
API_KEY = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "admin")

# 방법 2: .env 파일 지원 (python-dotenv 필요시)
try:
    from dotenv import load_dotenv
    load_dotenv()
    if not API_KEY:
        API_KEY = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
except ImportError:
    pass  # python-dotenv가 없어도 계속 진행

# 방법 3: 코드에 직접 입력 (개발용 - 프로덕션에서는 사용하지 마세요)
if not API_KEY:
    # 여기에 직접 API 키를 입력할 수 있습니다 (비추천)
    API_KEY = ""  # 예: "AIzaSy..."

if not API_KEY:
    logger.error("API_KEY가 설정되지 않았습니다.")
    logger.error("다음 중 하나의 방법으로 설정하세요:")
    logger.error("1. 환경변수: export GOOGLE_API_KEY='your-key'")
    logger.error("2. .env 파일: GOOGLE_API_KEY=your-key (python-dotenv 필요)")
    logger.error("3. 코드에 직접 입력: main.py의 API_KEY 변수에 키 입력")
    raise ValueError("GOOGLE_API_KEY가 필요합니다. 위 방법 중 하나로 설정하세요.")

try:
    genai.configure(api_key=API_KEY)
    model = genai.GenerativeModel('gemini-2.5-pro')
    logger.info("Gemini API 초기화 완료: gemini-2.5-pro")
except Exception as e:
    logger.error(f"Gemini API 초기화 실패: {e}")
    raise

app = FastAPI(title="통(通)역기 API")

# --- 2. CORS 미들웨어 설정 ---
# 개발 환경: 모든 origin 허용 (필요시 제한)
origins = [
    "http://localhost",
    "http://localhost:3000",
    "http://localhost:8000",
    "http://localhost:8080",
    "http://127.0.0.1:5500",
    "http://127.0.0.1:3000",
    "http://127.0.0.1:8000",
    "file://",  # 로컬 HTML 파일에서 접근
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)
logger.info(f"CORS 설정 완료. 허용된 origins: {origins}")

# --- 정적 파일 서빙 (HTML 파일 제공) ---
# 프로젝트 루트 디렉토리 가져오기
BASE_DIR = Path(__file__).parent
HTML_FILE = BASE_DIR / "main.html"
SUGGEST_FILE = BASE_DIR / "suggestions.json"

# HTML 파일 경로 로깅
logger.info(f"HTML 파일 경로: {HTML_FILE}")
logger.info(f"HTML 파일 존재 여부: {HTML_FILE.exists()}")
QUIZ_FILE = BASE_DIR / "message.json"

@app.get("/")
@app.get("/main.html")
async def read_index():
    """메인 HTML 페이지 제공 - localhost:8000/ 으로 접속 가능"""
    if not HTML_FILE.exists():
        logger.error(f"HTML 파일을 찾을 수 없습니다: {HTML_FILE}")
        raise HTTPException(
            status_code=404,
            detail=f"main.html 파일을 찾을 수 없습니다. 경로: {HTML_FILE}"
        )
    
    logger.info(f"HTML 파일 제공 중: {HTML_FILE}")
    # HTML 파일 내용을 읽어서 직접 반환 (다운로드 방지)
    with open(HTML_FILE, 'r', encoding='utf-8') as f:
        html_content = f.read()
    
    from fastapi.responses import HTMLResponse
    return HTMLResponse(content=html_content)

logger.info("정적 파일 서빙 설정 완료.")
logger.info("✅ http://localhost:8000/ 에서 main.html 접속 가능합니다.")
logger.info("✅ http://localhost:8000/main.html 도 접속 가능합니다.")

# --- CSV 기반 신조어 사전 로드 ---
CSV_FILE = BASE_DIR / "slang_dict.csv"
slang_dict: Dict[str, Dict[str, str]] = {}

def load_slang_dict():
    """CSV 파일에서 신조어 → 표준어 매핑 로드"""
    global slang_dict
    slang_dict = {}
    
    if not CSV_FILE.exists():
        logger.info(f"CSV 파일이 없습니다. 새로 생성합니다: {CSV_FILE}")
        # 기본 CSV 파일 생성
        with open(CSV_FILE, 'w', encoding='utf-8', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['slang', 'standard'])  # 헤더
            writer.writerow(['알잘딱깔센', '알아서 잘 딱 깔끔하고 센스있게'])
            writer.writerow(['킹받네', '왕짜증나네'])
            writer.writerow(['당모치', '당연히 모든 치킨은 옳으니까'])
            writer.writerow(['폼 미쳤죠', '멋지죠'])
        logger.info("기본 CSV 파일 생성 완료")
    
    try:
        # 1차 로드하여 헤더 확인
        with open(CSV_FILE, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            fieldnames = reader.fieldnames or []
            needs_migration = 'explain' not in fieldnames
            rows = list(reader)

        # 헤더에 explain이 없으면 마이그레이션(빈 explain 추가)
        if needs_migration:
            try:
                with open(CSV_FILE, 'w', encoding='utf-8', newline='') as fw:
                    writer = csv.DictWriter(fw, fieldnames=['slang', 'standard', 'explain'])
                    writer.writeheader()
                    for r in rows:
                        writer.writerow({
                            'slang': (r.get('slang') or '').strip(),
                            'standard': (r.get('standard') or '').strip(),
                            'explain': ''
                        })
                logger.info("CSV 헤더에 explain 컬럼을 추가했습니다.")
            except Exception as mig_err:
                logger.warning(f"CSV explain 컬럼 추가 실패(무시 가능): {mig_err}")

        # 최종 로드
        with open(CSV_FILE, 'r', encoding='utf-8') as f2:
            reader2 = csv.DictReader(f2)
            for row in reader2:
                slang = (row.get('slang') or '').strip()
                standard = (row.get('standard') or '').strip()
                explain = (row.get('explain') or '').strip()
                if slang and standard:
                    slang_dict[slang] = {"standard": standard, "explain": explain}
        logger.info(f"CSV 사전 로드 완료: {len(slang_dict)}개 항목")
    except Exception as e:
        logger.error(f"CSV 파일 로드 오류: {e}")
        slang_dict = {}


def _save_slang_entry(slang: str, standard: str, explain: str = "") -> None:
    """CSV와 메모리 사전에 안전하게 저장하는 내부 공용 함수."""
    slang = (slang or "").strip()
    standard = (standard or "").strip()
    explain = (explain or "").strip()
    if not slang or not standard:
        raise ValueError("slang/standard must be non-empty")

    # CSV 헤더 정규화 및 append
    if not CSV_FILE.exists():
        with open(CSV_FILE, 'w', encoding='utf-8', newline='') as fw:
            writer = csv.DictWriter(fw, fieldnames=['slang', 'standard', 'explain'])
            writer.writeheader()
            writer.writerow({'slang': slang, 'standard': standard, 'explain': explain})
    else:
        with open(CSV_FILE, 'r', encoding='utf-8') as fr:
            reader = csv.DictReader(fr)
            if 'explain' not in (reader.fieldnames or []):
                rows = list(reader)
                with open(CSV_FILE, 'w', encoding='utf-8', newline='') as fw:
                    writer = csv.DictWriter(fw, fieldnames=['slang', 'standard', 'explain'])
                    writer.writeheader()
                    for r in rows:
                        writer.writerow({'slang': (r.get('slang') or '').strip(), 'standard': (r.get('standard') or '').strip(), 'explain': ''})
        # 안전: 마지막 줄 개행 보장 후 append
        with open(CSV_FILE, 'a+', encoding='utf-8', newline='') as fa:
            try:
                fa.seek(0, 2)  # EOF로 이동
                pos = fa.tell()
                if pos > 0:
                    fa.seek(pos - 1)
                    last = fa.read(1)
                    if last not in ('\n', '\r'):
                        fa.write('\n')
            except Exception:
                pass
            writer = csv.DictWriter(fa, fieldnames=['slang', 'standard', 'explain'])
            writer.writerow({'slang': slang, 'standard': standard, 'explain': explain})

    # 메모리 사전 갱신
    slang_dict[slang] = {"standard": standard, "explain": explain}
    logger.info(f"CSV 사전 추가: {slang} → {standard} ({explain})")


def _read_csv_rows() -> list:
    rows = []
    if not CSV_FILE.exists():
        return rows
    with open(CSV_FILE, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for r in reader:
            rows.append({
                'slang': (r.get('slang') or '').strip(),
                'standard': (r.get('standard') or '').strip(),
                'explain': (r.get('explain') or '').strip(),
            })
    return rows


def _write_csv_rows(rows: list) -> None:
    with open(CSV_FILE, 'w', encoding='utf-8', newline='') as fw:
        writer = csv.DictWriter(fw, fieldnames=['slang', 'standard', 'explain'])
        writer.writeheader()
        for r in rows:
            writer.writerow({
                'slang': r.get('slang', ''),
                'standard': r.get('standard', ''),
                'explain': r.get('explain', ''),
            })


# --- 제안 큐 유틸 ---
import json

def _load_suggestions():
    if not SUGGEST_FILE.exists():
        return []
    try:
        with open(SUGGEST_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
            return data if isinstance(data, list) else []
    except Exception:
        return []

def _save_suggestions(items):
    try:
        with open(SUGGEST_FILE, 'w', encoding='utf-8') as f:
            json.dump(items, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.warning(f"제안 큐 저장 실패: {e}")

def preprocess_text_with_dict(text: str) -> tuple:
    """
    텍스트를 CSV 사전 기반으로 전처리
    Returns: (전처리된 텍스트, 치환된 단어 정보)
    """
    processed_text = text
    replaced_words = []
    
    # CSV 사전의 단어들을 우선순위대로 매칭 (긴 단어부터)
    sorted_slangs = sorted(slang_dict.keys(), key=len, reverse=True)
    
    for slang in sorted_slangs:
        if slang in processed_text or re.search(r"[A-Za-z]", slang):
            entry = slang_dict[slang]
            standard = entry.get('standard', '')

            # 영어(영문자) 신조어는 대/소문자 구분 없이 치환
            if re.search(r"[A-Za-z]", slang):
                pattern_en = re.compile(rf"{re.escape(slang)}", re.IGNORECASE)
                processed_text, n = pattern_en.subn(standard, processed_text)
                if n > 0:
                    replaced_words.append(f"{slang} → {standard}")
                continue

            # 한글 신조어: 붙은 조사/어미까지 안전하게 치환(뒤 한글 0~2자 보존)
            pattern_ko = re.compile(rf"{re.escape(slang)}(?P<suffix>[가-힣]{{0,2}})")

            def _replace(m: re.Match) -> str:
                suffix = m.group('suffix') or ''
                return standard + (f" {suffix}" if suffix else '')

            processed_text, n = pattern_ko.subn(_replace, processed_text)
            if n > 0:
                replaced_words.append(f"{slang} → {standard}")
    
    logger.info(f"CSV 전처리 결과: '{text}' → '{processed_text}'")
    # --- 2차: 퍼지(오타) 매칭 ---
    try:
        if slang_dict:
            def levenshtein(a: str, b: str) -> int:
                la, lb = len(a), len(b)
                if la == 0:
                    return lb
                if lb == 0:
                    return la
                dp = list(range(lb + 1))
                for i in range(1, la + 1):
                    prev = dp[0]
                    dp[0] = i
                    for j in range(1, lb + 1):
                        cur = dp[j]
                        cost = 0 if a[i - 1] == b[j - 1] else 1
                        dp[j] = min(dp[j] + 1, dp[j - 1] + 1, prev + cost)
                        prev = cur
                return dp[lb]

            # 토큰 단위로 비교 (한글/영문/숫자 덩어리)
            token_pattern = re.compile(r"[가-힣A-Za-z0-9]+")
            tokens = list(token_pattern.finditer(processed_text))
            if tokens:
                result_parts = []
                last_idx = 0
                sorted_slangs = list(slang_dict.keys())
                for m in tokens:
                    # 사이 구간 그대로 추가
                    result_parts.append(processed_text[last_idx:m.start()])
                    token = m.group(0)
                    # 순수 한글 일반어는 퍼지 매칭 제외(정확 일치만 허용)
                    if re.fullmatch(r"[가-힣]+", token) and token not in slang_dict:
                        result_parts.append(token)
                        last_idx = m.end()
                        continue
                    best_key = None
                    best_dist = 10**9
                    token_lower = token.lower()
                    for key in sorted_slangs:
                        key_cmp = key
                        t_cmp = token
                        # 영문 포함 시 대소문자 무시 비교
                        if re.search(r"[A-Za-z]", key) or re.search(r"[A-Za-z]", token):
                            key_cmp = key.lower()
                            t_cmp = token_lower
                        d = levenshtein(t_cmp, key_cmp)
                        if d < best_dist:
                            best_dist = d
                            best_key = key
                            if best_dist == 0:
                                break
                    # 길이에 따른 임계값 + 거리/길이 비율 임계값(과치환 방지)
                    L = len(token)
                    threshold = 1 if L <= 4 else (2 if L <= 8 else 3)
                    ratio_ok = False
                    if best_key is not None and best_dist > 0:
                        denom = max(len(token_lower), len(best_key))
                        if denom == 0:
                            ratio_ok = False
                        else:
                            ratio_ok = (best_dist / denom) <= 0.34  # 보수적 임계값
                    if best_key is not None and best_dist > 0 and best_dist <= threshold and ratio_ok:
                        standard = slang_dict[best_key].get('standard', '')
                        result_parts.append(standard)
                        replaced_words.append(f"{token} ≈ {best_key} → {standard}")
                    else:
                        result_parts.append(token)
                    last_idx = m.end()
                result_parts.append(processed_text[last_idx:])
                processed_text = ''.join(result_parts)
    except Exception as e:
        logger.warning(f"퍼지 매칭 단계 건너뜀: {e}")

    return processed_text, "; ".join(replaced_words) if replaced_words else ""

# 앱 시작 시 CSV 로드
load_slang_dict()

# --- 3. 프롬프트 정의 (최종 수정본) ---

PROMPT_MODE_A = """
당신은 '신조어 메시지'를 누구나 알아들을 수 있는 '표준어 문장'으로 즉시 변환하는 AI입니다.
**핵심 규칙:**
1. 해설/설명/메타발화 금지. (예: "이건 ~라는 뜻이에요" X, 따옴표/접두사/번호 X)
2. 문장 자체만 직접 변환. 내용 생략/요약 금지, 원문의 정보와 길이를 가능한 한 보존.
3. 원문의 정서/뉘앙스 그대로 유지(정중/친근 등).
4. 신조어는 (괄호) 안에 아주 간결한 부연만 허용.
5. 입력에 이미 표준어로 치환된 단어가 있으면 그대로 사용.
6. 출력 형식: 변환된 한국어 문장만. 불릿/따옴표/접두사/영어/해설 금지.
7. 줄바꿈/코드블록/목록 금지. 끝은 마침표/물음표/느낌표 등 문장부호로 마무리.

{replacement_info}

[입력]: {user_text}
[출력(문장만)]:
"""

PROMPT_MODE_B = """
당신은 '표준어 문장'을 10대가 좋아할 '유머러스한 MZ/신조어 톤'으로 즉시 변환합니다.
규칙: 해설/설명 금지, 출력은 변환된 문장만, 불릿/따옴표/접두사/영어 금지, 줄바꿈 금지, 문장부호로 마무리, 내용 생략/요약 금지.

[입력]: {user_text}
[출력(문장만)]:
"""

# [★수정됨★] 제주어 예시가 추가되었습니다.
PROMPT_MODE_C = """
당신은 '사투리'를 '표준어'로 통역합니다.
규칙: 해설/설명 금지, 출력은 표준어 문장만, 불릿/따옴표/접두사/영어 금지, 줄바꿈 금지, 문장부호로 마무리. 필요한 경우 (괄호)로 1개 단어만 아주 간단히 부연 가능.

[입력]: {user_text}
[출력(문장만)]:
"""

PROMPT_MODE_D = """
당신은 '표준어'를 요청된 '지역 사투리'로 변환합니다.
규칙: 해설/설명 금지, 출력은 변환된 사투리 문장만, 불릿/따옴표/접두사/영어 금지, 줄바꿈 금지, 문장부호로 마무리.

[입력]: ({region} 버전) {user_text}
[출력(문장만)]:
"""

# --- 4. API 엔드포인트 정의 ---

class TranslateRequest(BaseModel):
    text: str
    mode: str  
    region: str = "전라도" 
    
    class Config:
        # 입력 검증 예제 추가
        schema_extra = {
            "example": {
                "text": "할머니! 저 알잘딱깔센하게 과제 끝냈어요.",
                "mode": "A",
                "region": "전라도"
            }
        } 


@app.post("/translate")
async def translate_text(request: TranslateRequest):
    try:
        # 입력 검증
        if not request.text or not request.text.strip():
            logger.warning("빈 텍스트 입력 받음")
            raise HTTPException(status_code=400, detail="변환할 텍스트가 비어있습니다.")
        
        if len(request.text) > 5000:
            logger.warning(f"텍스트가 너무 김: {len(request.text)}자")
            raise HTTPException(status_code=400, detail="텍스트는 5000자 이하여야 합니다.")
        
        if request.mode not in ["A", "B", "C", "D"]:
            logger.warning(f"잘못된 mode: {request.mode}")
            raise HTTPException(status_code=400, detail=f"Invalid mode: {request.mode}. 허용된 값: A, B, C, D")
        
        # === 1단계: CSV 사전 기반 우선 치환 (모든 모드에서 먼저 수행) ===
        original_text = request.text
        preprocessed_text = request.text
        replacement_info = ""
        
        # CSV에서 신조어를 먼저 찾아서 표준어로 치환
        if slang_dict:
            preprocessed_text, replaced_str = preprocess_text_with_dict(request.text)
            if replaced_str:
                replacement_info = f"**CSV 사전에서 찾아 치환한 단어들**: {replaced_str}\n치환된 단어들은 이미 표준어로 바뀌었으므로 그대로 사용하세요.\n\n"
                logger.info(f"✅ CSV 우선 치환 완료: {replaced_str}")
                logger.info(f"   원문: '{original_text}'")
                logger.info(f"   치환: '{preprocessed_text}'")
        else:
            logger.info("CSV 사전이 비어있습니다. 원문 그대로 사용합니다.")
        
        # === 2단계: 치환된 텍스트로 프롬프트 생성 ===
        final_prompt = ""
        try:
            if request.mode == "A":
                # Mode A: 신조어 → 표준어
                final_prompt = PROMPT_MODE_A.format(
                    user_text=preprocessed_text,
                    replacement_info=replacement_info if replacement_info else ""
                )
            elif request.mode == "B":
                # Mode B: 표준어 → 신조어
                final_prompt = PROMPT_MODE_B.format(user_text=preprocessed_text)
            elif request.mode == "C":
                # Mode C: 사투리 → 표준어
                final_prompt = PROMPT_MODE_C.format(user_text=preprocessed_text)
            elif request.mode == "D":
                # Mode D: 표준어 → 사투리
                final_prompt = PROMPT_MODE_D.format(region=request.region, user_text=preprocessed_text)
        except KeyError as e:
            logger.error(f"프롬프트 포맷팅 오류: {e}")
            raise HTTPException(status_code=500, detail=f"프롬프트 생성 오류: {e}")
        
        logger.info(f"번역 요청 - Mode: {request.mode}, Region: {request.region}")
        logger.info(f"   원문 길이: {len(original_text)}자")
        if preprocessed_text != original_text:
            logger.info(f"   CSV 치환 후: {len(preprocessed_text)}자 (변경: {len(original_text)} → {len(preprocessed_text)})")
        else:
            logger.info(f"   CSV 치환 없음: 원문 그대로 사용")
        
        # === 3단계: 치환된 텍스트를 모델에 전달 ===
        logger.info(f"모델에 전달할 텍스트: '{preprocessed_text[:100]}{'...' if len(preprocessed_text) > 100 else ''}'")
        
        # Gemini API 호출
        try:
            # 안전성 설정
            generation_config = {
                "temperature": 0.7,
                "top_p": 0.8,
                "top_k": 40,
                # 긴 문장도 생략 없이 모두 출력되도록 출력 토큰 한도를 충분히 크게 설정
                "max_output_tokens": 8192,
            }
            
            # 안전성 설정 (BLOCK_ONLY_HIGH로 완화)
            try:
                from google.generativeai.types import HarmCategory, HarmBlockThreshold
                # 일부 SDK 버전에서 CIVIC_INTEGRITY 미지원 → 제외
                safety_settings = [
                    {"category": HarmCategory.HARM_CATEGORY_HATE_SPEECH, "threshold": HarmBlockThreshold.BLOCK_ONLY_HIGH},
                    {"category": HarmCategory.HARM_CATEGORY_HARASSMENT, "threshold": HarmBlockThreshold.BLOCK_ONLY_HIGH},
                    {"category": HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT, "threshold": HarmBlockThreshold.BLOCK_ONLY_HIGH},
                    {"category": HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT, "threshold": HarmBlockThreshold.BLOCK_ONLY_HIGH},
                ]
            except ImportError:
                # enum을 사용할 수 없는 경우 문자열로 시도
                safety_settings = [
                    {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_ONLY_HIGH"},
                    {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_ONLY_HIGH"},
                    {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_ONLY_HIGH"},
                    {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_ONLY_HIGH"},
                ]
            
            response = model.generate_content(
                final_prompt,
                generation_config=generation_config,
                safety_settings=safety_settings
            )
            
            # 응답 검증
            if not response:
                logger.error("Gemini API가 응답을 반환하지 않았습니다.")
                raise HTTPException(status_code=500, detail="변환 결과를 받을 수 없습니다. 다시 시도해주세요.")
            
            # finish_reason 확인
            candidates = getattr(response, 'candidates', [])
            result_text = ""
            skip_normal_processing = False
            
            if candidates:
                finish_reason = candidates[0].finish_reason if hasattr(candidates[0], 'finish_reason') else None
                if finish_reason == 2:  # SAFETY: 안전성 필터에 의해 차단됨
                    logger.warning(f"안전성 필터에 의해 차단됨. finish_reason: {finish_reason}, 입력: {request.text[:50]}...")
                    
                    # 재시도: 간단한 프롬프트로 재시도
                    logger.info("간단한 프롬프트로 재시도합니다.")
                    try:
                        if request.mode == "A":
                            simple_prompt = f"다음 문장을 표준어로 바꿔주세요:\n{preprocessed_text}"
                        else:
                            simple_prompt = f"다음 문장을 변환해주세요:\n{preprocessed_text}"
                        
                        retry_response = model.generate_content(
                            simple_prompt,
                            generation_config=generation_config,
                            safety_settings=safety_settings
                        )
                        
                        retry_candidates = getattr(retry_response, 'candidates', [])
                        if retry_candidates:
                            retry_finish_reason = retry_candidates[0].finish_reason if hasattr(retry_candidates[0], 'finish_reason') else None
                            if retry_finish_reason == 2:
                                raise HTTPException(
                                    status_code=400,
                                    detail="입력 텍스트가 안전 정책에 의해 차단되었습니다. 다른 문장으로 시도해주세요."
                                )
                        
                        try:
                            result_text = retry_response.text.strip()
                            logger.info("재시도 성공")
                            skip_normal_processing = True
                        except (ValueError, AttributeError):
                            if retry_candidates and hasattr(retry_candidates[0], 'content'):
                                parts = getattr(retry_candidates[0].content, 'parts', [])
                                if parts:
                                    result_text = "".join([part.text for part in parts if hasattr(part, 'text')]).strip()
                                    skip_normal_processing = True
                                else:
                                    raise HTTPException(status_code=400, detail="입력 텍스트를 처리할 수 없습니다.")
                            else:
                                raise HTTPException(status_code=400, detail="입력 텍스트를 처리할 수 없습니다.")
                    except HTTPException:
                        raise
                    except Exception as retry_err:
                        logger.error(f"재시도 실패: {retry_err}", exc_info=True)
                        raise HTTPException(
                            status_code=400,
                            detail="입력 텍스트가 안전 정책에 의해 차단되었습니다. 다른 문장으로 시도해주세요."
                        )
                elif finish_reason == 3:  # RECITATION: 저작권 문제
                    logger.warning(f"저작권 문제. finish_reason: {finish_reason}")
                    raise HTTPException(
                        status_code=400,
                        detail="저작권 보호 콘텐츠가 포함되어 있습니다."
                    )
            
            # 재시도에서 이미 처리된 경우 건너뛰기
            if skip_normal_processing and result_text:
                logger.info("재시도에서 이미 처리됨, 정상 응답 반환")
                return {"result": result_text, "replaced": replaced_str if 'replaced_str' in locals() else ""}
            
            # response.text 안전하게 접근
            if not result_text:
                try:
                    result_text = response.text.strip()
                except (ValueError, AttributeError) as e:
                    logger.error(f"응답 텍스트 추출 실패: {e}")
                    # 대안: parts에서 직접 추출
                    try:
                        if candidates and hasattr(candidates[0], 'content'):
                            parts = getattr(candidates[0].content, 'parts', [])
                            if parts:
                                result_text = "".join([part.text for part in parts if hasattr(part, 'text')]).strip()
                    except Exception as e2:
                        logger.error(f"대안 추출도 실패: {e2}")
            
            if not result_text:
                logger.warning("응답이 비어있음")
                raise HTTPException(
                    status_code=500,
                    detail="변환 결과가 비어있습니다. 다시 시도해주세요."
                )
            
            logger.info(f"번역 성공 - 결과 길이: {len(result_text)}")
            return {"result": result_text, "replaced": replaced_str if 'replaced_str' in locals() else ""}
        
        except HTTPException:
            raise
        
        except genai.types.BlockedPromptException as e:
            logger.error(f"차단된 프롬프트: {e}")
            raise HTTPException(
                status_code=400,
                detail="입력 텍스트가 안전 정책에 의해 차단되었습니다. 다른 문장으로 시도해주세요."
            )
        
        except genai.types.StopCandidateException as e:
            logger.error(f"후보 생성 중단: {e}")
            raise HTTPException(
                status_code=500,
                detail="응답 생성이 중단되었습니다. 다시 시도해주세요."
            )
        
        except Exception as e:
            logger.error(f"Gemini API 호출 오류: {type(e).__name__}: {e}", exc_info=True)
            error_message = str(e)
            error_lower = error_message.lower()
            
            if "api_key" in error_lower or "authentication" in error_lower:
                raise HTTPException(
                    status_code=401,
                    detail="[인증 오류] API 키가 유효하지 않습니다. 환경변수 GOOGLE_API_KEY를 확인하세요."
                )
            
            if "404" in error_message or "not found" in error_lower:
                raise HTTPException(
                    status_code=404,
                    detail=f"[모델 오류] 모델을 찾을 수 없습니다. 모델 이름: gemini-2.5-pro"
                )
            
            if "429" in error_message or "quota" in error_lower or "rate limit" in error_lower:
                raise HTTPException(
                    status_code=429,
                    detail="[할당량 초과] API 사용량이 초과되었습니다. 잠시 후 다시 시도해주세요."
                )
            
            if "timeout" in error_lower or "timed out" in error_lower:
                raise HTTPException(
                    status_code=504,
                    detail="[타임아웃] 요청 시간이 초과되었습니다. 다시 시도해주세요."
                )
            
            raise HTTPException(
                status_code=500,
                detail=f"[서버 오류] 변환 중 문제가 발생했습니다: {error_message[:200]}"
            )
    
    except HTTPException:
        raise
    
    except Exception as e:
        logger.error(f"예상치 못한 오류 발생: {type(e).__name__}: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"서버 내부 오류가 발생했습니다: {str(e)[:200]}"
        )


class AddSlangRequest(BaseModel):
    slang: str
    standard: str
    explain: Optional[str] = ""


@app.post("/slang")
def add_slang(req: AddSlangRequest, request: Request):
    """/slang 엔드포인트(레거시)도 바로 추가되도록 실제 구현 포함.
    관리자 토큰은 헤더 X-Admin-Token 사용.
    """
    token = request.headers.get('x-admin-token', '')
    if not ADMIN_TOKEN or token != ADMIN_TOKEN:
        raise HTTPException(status_code=403, detail="관리자만 추가할 수 있습니다.")

    slang = (req.slang or "").strip()
    standard = (req.standard or "").strip()
    explain = (req.explain or "").strip()
    if not slang or not standard:
        raise HTTPException(status_code=400, detail="slang과 standard는 비어있을 수 없습니다.")

    # 중복 확인(대소문자 무시: 영문 포함 시)
    for k in list(slang_dict.keys()):
        if (re.search(r"[A-Za-z]", k) or re.search(r"[A-Za-z]", slang)):
            if k.lower() == slang.lower():
                raise HTTPException(status_code=409, detail="이미 존재하는 신조어입니다.")
        else:
            if k == slang:
                raise HTTPException(status_code=409, detail="이미 존재하는 신조어입니다.")

    try:
        # CSV에 append (헤더 explain 보장)
        if not CSV_FILE.exists():
            with open(CSV_FILE, 'w', encoding='utf-8', newline='') as fw:
                writer = csv.DictWriter(fw, fieldnames=['slang', 'standard', 'explain'])
                writer.writeheader()
                writer.writerow({'slang': slang, 'standard': standard, 'explain': explain})
        else:
            with open(CSV_FILE, 'r', encoding='utf-8') as fr:
                reader = csv.DictReader(fr)
                if 'explain' not in (reader.fieldnames or []):
                    rows = list(reader)
                    with open(CSV_FILE, 'w', encoding='utf-8', newline='') as fw:
                        writer = csv.DictWriter(fw, fieldnames=['slang', 'standard', 'explain'])
                        writer.writeheader()
                        for r in rows:
                            writer.writerow({'slang': (r.get('slang') or '').strip(), 'standard': (r.get('standard') or '').strip(), 'explain': ''})

            with open(CSV_FILE, 'a', encoding='utf-8', newline='') as fa:
                writer = csv.DictWriter(fa, fieldnames=['slang', 'standard', 'explain'])
                writer.writerow({'slang': slang, 'standard': standard, 'explain': explain})

        # 메모리 사전 갱신
        slang_dict[slang] = {"standard": standard, "explain": explain}
        logger.info(f"CSV 사전 추가(/slang): {slang} → {standard} ({explain})")
        return {"ok": True}
    except Exception as e:
        logger.error(f"/slang 추가 실패: {e}")
        raise HTTPException(status_code=500, detail=f"추가 실패: {str(e)[:100]}")


@app.post("/slang/add")
def add_slang_admin(req: AddSlangRequest, request: Optional[object] = None):
    # 관리자 토큰 검증
    try:
        from fastapi import Request as _Req
        if isinstance(request, _Req):
            token = request.headers.get('x-admin-token', '')
        else:
            # FastAPI가 request를 주입해줌
            from fastapi import Request as R
            raise HTTPException(status_code=500, detail="Request 주입 실패")
    except Exception:
        # FastAPI가 자동으로 request를 주입하므로, 시그니처를 수정
        pass
    
    # 위 방식이 번거로워, 간단히 전용 엔드포인트로 다시 정의
    return {"detail": "deprecated"}


from fastapi import Request as _FastAPIRequest

@app.post("/slang")
def add_slang_protected(req: AddSlangRequest, request: _FastAPIRequest):
    token = request.headers.get('x-admin-token', '')
    if not ADMIN_TOKEN or token != ADMIN_TOKEN:
        raise HTTPException(status_code=403, detail="관리자만 추가할 수 있습니다.")
    slang = (req.slang or "").strip()
    standard = (req.standard or "").strip()
    explain = (req.explain or "").strip()
    if not slang or not standard:
        raise HTTPException(status_code=400, detail="slang과 standard는 비어있을 수 없습니다.")

    # 중복 확인(대소문자 무시: 영문 포함 시)
    for k in list(slang_dict.keys()):
        if (re.search(r"[A-Za-z]", k) or re.search(r"[A-Za-z]", slang)):
            if k.lower() == slang.lower():
                raise HTTPException(status_code=409, detail="이미 존재하는 신조어입니다.")
        else:
            if k == slang:
                raise HTTPException(status_code=409, detail="이미 존재하는 신조어입니다.")

    try:
        # CSV에 append
        # 헤더 보장: explain 포함으로 정규화
        if not CSV_FILE.exists():
            with open(CSV_FILE, 'w', encoding='utf-8', newline='') as fw:
                writer = csv.DictWriter(fw, fieldnames=['slang', 'standard', 'explain'])
                writer.writeheader()
                writer.writerow({'slang': slang, 'standard': standard, 'explain': explain})
        else:
            # 기존 파일 헤더 확인 후, explain 없으면 마이그레이션 수행
            with open(CSV_FILE, 'r', encoding='utf-8') as fr:
                reader = csv.DictReader(fr)
                if 'explain' not in (reader.fieldnames or []):
                    rows = list(reader)
                    with open(CSV_FILE, 'w', encoding='utf-8', newline='') as fw:
                        writer = csv.DictWriter(fw, fieldnames=['slang', 'standard', 'explain'])
                        writer.writeheader()
                        for r in rows:
                            writer.writerow({'slang': (r.get('slang') or '').strip(), 'standard': (r.get('standard') or '').strip(), 'explain': ''})
                
            with open(CSV_FILE, 'a', encoding='utf-8', newline='') as fa:
                writer = csv.DictWriter(fa, fieldnames=['slang', 'standard', 'explain'])
                writer.writerow({'slang': slang, 'standard': standard, 'explain': explain})
        # 메모리 사전 갱신
        slang_dict[slang] = {"standard": standard, "explain": explain}
        logger.info(f"CSV 사전 추가: {slang} → {standard} ({explain})")
        return {"ok": True}
    except Exception as e:
        logger.error(f"CSV 추가 실패: {e}")
        raise HTTPException(status_code=500, detail=f"CSV 추가 실패: {str(e)[:100]}")


# --- 제안 큐 엔드포인트 ---
class SuggestRequest(BaseModel):
    slang: str
    standard: str
    explain: Optional[str] = ""


@app.post("/suggest")
def suggest(req: SuggestRequest):
    slang = (req.slang or "").strip()
    standard = (req.standard or "").strip()
    explain = (req.explain or "").strip()
    if not slang or not standard:
        raise HTTPException(status_code=400, detail="slang과 standard는 비어있을 수 없습니다.")
    items = _load_suggestions()
    # 간단 중복 방지: 동일 slang(영문은 lower) 미허용
    key = slang.lower() if re.search(r"[A-Za-z]", slang) else slang
    for it in items:
        k = it.get('slang','')
        if (re.search(r"[A-Za-z]", k) or re.search(r"[A-Za-z]", slang)):
            if k.lower() == key:
                raise HTTPException(status_code=409, detail="이미 제안 큐에 존재합니다.")
        else:
            if k == key:
                raise HTTPException(status_code=409, detail="이미 제안 큐에 존재합니다.")
    item = {"id": len(items) + 1, "slang": slang, "standard": standard, "explain": explain, "status": "pending"}
    items.append(item)
    _save_suggestions(items)
    return {"ok": True, "id": item["id"]}


@app.get("/suggest/list")
def suggest_list():
    items = _load_suggestions()
    return {"items": [it for it in items if it.get('status') == 'pending']}


class SuggestActionRequest(BaseModel):
    ids: list[int]


@app.post("/suggest/approve")
def suggest_approve(req: SuggestActionRequest):
    items = _load_suggestions()
    idset = set(req.ids or [])
    approved = 0
    remaining = []
    for it in items:
        if it.get('id') in idset and it.get('status') == 'pending':
            try:
                item_type = it.get('type', 'add')
                if item_type == 'edit':
                    # 수정 요청: 기존 항목을 proposed_standard로 업데이트
                    slang = it.get('slang', '')
                    proposed_standard = it.get('proposed_standard', '')
                    explain = it.get('reason', '')
                    # CSV에서 해당 slang 찾아서 수정
                    rows = _read_csv_rows()
                    found = False
                    for r in rows:
                        if r.get('slang') == slang:
                            r['standard'] = proposed_standard.strip()
                            if explain:
                                r['explain'] = explain.strip()
                            found = True
                            break
                    if found:
                        _write_csv_rows(rows)
                        # 메모리 갱신
                        slang_dict[slang] = {"standard": proposed_standard, "explain": explain}
                        logger.info(f"승인: 수정 요청 반영 - {slang} → {proposed_standard}")
                    else:
                        logger.warning(f"승인 실패: 수정할 항목 없음 - {slang}")
                else:
                    # 추가 요청: 새 항목을 CSV에 추가
                    _save_slang_entry(it.get('slang',''), it.get('standard',''), it.get('explain',''))
                approved += 1
            except Exception as e:
                logger.error(f"승인 중 CSV 저장 실패: {e}")
                continue
            continue
        remaining.append(it)
    _save_suggestions(remaining)
    return {"ok": True, "approved": approved}


@app.post("/suggest/reject")
def suggest_reject(req: SuggestActionRequest):
    items = _load_suggestions()
    idset = set(req.ids or [])
    rejected = 0
    remaining = []
    for it in items:
        if it.get('id') in idset and it.get('status') == 'pending':
            # 큐에서 제거(파일에서도 삭제 효과)
            rejected += 1
            continue
        remaining.append(it)
    _save_suggestions(remaining)
    return {"ok": True, "rejected": rejected}


# 수정 요청 전용 엔드포인트 (수정은 관리자 승인 후에만 반영)
class SuggestEditRequest(BaseModel):
    slang: str
    current_standard: str
    proposed_standard: str
    reason: Optional[str] = ""


@app.post("/suggest/edit")
def suggest_edit(req: SuggestEditRequest):
    slang = (req.slang or "").strip()
    current_standard = (req.current_standard or "").strip()
    proposed_standard = (req.proposed_standard or "").strip()
    reason = (req.reason or "").strip()
    if not slang or not proposed_standard:
        raise HTTPException(status_code=400, detail="신조어와 제안 표준어는 필수입니다.")
    items = _load_suggestions()
    item = {
        "id": len(items) + 1,
        "type": "edit",
        "slang": slang,
        "current_standard": current_standard,
        "proposed_standard": proposed_standard,
        "reason": reason,
        "status": "pending",
    }
    items.append(item)
    _save_suggestions(items)
    return {"ok": True, "id": item["id"]}


# --- 사전 관리 엔드포인트 ---
@app.get("/slang/list")
def slang_list():
    items = _read_csv_rows()
    # 간단 정렬
    items.sort(key=lambda x: x.get('slang', ''))
    return {"items": items}


class UpdateSlangRequest(BaseModel):
    original_slang: str
    slang: str
    standard: str
    explain: Optional[str] = ""


from fastapi import Request as _ReqForAdmin

@app.post("/slang/update")
def slang_update(req: UpdateSlangRequest, request: _ReqForAdmin):
    token = request.headers.get('x-admin-token', '')
    if not ADMIN_TOKEN or token != ADMIN_TOKEN:
        raise HTTPException(status_code=403, detail="관리자만 수정할 수 있습니다.")
    rows = _read_csv_rows()
    found = False
    for r in rows:
        if r.get('slang') == req.original_slang:
            r['slang'] = (req.slang or '').strip()
            r['standard'] = (req.standard or '').strip()
            r['explain'] = (req.explain or '').strip()
            found = True
            break
    if not found:
        raise HTTPException(status_code=404, detail="수정할 항목을 찾을 수 없습니다.")
    _write_csv_rows(rows)
    # 메모리 갱신
    if req.original_slang in slang_dict:
        slang_dict.pop(req.original_slang, None)
    slang_dict[req.slang] = {"standard": req.standard, "explain": req.explain or ''}
    return {"ok": True}


class DeleteSlangRequest(BaseModel):
    slang: str


@app.post("/slang/delete")
def slang_delete(req: DeleteSlangRequest, request: _ReqForAdmin):
    token = request.headers.get('x-admin-token', '')
    if not ADMIN_TOKEN or token != ADMIN_TOKEN:
        raise HTTPException(status_code=403, detail="관리자만 삭제할 수 있습니다.")
    rows = _read_csv_rows()
    new_rows = [r for r in rows if r.get('slang') != (req.slang or '').strip()]
    if len(new_rows) == len(rows):
        raise HTTPException(status_code=404, detail="삭제할 항목을 찾을 수 없습니다.")
    _write_csv_rows(new_rows)
    slang_dict.pop(req.slang, None)
    return {"ok": True}

@app.get("/health")
def health_check():
    """헬스 체크 엔드포인트"""
    try:
        # 간단한 테스트로 API 연결 확인
        test_response = model.generate_content("테스트")
        api_status = "ok" if test_response else "error"
    except Exception as e:
        logger.warning(f"헬스 체크 실패: {e}")
        api_status = f"error: {str(e)[:100]}"
    
    return {
        "status": "healthy" if api_status == "ok" else "unhealthy",
        "api_status": api_status,
        "model": "gemini-2.5-pro"
    }


# --- 퀴즈 API ---
import random

@app.get("/quiz")
def get_quiz():
    """message.json의 문제에서 10문제를 랜덤으로 제공."""
    if not QUIZ_FILE.exists():
        raise HTTPException(status_code=404, detail="message.json 파일이 없습니다.")
    try:
        with open(QUIZ_FILE, 'r', encoding='utf-8') as f:
            # 파일이 배열 형식이 아닐 수 있어 안전 파싱
            text = f.read().strip()
            # 1) 파이썬 표기 치환(None -> null)
            text = re.sub(r"\bNone\b", "null", text)
            # 2) 스마트 따옴표 등 특수문자 정규화(문자열 내부는 그대로 두어도 JSON엔 문제 없음)
            # 3) 트레일링 콤마 제거: ,] / ,}
            text = re.sub(r",\s*\]", "]", text)
            text = re.sub(r",\s*\}", "}", text)
            # 4) 상위 객체들 사이에 콤마가 없을 수 있으므로 보정: '}{' -> '},{'
            text = re.sub(r"}\s*\n\s*{", "},{", text)
            text = re.sub(r"}\s*{", "},{", text)
            # 5) 마지막 객체 뒤에 잘못 남은 콤마 제거
            text = re.sub(r",\s*$", "", text, flags=re.S)
            # 6) message.json이 객체들로만 구성된 경우를 대비해 대괄호 보정
            if not text.startswith('['):
                text = '[' + text
            if not text.endswith(']'):
                text = text + ']'
            items = json.loads(text)
            # 필수 필드만 유지
            questions = []
            for it in items:
                q = {
                    'question': it.get('question'),
                    'choices': it.get('choices', []),
                    'answer': it.get('answer')
                }
                if q['question'] and isinstance(q['choices'], list) and q['answer'] is not None:
                    questions.append(q)
            random.shuffle(questions)
            questions = questions[:10] if len(questions) > 10 else questions
            return { 'items': questions }
    except Exception as e:
        logger.error(f"퀴즈 로드 실패: {e}")
        raise HTTPException(status_code=500, detail="퀴즈를 불러오지 못했습니다.")
