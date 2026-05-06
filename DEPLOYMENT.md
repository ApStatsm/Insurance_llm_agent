# 보험 약관 AI 챗봇 배포 가이드

이 문서는 공모전 데모 앱을 다른 사람이 접속할 수 있도록 배포하기 위한 최소 절차를 정리한 문서입니다.

## 권장 배포 방식

가장 간단한 방식은 Streamlit Community Cloud에 GitHub 저장소를 연결하는 것입니다.

- 배포 엔트리 파일: `app/main.py`
- Python 의존성 파일: `requirements.txt`
- 앱 실행 명령: Streamlit Cloud가 `app/main.py`를 기준으로 자동 실행
- OpenAI API 키: 저장소에 올리지 말고 Streamlit secrets에 등록

## 배포 전 반드시 확인할 것

1. 실제 API 키 파일은 GitHub에 올리지 않습니다.
   - `config/OpenAI api.txt`
   - `config/Gemini api.txt`
   - `config/LlamaCloud API.txt`

2. 업로드 파일과 접수 데이터는 배포 저장소에 올리지 않습니다.
   - `data/uploads/`
   - `data/tickets/`

3. 데모 고객 DB는 가상 고객만 포함합니다.
   - `data/customer_db/customers.csv`
   - 현재 `CUST-0001` ~ `CUST-0050`은 데모용 가상 고객입니다.
   - 비밀번호 `1234`는 데모용이며 실제 서비스에 사용하면 안 됩니다.

4. Vector DB는 앱 실행에 필요합니다.
   - `data/vectorstore/insurance_chroma_db/`
   - 저장소 용량 정책에 걸리지 않는지 확인합니다.

## Streamlit Community Cloud 배포 순서

1. GitHub에 새 저장소를 만듭니다.
2. 이 프로젝트를 GitHub 저장소에 push합니다.
3. Streamlit Community Cloud에서 새 앱을 생성합니다.
4. 저장소, 브랜치, 메인 파일을 선택합니다.
   - Main file path: `app/main.py`
5. Advanced settings 또는 Secrets에 아래 값을 등록합니다.
   - Python version: `3.12`

```toml
OPENAI_API_KEY = "sk-..."
```

6. 배포 후 로그인 화면에서 데모 계정으로 접속합니다.
   - 고객 ID: `CUST-0001` ~ `CUST-0050`
   - 비밀번호: `1234`

주의: Chroma, protobuf, sentence-transformers 계열 의존성은 최신 Python 런타임에서 깨질 수 있습니다.
Streamlit Community Cloud의 Advanced settings에서 Python을 `3.12`로 선택해 배포하세요.
이미 Python 3.14로 생성된 앱은 설정만 바꿔서는 런타임이 바뀌지 않을 수 있으므로,
앱을 삭제한 뒤 같은 저장소/도메인으로 다시 배포하면서 Python 3.12를 선택하는 방식을 권장합니다.

## 로컬 실행

```bash
streamlit run app/main.py
```

로컬에서는 기존 구현 순서대로 다음 중 하나에서 API 키를 읽습니다.

1. Streamlit secrets
2. `OPENAI_API_KEY` 환경변수
3. `config/OpenAI api.txt`

배포 환경에서는 1번 Streamlit secrets 사용을 권장합니다.

## GitHub에 올리기 전 체크리스트

```bash
python3 -m compileall app scripts
python3 scripts/test_routing.py
```

실제 커밋 전에는 아래 명령으로 민감 파일이 staged 되었는지 확인합니다.

```bash
git status
```

아래 파일이 GitHub에 올라가면 안 됩니다.

- `.streamlit/secrets.toml`
- `config/*.txt`
- `data/uploads/*`
- `data/tickets/*`

## 데모 계정

대표 테스트 계정:

- 자동차/실손 복수 가입: `CUST-0001 / 1234`
- 암보험 가입: `CUST-0002 / 1234`
- 자동차보험 가입: `CUST-0003 / 1234`
- 치아보험 가입: `CUST-0004 / 1234`
- 3개 상품 가입: `CUST-0005 / 1234`

## 현재 한계

- 로그인은 데모용 간편 인증입니다.
- 모든 데모 계정 비밀번호는 `1234`입니다.
- 실제 고객 개인정보, 실제 보험 계약 데이터, 실제 청구 API와 연결되어 있지 않습니다.
- 배포된 앱을 공개하면 OpenAI API 사용량이 발생할 수 있습니다.
- 다수 사용자가 동시에 접속할 경우 무료 배포 환경에서는 속도가 느려질 수 있습니다.

## 실제 서비스화 시 필요한 작업

- 본인인증 또는 SSO 연동
- 비밀번호 해시/솔트 적용
- 고객별 권한 분리
- 업로드 파일 암호화 저장
- 접수 데이터 DB 이전
- API 사용량 제한
- 운영 로그 및 감사 로그 분리
- 개인정보 마스킹 정책 강화
