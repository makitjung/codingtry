#!/usr/bin/env python
# -*- coding: utf-8 -*-

from __future__ import annotations

import json
import os
import re
import threading
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib import error as urlerror
from urllib import request as urlrequest

from flask import Flask, Response, jsonify, request, send_file


app = Flask(__name__)

CASE_TYPES = ["임금체불", "해고/징계", "근로시간/수당", "퇴직금", "기타"]
OUTCOMES = ["기소송치", "법위반없음", "시정지시", "계속내사"]
RRN_PATTERN = re.compile(r"^\d{6}-?\d{7}$")
PHONE_PATTERN = re.compile(r"^\d{2,3}-?\d{3,4}-?\d{4}$")
DATE_PATTERN = re.compile(r"\d{4}[-./]\d{1,2}[-./]\d{1,2}")
MONEY_PATTERN = re.compile(r"\d[\d,]*\s*원")

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-5-mini").strip()
OPENAI_TIMEOUT_SECONDS = int(os.getenv("OPENAI_TIMEOUT_SECONDS", "25"))


ROOT_DIR = Path(__file__).resolve().parent.parent
WEB_INDEX = ROOT_DIR / "web" / "index.html"


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
        "fields": [{"key": "case_specific_note", "label": "특이사항", "placeholder": "사건 특이사항"}],
    },
}

GROUP_RESULT = {
    "id": "result",
    "title": "잠정 결과",
    "fields": [{"key": "result", "label": "결과", "placeholder": "기소송치 / 법위반없음 / 시정지시 / 계속내사"}],
}


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


STATE = AppState()


def normalize_case_type(text: str) -> str:
    t = str(text).strip()
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


def build_group_flow(case_type: str) -> list[dict[str, Any]]:
    flow = list(GROUPS_COMMON)
    flow.append(GROUPS_CASE_EXTRA.get(normalize_case_type(case_type), GROUPS_CASE_EXTRA["기타"]))
    flow.append(GROUP_RESULT)
    return flow


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
        headers={"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type": "application/json"},
    )
    try:
        with urlrequest.urlopen(req, timeout=OPENAI_TIMEOUT_SECONDS) as res:
            body = res.read().decode("utf-8")
        return _extract_response_text(json.loads(body)) or None
    except (urlerror.URLError, TimeoutError, json.JSONDecodeError, OSError):
        return None


def ai_group_instruction(group: dict[str, Any], fields: dict[str, str]) -> str:
    fallback = f"{group['title']}를 한 번에 입력해주세요."
    text = call_openai_text(
        "당신은 한국 노동사건 인터뷰 보조 AI입니다. 한 번에 입력할 묶음 질문을 1문장으로 만드세요.",
        json.dumps({"group": group, "filled": list(fields.keys())}, ensure_ascii=False),
    )
    return text.splitlines()[0].strip() if text else fallback


def ai_followup_questions(group: dict[str, Any], missing_fields: list[dict[str, str]], current_fields: dict[str, str]) -> list[str]:
    fallback = [f"{f['label']} 정보를 추가로 입력해주세요." for f in missing_fields]
    text = call_openai_text(
        "사건 이해에 필요한 후속질문만 JSON 배열로 작성하세요.",
        json.dumps({"group": group, "missing_fields": missing_fields, "current_fields": current_fields}, ensure_ascii=False),
    )
    if not text:
        return fallback
    try:
        s, e = text.find("["), text.rfind("]")
        arr = json.loads(text[s : e + 1]) if s >= 0 and e > s else []
        rows = [str(x).strip() for x in arr if str(x).strip()]
        return rows if rows else fallback
    except json.JSONDecodeError:
        return fallback


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
        if key == "result" and value not in OUTCOMES:
            errors.append("결과는 기소송치/법위반없음/시정지시/계속내사 중 하나로 입력해주세요.")
    return errors


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
        for value in item.get("answers", {}).values():
            for sentence in re.split(r"[.\n]", str(value)):
                s = sentence.strip()
                if len(s) >= 8:
                    pool.append(s)
    ranked = sorted(pool, key=relevance_score, reverse=True)
    out, seen = [], set()
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
    text = call_openai_text(
        "관련 법령/판례/질의회시를 JSON 배열로 추천하세요.",
        json.dumps({"case_type": case_type, "facts": facts[:8], "fields": fields}, ensure_ascii=False),
    )
    if text:
        try:
            s, e = text.find("["), text.rfind("]")
            arr = json.loads(text[s : e + 1]) if s >= 0 and e > s else []
            rows = [str(x).strip() for x in arr if str(x).strip()]
            if rows:
                return rows
        except json.JSONDecodeError:
            pass
    return [
        "법령 | 근로기준법 관련 조문 | 조문 확인 필요 | 사건 쟁점별 적용 조문 검토",
        "판례 | 유사 쟁점 대법원 판례 | 사건번호 확인 필요 | 사실관계 유사성 검토",
        "질의회시 | 고용노동부 질의회시 | 문서번호 확인 필요 | 행정해석 대조 필요",
    ]


def summarize_text(text: str, limit: int = 2) -> str:
    rows = [p.strip() for p in re.split(r"[.\n]", text or "") if p.strip()]
    return " / ".join(rows[:limit]) if rows else "추가 확인 필요"


def mask_rrn(value: str) -> str:
    digits = str(value).replace("-", "")
    if len(digits) != 13:
        return value or "추가 확인 필요"
    return f"{digits[:6]}-{digits[6]}******"


