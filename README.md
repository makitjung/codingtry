# 노동사건 실무 도구 모음

이 프로젝트는 근로감독 실무를 돕기 위한 Python 도구 모음입니다.

## 포함 프로그램

1. `report.py` + `web/index.html`
- 반응형 웹 내사보고서 자동작성기
- 진정인/피진정인/사업장 등 정보를 그룹 단위로 한 번에 입력
- 답변 전체를 그대로 붙이지 않고, 관련성이 높은 사실을 선별해 보고서 초안 생성
- Markdown 보고서 출력 및 다운로드 지원
- 관련 법령/판례/질의회시는 사용자가 직접 입력하지 않고 프로그램이 AI로 자동 탐색
- `OPENAI_API_KEY`가 설정되면 OpenAI 모델 기반 추천 품질이 향상

2. `퇴직금계산기.py`
- 입/퇴사일과 최근 3개월 임금으로 퇴직금 산정

3. `통상임금계산기.py`
- 임금 항목별 통상임금 포함 여부를 보조 판단

## 실행 방법

PowerShell:

```powershell
.\run_내사보고서자동작성기.ps1
```

또는 직접:

```powershell
uv run --python 3.12 python report.py
```

실행 후 브라우저에서 아래 주소가 열립니다.

`http://127.0.0.1:8765/web/index.html`

## OpenAI 연결(선택)

PowerShell:

```powershell
$env:OPENAI_API_KEY="YOUR_API_KEY"
$env:OPENAI_MODEL="gpt-5-mini"
uv run --python 3.12 python report.py
```

키가 없으면 앱은 자동으로 규칙 기반 모드로 동작합니다.
