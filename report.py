#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""내사보고서 자동작성기 웹 서버 (그룹 입력 + AI 근거탐색).

실행:
    uv run --python 3.12 python report.py
"""

from __future__ import annotations

import argparse
import json
import os
import re
import threading
import uuid
import webbrowser
from datetime import datetime
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib import error as urlerror
from urllib import request as urlrequest


CASE_TYPES = ["임금체불", "해고/징계", "근로시간/수당", "퇴직금", "기타"]
OUTCOMES = ["기소송치", "법위반없음", "시정지시", "계속내사"]

RRN_PATTERN = re.compile(r"^\d{6}-?\d{7}$")
PHONE_PATTERN = re.compile(r"^\d{2,3}-?\d{3,4}-?\d{4}$")
DATE_PATTERN = re.compile(r"\d{4}[-./]\d{1,2}[-./]\d{1,2}")
MONEY_PATTERN = re.compile(r"\d[\d,]*\s*원")

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-5-mini").strip()
OPENAI_TIMEOUT_SECONDS = int(os.getenv("OPENAI_TIMEOUT_SECONDS", "25"))

OPENAI_SYSTEM_INTERVIEW = (
    "당신은 한국 노동사건 내사보고서 작성을 보조하는 인터뷰 AI입니다. "
    "사용자가 한 번에 입력해야 할 정보 묶음을 간결하고 실무형으로 안내하세요."
)
OPENAI_SYSTEM_REPORT = (
    "당신은 한국 노동사건 내사보고서 초안 작성 보조 AI입니다. "
    "입력 사실만 사용하고 추측 금지. 모르면 '추가 확인 필요'를 쓰세요."
)
OPENAI_SYSTEM_REF = (
    "당신은 한국 노동법 리서치 보조 AI입니다. "
    "사건유형/사실관계에 맞는 관련 법령, 판례, 질의회시를 제안하세요. "
    "불확실하면 '문서번호 확인 필요'를 명시하세요."
)
OPENAI_SYSTEM_FOLLOWUP = (
    "당신은 한국 노동사건 내사보고서 보조 AI입니다. "
    "입력된 정보가 부족하면 사건 이해에 꼭 필요한 후속질문만 만드세요. "
    "질문은 짧고 구체적으로, 한 번에 답할 수 있게 작성하세요."
)


GROUPS_COMMON = [
    {
        "id": "case_basic",
        "title": "사건 기본정보",
        "fields": [
            {"key": "case_type", "label": "사건유형", "placeholder": "임금체불 / 해고·징계 / 근로시간·수당 / 퇴직금 / 기타"},
            {"key": "investigation_period", "label": "내사 검토 기간", "placeholder": "예: 2026-01-01 ~ 2026-03-31"},
        ],
    },
    {
        "id": "complainant",
        "title": "진정인 정보",
        "fields": [
            {"key": "complainant_name", "label": "이름", "placeholder": "홍길동"},
            {"key": "complainant_rrn", "label": "주민등록번호", "placeholder": "######-#######"},
            {"key": "complainant_address", "label": "주소", "placeholder": "서울시 ..."},
            {"key": "complainant_phone", "label": "전화번호", "placeholder": "010-1234-5678"},
        ],
    },
    {
        "id": "respondent",
        "title": "피진정인 정보",
        "fields": [
            {"key": "respondent_name", "label": "이름", "placeholder": "홍길동"},
            {"key": "respondent_rrn", "label": "주민등록번호", "placeholder": "######-#######"},
            {"key": "respondent_address", "label": "주소", "placeholder": "서울시 ..."},
            {"key": "respondent_phone", "label": "전화번호", "placeholder": "010-1234-5678"},
        ],
    },
    {
        "id": "workplace",
        "title": "사업장 정보",
        "fields": [
            {"key": "workplace_name", "label": "명칭", "placeholder": "사업장 명"},
            {"key": "workplace_address", "label": "주소", "placeholder": "서울시 ..."},
            {"key": "workplace_industry", "label": "업종", "placeholder": "물류 / 제조 등"},
            {"key": "workplace_workers", "label": "상시근로자 수", "placeholder": "숫자"},
        ],
    },
    {
        "id": "review",
        "title": "내사 검토 핵심내용",
        "fields": [
            {"key": "claimant_claim", "label": "진정인 주장", "placeholder": "주요 주장과 핵심 사실"},
            {"key": "respondent_claim", "label": "피진정인 주장", "placeholder": "반박/해명 요지"},
            {"key": "evidence_summary", "label": "증거자료", "placeholder": "근로계약서, 급여대장, 근태기록 등"},
        ],
    },
]

GROUPS_CASE_EXTRA = {
    "임금체불": {
        "id": "case_extra",
        "title": "임금체불 추가정보",
        "fields": [
            {"key": "wage_unpaid_period", "label": "체불 기간", "placeholder": "예: 2026-01 ~ 2026-03"},
            {"key": "wage_unpaid_amount", "label": "체불 금액", "placeholder": "예: 7,800,000원"},
            {"key": "wage_payday_rule", "label": "정기 지급일", "placeholder": "예: 매월 25일"},
        ],
    },
    "해고/징계": {
        "id": "case_extra",
        "title": "해고/징계 추가정보",
        "fields": [
            {"key": "dismissal_date", "label": "통보일", "placeholder": "YYYY-MM-DD"},
            {"key": "dismissal_reason", "label": "해고/징계 사유", "placeholder": "사유 설명"},
            {"key": "dismissal_notice", "label": "해고예고 이행 여부", "placeholder": "30일 예고 또는 수당지급 여부"},
        ],
    },
    "근로시간/수당": {
        "id": "case_extra",
        "title": "근로시간/수당 추가정보",
        "fields": [
            {"key": "weekly_hours", "label": "주당 근로시간", "placeholder": "예: 52시간"},
            {"key": "overtime_hours", "label": "연장/야간/휴일 근로시간", "placeholder": "월 단위/기간 단위로 입력"},
            {"key": "overtime_paid", "label": "수당 지급 여부", "placeholder": "지급/미지급 및 근거"},
        ],
    },
    "퇴직금": {
        "id": "case_extra",
        "title": "퇴직금 추가정보",
        "fields": [
            {"key": "employment_start", "label": "입사일", "placeholder": "YYYY-MM-DD"},
            {"key": "employment_end", "label": "퇴사일", "placeholder": "YYYY-MM-DD"},
            {"key": "retirement_amount", "label": "퇴직금 지급/미지급 금액", "placeholder": "예: 3,200,000원"},
        ],
    },
    "기타": {
        "id": "case_extra",
        "title": "기타 사건 추가정보",
        "fields": [
            {"key": "case_specific_note", "label": "특이사항", "placeholder": "사건 특이사항"},
        ],
    },
}

GROUP_RESULT = {
    "id": "result",
    "title": "잠정 결과",
    "fields": [
        {"key": "result", "label": "결과", "placeholder": "기소송치 / 법위반없음 / 시정지시 / 계속내사"},
    ],
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="내사보고서 자동작성기 웹 서버")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-browser", action="store_true")
    return parser.parse_args()


def normalize_case_type(text: str) -> str:
    t = text.strip()
    if t in CASE_TYPES:
        return t
    if "임금" in t or "체불" in t:
        return "임금체불"
    if "해고" in t or "징계" in t:
        return "해고/징계"
    if "근로시간" in t or "연장" in t or "야간" in t or "휴일" in t:
        return "근로시간/수당"
    if "퇴직" in t:
        return "퇴직금"
    return "기타"


def _extract_response_text(payload: dict[str, Any]) -> str:
    if isinstance(payload.get("output_text"), str) and payload["output_text"].strip():
        return payload["output_text"].strip()
    chunks: list[str] = []
    for output in payload.get("output", []):
        for content in output.get("content", []):
            if content.get("type") in ("output_text", "text"):
                text = content.get("text", "")
                if isinstance(text, str) and text.strip():
                    chunks.append(text.strip())
    return "\n".join(chunks).strip()


def call_openai_text(system_prompt: str, user_prompt: str) -> str | None:
    if not OPENAI_API_KEY:
        return None
    payload = {
        "model": OPENAI_MODEL,
        "input": [
            {"role": "system", "content": [{"type": "input_text", "text": system_prompt}]},
            {"role": "user", "content": [{"type": "input_text", "text": user_prompt}]},
        ],
    }
    req = urlrequest.Request(
        "https://api.openai.com/v1/responses",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        method="POST",
        headers={
            "Authorization": f"Bearer {OPENAI_API_KEY}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urlrequest.urlopen(req, timeout=OPENAI_TIMEOUT_SECONDS) as res:
            body = res.read().decode("utf-8")
        parsed = json.loads(body)
        text = _extract_response_text(parsed)
        return text if text else None
    except (urlerror.URLError, TimeoutError, json.JSONDecodeError, OSError):
        return None


def ai_group_instruction(group: dict[str, Any], fields: dict[str, str]) -> str:
    fallback = f"{group['title']}를 한 번에 입력해주세요."
    if not OPENAI_API_KEY:
        return fallback
    keys = ", ".join(field["label"] for field in group["fields"])
    prompt = (
        f"[현재 그룹]\n{group['title']}\n"
        f"[필수 항목]\n{keys}\n"
        f"[이미 입력된 키]\n{', '.join(sorted(fields.keys()))}\n\n"
        "요구사항: 사용자가 한 번에 입력할 수 있게 1~2문장으로 안내."
    )
    text = call_openai_text(OPENAI_SYSTEM_INTERVIEW, prompt)
    if not text:
        return fallback
    return text.splitlines()[0].strip()


def ai_followup_questions(
    group: dict[str, Any],
    missing_fields: list[dict[str, str]],
    current_fields: dict[str, str],
    history: list[dict[str, Any]],
) -> list[str]:
    # 기본 폴백 질문
    fallback = [f"{f['label']} 정보를 추가로 입력해주세요." for f in missing_fields]
    if not OPENAI_API_KEY or not missing_fields:
        return fallback

    compact_history = history[-4:]
    payload = {
        "group_title": group.get("title", ""),
        "missing_fields": missing_fields,
        "current_fields": current_fields,
        "recent_history": compact_history,
    }
    prompt = (
        "아래 정보로 후속질문 목록을 JSON 배열로 작성하세요.\n"
        "규칙:\n"
        "- 각 질문은 1문장\n"
        "- 사건 이해를 위해 꼭 필요한 것만\n"
        "- 질문 앞에 번호/기호 금지\n"
        "- JSON 배열 외 텍스트 금지\n\n"
        + json.dumps(payload, ensure_ascii=False)
    )
    text = call_openai_text(OPENAI_SYSTEM_FOLLOWUP, prompt)
    if not text:
        return fallback
    try:
        start = text.find("[")
        end = text.rfind("]")
        if start < 0 or end <= start:
            return fallback
        rows = json.loads(text[start : end + 1])
        questions = [str(x).strip() for x in rows if str(x).strip()]
        return questions if questions else fallback
    except json.JSONDecodeError:
        return fallback


def summarize_text(text: str, limit: int = 2) -> str:
    parts = re.split(r"[.\n]", text)
    rows = [p.strip() for p in parts if p.strip()]
    if not rows:
        return "추가 확인 필요"
    return " / ".join(rows[:limit])


def mask_rrn(value: str) -> str:
    digits = value.replace("-", "")
    if len(digits) != 13:
        return value or "추가 확인 필요"
    return f"{digits[:6]}-{digits[6]}******"


def bullets(lines: list[str] | str) -> str:
    if isinstance(lines, str):
        arr = [x.strip() for x in lines.splitlines() if x.strip()]
    else:
        arr = [str(x).strip() for x in lines if str(x).strip()]
    if not arr:
        return "- 추가 확인 필요"
    return "\n".join(f"- {x}" for x in arr)


def value_or_missing(data: dict[str, str], key: str) -> str:
    value = data.get(key, "").strip()
    return value if value else "추가 확인 필요"


def relevance_score(sentence: str) -> int:
    score = 0
    for kw in ("임금", "체불", "퇴직금", "해고", "근로시간", "수당", "증거", "진술", "계약"):
        if kw in sentence:
            score += 2
    if DATE_PATTERN.search(sentence):
        score += 1
    if MONEY_PATTERN.search(sentence):
        score += 1
    return score


def curate_facts(history: list[dict[str, Any]], limit: int = 8) -> list[str]:
    pool: list[str] = []
    for item in history:
        answers = item.get("answers", {})
        for value in answers.values():
            text = str(value).strip()
            if not text:
                continue
            for sentence in re.split(r"[.\n]", text):
                s = sentence.strip()
                if len(s) >= 8:
                    pool.append(s)
    ranked = sorted(pool, key=relevance_score, reverse=True)
    out: list[str] = []
    seen: set[str] = set()
    for row in ranked:
        if row in seen:
            continue
        seen.add(row)
        out.append(row)
        if len(out) >= limit:
            break
    return out


def ai_generate_references(fields: dict[str, str], facts: list[str]) -> list[str]:
    case_type = fields.get("case_type", "기타")
    if OPENAI_API_KEY:
        payload = {
            "case_type": case_type,
            "facts": facts[:10],
            "claims": {
                "claimant": fields.get("claimant_claim", ""),
                "respondent": fields.get("respondent_claim", ""),
            },
        }
        prompt = (
            "아래 사건정보에 대해 관련 법령/판례/질의회시를 각각 최소 1개 이상 추천하세요.\n"
            "출력 형식: JSON 배열 문자열. 각 항목은 '구분|제목|식별정보|요지' 형식의 텍스트.\n"
            "정확한 문서번호를 확신 못하면 '확인 필요'를 명시.\n\n"
            + json.dumps(payload, ensure_ascii=False)
        )
        text = call_openai_text(OPENAI_SYSTEM_REF, prompt)
        if text:
            try:
                start = text.find("[")
                end = text.rfind("]")
                if start >= 0 and end > start:
                    arr = json.loads(text[start : end + 1])
                    rows = [str(x).strip() for x in arr if str(x).strip()]
                    if rows:
                        return rows
            except json.JSONDecodeError:
                pass

    # 폴백 규칙 추천
    refs = []
    if case_type == "임금체불":
        refs += [
            "법령 | 근로기준법 제43조(임금 지급) | 법령 원문 확인 필요 | 임금 전액·정기 지급 원칙",
            "판례 | 대법원 2023.6.15. 선고 2020도16228 | 사건번호 확인 필요 | 임금 미지급 관련 책임 판단",
            "질의회시 | 고용노동부 임금체불 관련 질의회시 | 문서번호 확인 필요 | 체불 임금 지급의무 해석",
        ]
    elif case_type == "해고/징계":
        refs += [
            "법령 | 근로기준법 제26조(해고의 예고) | 법령 원문 확인 필요 | 해고예고/수당 규정",
            "판례 | 부당해고 관련 대법원 판례 | 사건번호 확인 필요 | 해고 사유 및 절차 적법성 판단",
            "질의회시 | 고용노동부 해고예고 질의회시 | 문서번호 확인 필요 | 예고수당 지급 기준",
        ]
    elif case_type == "근로시간/수당":
        refs += [
            "법령 | 근로기준법 제56조(연장·야간·휴일 근로) | 법령 원문 확인 필요 | 가산수당 지급 기준",
            "판례 | 대법원 2024.6.27. 선고 2020도16541 | 사건번호 확인 필요 | 근로시간 및 수당 입증 판단",
            "질의회시 | 고용노동부 연장근로수당 질의회시 | 문서번호 확인 필요 | 수당 산정 해석",
        ]
    elif case_type == "퇴직금":
        refs += [
            "법령 | 근로자퇴직급여 보장법 제8조 | 법령 원문 확인 필요 | 퇴직금 지급 요건",
            "판례 | 퇴직금 산정 관련 대법원 판례 | 사건번호 확인 필요 | 평균임금/계속근로기간 판단",
            "질의회시 | 고용노동부 퇴직금 질의회시 | 문서번호 확인 필요 | 지급기한 및 산정 해석",
        ]
    else:
        refs += [
            "법령 | 근로기준법 관련 조문 | 조문 확인 필요 | 사건 쟁점별 적용 조문 검토",
            "판례 | 유사 쟁점 대법원 판례 | 사건번호 확인 필요 | 사실관계 유사성 검토 필요",
            "질의회시 | 고용노동부 질의회시 | 문서번호 확인 필요 | 행정해석 대조 필요",
        ]
    return refs


def validate_group_answers(group: dict[str, Any], answers: dict[str, str]) -> list[str]:
    errors: list[str] = []
    for field in group["fields"]:
        key = field["key"]
        value = str(answers.get(key, "")).strip()
        if not value:
            continue
        if key in ("complainant_rrn", "respondent_rrn") and not RRN_PATTERN.match(value):
            errors.append(f"{field['label']} 형식이 올바르지 않습니다. (######-#######)")
        if key in ("complainant_phone", "respondent_phone") and not PHONE_PATTERN.match(value):
            errors.append(f"{field['label']} 형식이 올바르지 않습니다. (예: 010-1234-5678)")
        if key == "workplace_workers" and not value.replace(",", "").isdigit():
            errors.append("상시근로자 수는 숫자로 입력해주세요.")
        if key == "case_type":
            answers[key] = normalize_case_type(value)
        if key == "result" and value not in OUTCOMES:
            errors.append("결과는 기소송치/법위반없음/시정지시/계속내사 중 하나로 입력해주세요.")
    return errors


def build_group_flow(case_type: str) -> list[dict[str, Any]]:
    normalized = normalize_case_type(case_type)
    flow = list(GROUPS_COMMON)
    flow.append(GROUPS_CASE_EXTRA.get(normalized, GROUPS_CASE_EXTRA["기타"]))
    flow.append(GROUP_RESULT)
    return flow


def generate_markdown(fields: dict[str, str], history: list[dict[str, Any]]) -> str:
    case_type = fields.get("case_type", "기타")
    facts = curate_facts(history)
    references = ai_generate_references(fields, facts)

    case_extra_lines = [f"### 2.5 사건유형 추가사항 ({case_type})"]
    for f in GROUPS_CASE_EXTRA.get(case_type, GROUPS_CASE_EXTRA["기타"])["fields"]:
        case_extra_lines.append(f"- {f['key']}: {value_or_missing(fields, f['key'])}")

    lines = [
        "# 내사 보고서",
        "",
        "## 1. 기본정보",
        f"- 사건유형: {value_or_missing(fields, 'case_type')}",
        f"- 내사 검토 기간: {value_or_missing(fields, 'investigation_period')}",
        "- 진정인정보:",
        f"  - 이름: {value_or_missing(fields, 'complainant_name')}",
        f"  - 주민번호: {mask_rrn(fields.get('complainant_rrn', ''))}",
        f"  - 주소: {value_or_missing(fields, 'complainant_address')}",
        f"  - 전화번호: {value_or_missing(fields, 'complainant_phone')}",
        "- 피진정인정보:",
        f"  - 이름: {value_or_missing(fields, 'respondent_name')}",
        f"  - 주민번호: {mask_rrn(fields.get('respondent_rrn', ''))}",
        f"  - 주소: {value_or_missing(fields, 'respondent_address')}",
        f"  - 전화번호: {value_or_missing(fields, 'respondent_phone')}",
        "- 사업장정보:",
        f"  - 명칭: {value_or_missing(fields, 'workplace_name')}",
        f"  - 주소: {value_or_missing(fields, 'workplace_address')}",
        f"  - 업종: {value_or_missing(fields, 'workplace_industry')}",
        f"  - 상시근로자수: {value_or_missing(fields, 'workplace_workers')}",
        "",
        "## 2. 내사검토",
        "### 2.1 인정되는 사실(AI 선별)",
        bullets(facts),
        "",
        "### 2.2 진정인 주장",
        f"- {summarize_text(fields.get('claimant_claim', ''))}",
        "",
        "### 2.3 피진정인 주장",
        f"- {summarize_text(fields.get('respondent_claim', ''))}",
        "",
        "### 2.4 증거자료",
        bullets(fields.get("evidence_summary", "")),
        "",
        *case_extra_lines,
        "",
        "## 3. 내사결과",
        "### 3.1 근로감독관 판단(AI 초안)",
        "- 진정인·피진정인 주장과 증거를 교차 검토한 결과를 기준으로 판단함.",
        "- 상충 진술은 객관증거(근태기록/급여대장/계약서) 우선으로 재검증 필요.",
        "- 법령·판례·질의회시의 사실관계 유사성 확인 후 최종 결재 필요.",
        "",
        "### 3.2 근거 인용(프로그램 AI 자동탐색)",
        bullets(references),
        "",
        "### 3.3 결과",
        f"- {value_or_missing(fields, 'result')}",
        "",
        "## 4. 검증메모",
        "- 본 문서의 법령/판례/질의회시는 AI 자동탐색 결과이며, 문서번호/선고일 최종 대조 필요.",
        "- 누락 또는 불명확 정보는 '추가 확인 필요'로 보완할 것.",
    ]
    return "\n".join(lines).strip() + "\n"


class AppState:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.sessions: dict[str, dict[str, Any]] = {}

    def create_session(self) -> dict[str, Any]:
        session_id = str(uuid.uuid4())
        case_type = "임금체불"
        groups = build_group_flow(case_type)
        session = {
            "id": session_id,
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "fields": {"case_type": case_type, "result": "계속내사"},
            "history": [],
            "groups": groups,
            "group_index": 0,
            "ai_enabled": bool(OPENAI_API_KEY),
        }
        self.sessions[session_id] = session
        return session

    def get(self, session_id: str) -> dict[str, Any] | None:
        return self.sessions.get(session_id)


APP_STATE = AppState()


class ReportHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args: Any, directory: str | None = None, **kwargs: Any) -> None:
        super().__init__(*args, directory=directory, **kwargs)

    def _json(self, payload: dict[str, Any], status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length) if length > 0 else b"{}"
        try:
            payload = json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError:
            self._json({"ok": False, "error": "invalid_json"}, 400)
            return

        if self.path == "/api/session":
            self._create_session()
            return
        if self.path == "/api/group_submit":
            self._group_submit(payload)
            return
        if self.path == "/api/report":
            self._report(payload)
            return
        self._json({"ok": False, "error": "not_found"}, 404)

    @staticmethod
    def _group_values(group: dict[str, Any], fields: dict[str, str]) -> dict[str, str]:
        values: dict[str, str] = {}
        for f in group["fields"]:
            key = f["key"]
            if key in fields:
                values[key] = str(fields.get(key, ""))
        return values

    def _current_group_payload(self, session: dict[str, Any]) -> dict[str, Any]:
        idx = session["group_index"]
        groups = session["groups"]
        if idx >= len(groups):
            return {"done": True, "group": None, "progress": f"{len(groups)}/{len(groups)}"}
        group = groups[idx]
        instruction = ai_group_instruction(group, session["fields"])
        return {
            "done": False,
            "group": group,
            "instruction": instruction,
            "progress": f"{idx}/{len(groups)}",
            "current_values": self._group_values(group, session["fields"]),
        }

    def _create_session(self) -> None:
        with APP_STATE.lock:
            session = APP_STATE.create_session()
            payload = self._current_group_payload(session)
            payload.update(
                {
                    "ok": True,
                    "session_id": session["id"],
                    "ai_enabled": session["ai_enabled"],
                    "model": OPENAI_MODEL if session["ai_enabled"] else None,
                }
            )
        self._json(payload)

    def _group_submit(self, payload: dict[str, Any]) -> None:
        session_id = str(payload.get("session_id", "")).strip()
        answers = payload.get("answers", {})
        if not session_id or not isinstance(answers, dict):
            self._json({"ok": False, "error": "missing_session_or_answers"}, 400)
            return

        with APP_STATE.lock:
            session = APP_STATE.get(session_id)
            if not session:
                self._json({"ok": False, "error": "session_not_found"}, 404)
                return

            idx = session["group_index"]
            if idx >= len(session["groups"]):
                self._json({"ok": True, "done": True, "progress": f"{len(session['groups'])}/{len(session['groups'])}"})
                return

            group = session["groups"][idx]
            normalized_answers = {k: str(v).strip() for k, v in answers.items()}
            errors = validate_group_answers(group, normalized_answers)
            if errors:
                self._json(
                    {
                        "ok": True,
                        "done": False,
                        "errors": errors,
                        "group": group,
                        "progress": f"{idx}/{len(session['groups'])}",
                    }
                )
                return

            # 저장
            non_empty = {k: v for k, v in normalized_answers.items() if str(v).strip()}
            session["fields"].update(non_empty)
            if "case_type" in normalized_answers:
                case_type = normalize_case_type(normalized_answers["case_type"])
                session["fields"]["case_type"] = case_type
                session["groups"] = build_group_flow(case_type)
                # 현재 그룹은 case_basic이므로 인덱스 유지
            session["history"].append({"group_id": group["id"], "title": group["title"], "answers": non_empty})

            # 그룹 필수값이 아직 부족하면 같은 그룹에서 후속 질문
            missing_fields = []
            for f in group["fields"]:
                key = f["key"]
                if not str(session["fields"].get(key, "")).strip():
                    missing_fields.append(f)

            if missing_fields:
                followups = ai_followup_questions(
                    group=group,
                    missing_fields=missing_fields,
                    current_fields=session["fields"],
                    history=session["history"],
                )
                facts = curate_facts(session["history"], limit=5)
                self._json(
                    {
                        "ok": True,
                        "done": False,
                        "need_more_info": True,
                        "followup_questions": followups,
                        "missing_keys": [f["key"] for f in missing_fields],
                        "group": group,
                        "current_values": self._group_values(group, session["fields"]),
                        "instruction": "입력된 내용이 일부 부족합니다. 아래 후속질문을 참고해 같은 그룹을 보완해주세요.",
                        "progress": f"{idx}/{len(session['groups'])}",
                        "curated_facts": facts,
                        "errors": [],
                        "ai_enabled": session["ai_enabled"],
                        "model": OPENAI_MODEL if session["ai_enabled"] else None,
                    }
                )
                return

            session["group_index"] += 1

            facts = curate_facts(session["history"], limit=5)
            payload_out = self._current_group_payload(session)
            payload_out.update(
                {
                    "ok": True,
                    "errors": [],
                    "need_more_info": False,
                    "followup_questions": [],
                    "missing_keys": [],
                    "curated_facts": facts,
                    "filled_keys": list(session["fields"].keys()),
                    "ai_enabled": session["ai_enabled"],
                    "model": OPENAI_MODEL if session["ai_enabled"] else None,
                }
            )
        self._json(payload_out)

    def _report(self, payload: dict[str, Any]) -> None:
        session_id = str(payload.get("session_id", "")).strip()
        if not session_id:
            self._json({"ok": False, "error": "missing_session_id"}, 400)
            return

        with APP_STATE.lock:
            session = APP_STATE.get(session_id)
            if not session:
                self._json({"ok": False, "error": "session_not_found"}, 404)
                return

            markdown = generate_markdown(session["fields"], session["history"])
            missing = []
            for g in session["groups"]:
                for f in g["fields"]:
                    if not str(session["fields"].get(f["key"], "")).strip():
                        missing.append(f["key"])
        self._json({"ok": True, "markdown": markdown, "missing": missing})


def main() -> None:
    args = parse_args()
    root = Path(__file__).resolve().parent
    url = f"http://{args.host}:{args.port}/web/index.html"
    handler = lambda *a, **kw: ReportHandler(*a, directory=str(root), **kw)
    server = ThreadingHTTPServer((args.host, args.port), handler)

    print(f"[INFO] Serving: {root}")
    print(f"[INFO] Open: {url}")
    if not args.no_browser:
        webbrowser.open(url)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[INFO] 서버를 종료합니다.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