def bullets(lines: list[str] | str) -> str:
    if isinstance(lines, str):
        arr = [x.strip() for x in lines.splitlines() if x.strip()]
    else:
        arr = [str(x).strip() for x in lines if str(x).strip()]
    return "\n".join(f"- {x}" for x in arr) if arr else "- 추가 확인 필요"


def value_or_missing(fields: dict[str, str], key: str) -> str:
    value = str(fields.get(key, "")).strip()
    return value if value else "추가 확인 필요"


def generate_markdown(fields: dict[str, str], history: list[dict[str, Any]]) -> str:
    case_type = fields.get("case_type", "기타")
    facts = curate_facts(history)
    refs = ai_generate_references(fields, facts)
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
        "- 상충 진술은 객관증거 우선으로 재검증 필요.",
        "- 법령·판례·질의회시 사실관계 유사성 확인 후 최종 결재 필요.",
        "",
        "### 3.2 근거 인용(프로그램 AI 자동탐색)",
        bullets(refs),
        "",
        "### 3.3 결과",
        f"- {value_or_missing(fields, 'result')}",
        "",
        "## 4. 검증메모",
        "- AI 자동탐색 결과는 원문 대조 후 확정 필요.",
    ]
    return "\n".join(lines).strip() + "\n"


def current_group_payload(session: dict[str, Any]) -> dict[str, Any]:
    idx = session["group_index"]
    groups = session["groups"]
    if idx >= len(groups):
        return {"done": True, "group": None, "progress": f"{len(groups)}/{len(groups)}"}
    group = groups[idx]
    current_values = {f["key"]: session["fields"].get(f["key"], "") for f in group["fields"]}
    return {
        "done": False,
        "group": group,
        "instruction": ai_group_instruction(group, session["fields"]),
        "progress": f"{idx}/{len(groups)}",
        "current_values": current_values,
    }


@app.get("/")
def root() -> Response:
    return send_file(WEB_INDEX)


@app.get("/web/index.html")
def web_index() -> Response:
    return send_file(WEB_INDEX)


@app.post("/api/session")
def api_session() -> Response:
    with STATE.lock:
        session = STATE.create_session()
        payload = current_group_payload(session)
        payload.update({"ok": True, "session_id": session["id"], "ai_enabled": session["ai_enabled"], "model": OPENAI_MODEL if session["ai_enabled"] else None})
    return jsonify(payload)


@app.post("/api/group_submit")
def api_group_submit() -> Response:
    data = request.get_json(silent=True) or {}
    session_id = str(data.get("session_id", "")).strip()
    answers = data.get("answers", {})
    if not session_id or not isinstance(answers, dict):
        return jsonify({"ok": False, "error": "missing_session_or_answers"}), 400

    with STATE.lock:
        session = STATE.get(session_id)
        if not session:
            return jsonify({"ok": False, "error": "session_not_found"}), 404
        idx = session["group_index"]
        if idx >= len(session["groups"]):
            return jsonify({"ok": True, "done": True, "progress": f"{len(session['groups'])}/{len(session['groups'])}"})

        group = session["groups"][idx]
        normalized_answers = {k: str(v).strip() for k, v in answers.items()}
        errors = validate_group_answers(group, normalized_answers)
        if errors:
            return jsonify({"ok": True, "done": False, "errors": errors, "group": group, "progress": f"{idx}/{len(session['groups'])}"})

        non_empty = {k: v for k, v in normalized_answers.items() if str(v).strip()}
        session["fields"].update(non_empty)
        if "case_type" in normalized_answers:
            ct = normalize_case_type(normalized_answers["case_type"])
            session["fields"]["case_type"] = ct
            session["groups"] = build_group_flow(ct)
        session["history"].append({"group_id": group["id"], "title": group["title"], "answers": non_empty})

        missing_fields = [f for f in group["fields"] if not str(session["fields"].get(f["key"], "")).strip()]
        if missing_fields:
            followups = ai_followup_questions(group, missing_fields, session["fields"])
            facts = curate_facts(session["history"], 5)
            current_values = {f["key"]: session["fields"].get(f["key"], "") for f in group["fields"]}
            return jsonify(
                {
                    "ok": True,
                    "done": False,
                    "need_more_info": True,
                    "followup_questions": followups,
                    "missing_keys": [f["key"] for f in missing_fields],
                    "group": group,
                    "current_values": current_values,
                    "instruction": "입력된 내용이 일부 부족합니다. 아래 후속질문을 참고해 같은 그룹을 보완해주세요.",
                    "progress": f"{idx}/{len(session['groups'])}",
                    "curated_facts": facts,
                    "errors": [],
                    "ai_enabled": session["ai_enabled"],
                    "model": OPENAI_MODEL if session["ai_enabled"] else None,
                }
            )

        session["group_index"] += 1
        facts = curate_facts(session["history"], 5)
        payload = current_group_payload(session)
        payload.update(
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
        return jsonify(payload)


@app.post("/api/report")
def api_report() -> Response:
    data = request.get_json(silent=True) or {}
    session_id = str(data.get("session_id", "")).strip()
    if not session_id:
        return jsonify({"ok": False, "error": "missing_session_id"}), 400

    with STATE.lock:
        session = STATE.get(session_id)
        if not session:
            return jsonify({"ok": False, "error": "session_not_found"}), 404
        markdown = generate_markdown(session["fields"], session["history"])
        missing = []
        for g in session["groups"]:
            for f in g["fields"]:
                if not str(session["fields"].get(f["key"], "")).strip():
                    missing.append(f["key"])
    return jsonify({"ok": True, "markdown": markdown, "missing": missing})

