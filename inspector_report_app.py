#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""질문-응답형 내사보고서 자동작성기.

핵심 설계:
- 프로그램이 순차 질문을 던지고 사용자가 답변
- 필수 항목 누락 시 팝업으로 보완 입력
- 보고서는 한글(HWP) 양식에 맞춘 Markdown으로 생성
- 판단 문장은 사용자 입력 사실/근거만 사용하도록 제한
"""

from __future__ import annotations

import json
import os
import re
import tkinter as tk
from dataclasses import dataclass
from tkinter import filedialog, messagebox, simpledialog, ttk


RRN_PATTERN = re.compile(r"^\d{6}-?\d{7}$")
PHONE_PATTERN = re.compile(r"^\d{2,3}-?\d{3,4}-?\d{4}$")


@dataclass
class Question:
    key: str
    text: str
    required: bool = True
    multiline: bool = False
    group: str = "기본"


COMMON_QUESTIONS = [
    Question("case_id", "사건번호를 입력해주세요. (예: 2026-서울-내사-001)", group="사건"),
    Question("investigation_period", "내사 검토 기간을 입력해주세요. (예: 2026-04-01 ~ 2026-04-09)", group="사건"),
    Question("complainant_name", "진정인의 성명을 입력해주세요.", group="진정인"),
    Question("complainant_rrn", "진정인의 주민등록번호를 입력해주세요. (######-#######)", group="진정인"),
    Question("complainant_address", "진정인의 주소를 입력해주세요.", group="진정인"),
    Question("complainant_phone", "진정인의 전화번호를 입력해주세요.", group="진정인"),
    Question("respondent_name", "피진정인의 성명을 입력해주세요.", group="피진정인"),
    Question("respondent_rrn", "피진정인의 주민등록번호를 입력해주세요. (######-#######)", group="피진정인"),
    Question("respondent_address", "피진정인의 주소를 입력해주세요.", group="피진정인"),
    Question("respondent_phone", "피진정인의 전화번호를 입력해주세요.", group="피진정인"),
    Question("workplace_name", "사업장 명칭을 입력해주세요.", group="사업장"),
    Question("workplace_address", "사업장 주소를 입력해주세요.", group="사업장"),
    Question("workplace_industry", "사업장 업종을 입력해주세요.", group="사업장"),
    Question("workplace_workers", "사업장 상시근로자수를 입력해주세요.", group="사업장"),
    Question("recognized_facts", "인정되는 사실을 구체적으로 입력해주세요.", multiline=True, group="내사검토"),
    Question("claimant_claim", "진정인 주장을 입력해주세요.", multiline=True, group="내사검토"),
    Question("respondent_claim", "피진정인 주장을 입력해주세요.", multiline=True, group="내사검토"),
    Question("evidence_summary", "확보된 증거자료 목록/요지를 입력해주세요.", multiline=True, group="내사검토"),
    Question("inspector_judgment", "근로감독관 판단을 입력해주세요.", multiline=True, group="내사결과"),
    Question(
        "reference_text",
        "판례/질의회시/지침/법령 근거를 입력해주세요. (문서번호/일자/핵심요지)",
        multiline=True,
        group="내사결과",
    ),
    Question("result", "내사결과를 선택해주세요. (기소송치/법위반없음/시정지시/계속내사)", group="내사결과"),
]

CASE_QUESTIONS = {
    "임금체불": [
        Question("wage_unpaid_period", "체불 기간을 입력해주세요. (예: 2025-11 ~ 2026-01)", group="사건유형"),
        Question("wage_unpaid_amount", "체불 금액(추정)을 입력해주세요.", group="사건유형"),
        Question("wage_payday_rule", "정기 임금지급일을 입력해주세요.", group="사건유형"),
    ],
    "해고/징계": [
        Question("dismissal_date", "해고(또는 징계) 통보일을 입력해주세요.", group="사건유형"),
        Question("dismissal_reason", "사용자 측 해고/징계 사유를 입력해주세요.", multiline=True, group="사건유형"),
        Question("dismissal_notice", "해고예고(30일 또는 수당지급) 이행 여부를 입력해주세요.", group="사건유형"),
    ],
    "근로시간/수당": [
        Question("weekly_hours", "주당 실제 근로시간을 입력해주세요.", group="사건유형"),
        Question("overtime_hours", "연장/야간/휴일 근로시간을 입력해주세요.", group="사건유형"),
        Question("overtime_paid", "연장/야간/휴일수당 지급 여부를 입력해주세요.", group="사건유형"),
    ],
    "퇴직금": [
        Question("employment_start", "입사일을 입력해주세요. (YYYY-MM-DD)", group="사건유형"),
        Question("employment_end", "퇴사일을 입력해주세요. (YYYY-MM-DD)", group="사건유형"),
        Question("retirement_amount", "퇴직금 지급액(또는 미지급액)을 입력해주세요.", group="사건유형"),
    ],
    "기타": [
        Question("case_specific_note", "사건 특이사항을 입력해주세요.", multiline=True, group="사건유형"),
    ],
}

OUTCOME_CHOICES = ["기소송치", "법위반없음", "시정지시", "계속내사"]

REFERENCE_DATA_FILE = "근거자료_레퍼런스.json"
DEFAULT_REFERENCE_CATALOG = [
    {
        "id": "law-lsa-43",
        "title": "근로기준법 제43조(임금 지급)",
        "type": "법령",
        "case_types": ["임금체불", "근로시간/수당"],
        "keywords": ["임금", "체불", "지급일", "미지급", "월급"],
        "summary": "임금은 통화로 직접, 전액, 매월 1회 이상 일정한 날짜에 지급해야 함.",
        "source_hint": "국가법령정보센터",
    },
    {
        "id": "law-lsa-56",
        "title": "근로기준법 제56조(연장·야간·휴일 근로)",
        "type": "법령",
        "case_types": ["근로시간/수당"],
        "keywords": ["연장", "야간", "휴일", "가산", "수당"],
        "summary": "연장·야간·휴일근로에 대한 가산수당 지급 기준을 규정.",
        "source_hint": "국가법령정보센터",
    },
    {
        "id": "law-lsa-26",
        "title": "근로기준법 제26조(해고의 예고)",
        "type": "법령",
        "case_types": ["해고/징계"],
        "keywords": ["해고", "예고", "30일", "해고예고수당", "징계"],
        "summary": "해고 시 30일 전 예고 또는 통상임금 30일분 지급 원칙.",
        "source_hint": "국가법령정보센터",
    },
    {
        "id": "law-lsa-36",
        "title": "근로기준법 제36조(금품청산)",
        "type": "법령",
        "case_types": ["퇴직금", "임금체불"],
        "keywords": ["퇴직", "금품청산", "14일", "미지급"],
        "summary": "퇴직 시 지급사유 발생 금품의 청산 기한 규정.",
        "source_hint": "국가법령정보센터",
    },
    {
        "id": "law-rba-8",
        "title": "근로자퇴직급여 보장법 제8조(퇴직금제도)",
        "type": "법령",
        "case_types": ["퇴직금"],
        "keywords": ["퇴직금", "1년", "30일분", "평균임금"],
        "summary": "퇴직금 산정의 기본원칙 및 지급 요건.",
        "source_hint": "국가법령정보센터",
    },
    {
        "id": "prec-2020do16228",
        "title": "대법원 2023.6.15. 선고 2020도16228",
        "type": "판례",
        "case_types": ["임금체불", "근로시간/수당"],
        "keywords": ["임금", "체불", "사용자", "지급의무"],
        "summary": "임금 미지급 관련 사용자 책임 판단에서 사실관계 입증이 핵심.",
        "source_hint": "대법원/국가법령정보센터 판례",
    },
    {
        "id": "prec-2020do16541",
        "title": "대법원 2024.6.27. 선고 2020도16541",
        "type": "판례",
        "case_types": ["근로시간/수당", "임금체불"],
        "keywords": ["근로시간", "가산수당", "입증", "근태기록"],
        "summary": "근로시간 및 수당 다툼에서 객관적 기록과 진술 정합성 판단 중요.",
        "source_hint": "대법원/국가법령정보센터 판례",
    },
    {
        "id": "moel-guideline-labor-inspector",
        "title": "근로감독관 집무규정",
        "type": "지침",
        "case_types": ["임금체불", "해고/징계", "근로시간/수당", "퇴직금", "기타"],
        "keywords": ["내사", "조사", "사실확인", "진술", "증거"],
        "summary": "근로감독 사건 처리 절차 및 보고서 작성 실무 기준.",
        "source_hint": "고용노동부 훈령",
    },
    {
        "id": "moel-qna-template",
        "title": "고용노동부 질의회시(해당 쟁점 검색 필요)",
        "type": "질의회시",
        "case_types": ["임금체불", "해고/징계", "근로시간/수당", "퇴직금", "기타"],
        "keywords": ["질의회시", "행정해석", "근로기준정책"],
        "summary": "사실관계와 쟁점에 맞는 문서번호/회시일자를 직접 대조해 인용.",
        "source_hint": "고용노동부 질의회시 공개시스템",
    },
]


class ReportApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("내사보고서 자동작성기")
        self.geometry("1080x760")
        self.minsize(980, 680)

        self.answers: dict[str, str] = {}
        self.questions: list[Question] = []
        self.current_index = 0
        self.recommended_items: list[dict[str, object]] = []
        self.reference_catalog = self._load_reference_catalog()

        self.case_type_var = tk.StringVar(value="임금체불")
        self.result_var = tk.StringVar(value=OUTCOME_CHOICES[0])
        self.use_masking_var = tk.BooleanVar(value=True)

        self._build_ui()
        self._refresh_questions()
        self._show_current_question()

    def _build_ui(self) -> None:
        top = ttk.Frame(self, padding=(12, 10))
        top.pack(fill="x")

        ttk.Label(top, text="사건유형").pack(side="left")
        case_combo = ttk.Combobox(
            top,
            textvariable=self.case_type_var,
            values=list(CASE_QUESTIONS.keys()),
            state="readonly",
            width=20,
        )
        case_combo.pack(side="left", padx=(8, 12))
        case_combo.bind("<<ComboboxSelected>>", lambda _: self._on_case_type_changed())

        ttk.Label(top, text="결과 기본값").pack(side="left")
        result_combo = ttk.Combobox(
            top,
            textvariable=self.result_var,
            values=OUTCOME_CHOICES,
            state="readonly",
            width=14,
        )
        result_combo.pack(side="left", padx=(8, 12))

        ttk.Checkbutton(top, text="출력 시 주민번호 마스킹", variable=self.use_masking_var).pack(side="left")

        container = ttk.Panedwindow(self, orient=tk.HORIZONTAL)
        container.pack(fill="both", expand=True, padx=12, pady=(0, 8))

        left = ttk.Frame(container, padding=10)
        right = ttk.Frame(container, padding=10)
        container.add(left, weight=2)
        container.add(right, weight=3)

        self.progress_label = ttk.Label(left, text="질문 0/0")
        self.progress_label.pack(anchor="w")

        self.group_label = ttk.Label(left, text="분류: -")
        self.group_label.pack(anchor="w", pady=(2, 8))

        self.question_text = tk.Text(left, height=4, wrap="word", state="disabled")
        self.question_text.pack(fill="x")

        ttk.Label(left, text="답변").pack(anchor="w", pady=(10, 4))
        self.answer_input = tk.Text(left, height=9, wrap="word")
        self.answer_input.pack(fill="both", expand=True)

        btn_row = ttk.Frame(left)
        btn_row.pack(fill="x", pady=(8, 0))
        ttk.Button(btn_row, text="저장 후 다음", command=self._save_and_next).pack(side="left")
        ttk.Button(btn_row, text="이전 질문", command=self._prev_question).pack(side="left", padx=6)
        ttk.Button(btn_row, text="질문 건너뛰기", command=self._skip_question).pack(side="left")

        ttk.Label(left, text="입력 로그").pack(anchor="w", pady=(10, 4))
        self.log_list = tk.Listbox(left, height=10)
        self.log_list.pack(fill="both", expand=True)

        ttk.Label(right, text="보고서 미리보기 (Markdown)").pack(anchor="w")
        self.preview = tk.Text(right, wrap="word")
        self.preview.pack(fill="both", expand=True, pady=(4, 8))

        right_btn = ttk.Frame(right)
        right_btn.pack(fill="x")
        ttk.Button(right_btn, text="미리보기 갱신", command=self._refresh_preview).pack(side="left")
        ttk.Button(right_btn, text="누락정보 확인 팝업", command=self._collect_missing_via_popup).pack(side="left", padx=6)
        ttk.Button(right_btn, text="근거 자동추천", command=self._recommend_references).pack(side="left", padx=6)
        ttk.Button(right_btn, text="Markdown 저장", command=self._save_markdown).pack(side="right")

        ttk.Label(right, text="자동추천 근거 목록 (검증 전)").pack(anchor="w", pady=(8, 4))
        self.recommend_list = tk.Listbox(right, height=8, selectmode=tk.MULTIPLE)
        self.recommend_list.pack(fill="x")
        ttk.Button(right, text="선택 근거를 인용란에 반영", command=self._apply_selected_references).pack(
            anchor="e", pady=(6, 0)
        )

    def _on_case_type_changed(self) -> None:
        # 사건유형 변경 시, 기존 답변은 보존하되 질문 목록만 다시 구성
        self._refresh_questions()
        if self.current_index >= len(self.questions):
            self.current_index = max(0, len(self.questions) - 1)
        self._show_current_question()

    def _refresh_questions(self) -> None:
        case_questions = CASE_QUESTIONS[self.case_type_var.get()]
        split_idx = next(
            (idx for idx, q in enumerate(COMMON_QUESTIONS) if q.key == "recognized_facts"),
            len(COMMON_QUESTIONS),
        )
        self.questions = COMMON_QUESTIONS[:split_idx] + case_questions + COMMON_QUESTIONS[split_idx:]

        # 결과 질문은 콤보 기본값을 반영
        if not self.answers.get("result"):
            self.answers["result"] = self.result_var.get()

    def _show_current_question(self) -> None:
        if not self.questions:
            return
        q = self.questions[self.current_index]
        self.progress_label.config(text=f"질문 {self.current_index + 1}/{len(self.questions)}")
        self.group_label.config(text=f"분류: {q.group}")
        self._set_text(self.question_text, q.text)

        current_answer = self.answers.get(q.key, "")
        self.answer_input.delete("1.0", tk.END)
        if q.key == "result" and not current_answer:
            current_answer = self.result_var.get()
        self.answer_input.insert("1.0", current_answer)

    def _save_and_next(self) -> None:
        q = self.questions[self.current_index]
        answer = self.answer_input.get("1.0", tk.END).strip()
        if q.required and not answer:
            messagebox.showwarning("입력 필요", "필수 질문입니다. 답변을 입력해주세요.")
            return
        if answer:
            self.answers[q.key] = answer
            self._append_log(q, answer)
        self._refresh_preview()
        if self.current_index < len(self.questions) - 1:
            self.current_index += 1
            self._show_current_question()
        else:
            messagebox.showinfo("안내", "마지막 질문입니다. 미리보기 또는 저장을 진행해주세요.")

    def _skip_question(self) -> None:
        if self.current_index < len(self.questions) - 1:
            self.current_index += 1
            self._show_current_question()
        else:
            messagebox.showinfo("안내", "이미 마지막 질문입니다.")

    def _prev_question(self) -> None:
        if self.current_index > 0:
            self.current_index -= 1
            self._show_current_question()

    def _append_log(self, q: Question, answer: str) -> None:
        short = answer.replace("\n", " ")
        if len(short) > 42:
            short = short[:42] + "..."
        self.log_list.insert(tk.END, f"[{q.group}] {q.text} -> {short}")
        self.log_list.yview_moveto(1.0)

    def _refresh_preview(self) -> None:
        markdown = self._build_markdown()
        self._set_text(self.preview, markdown)

    def _load_reference_catalog(self) -> list[dict[str, object]]:
        if os.path.exists(REFERENCE_DATA_FILE):
            try:
                with open(REFERENCE_DATA_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, list):
                    return data
            except (OSError, json.JSONDecodeError):
                pass
        return DEFAULT_REFERENCE_CATALOG

    def _recommend_references(self) -> None:
        context_chunks = [
            self.case_type_var.get(),
            self.answers.get("recognized_facts", ""),
            self.answers.get("claimant_claim", ""),
            self.answers.get("respondent_claim", ""),
            self.answers.get("evidence_summary", ""),
            self.answers.get("inspector_judgment", ""),
        ]
        context = " ".join(context_chunks).lower()
        case_type = self.case_type_var.get()

        scored: list[tuple[int, dict[str, str]]] = []
        for item in self.reference_catalog:
            score = self._score_reference(item, context, case_type)
            if score > 0:
                scored.append((score, item))

        scored.sort(key=lambda x: x[0], reverse=True)
        self.recommended_items = [item for _, item in scored[:8]]

        self.recommend_list.delete(0, tk.END)
        for idx, item in enumerate(self.recommended_items, start=1):
            line = f"{idx}. [{item.get('type', '근거')}] {item.get('title', '')} | {item.get('id', '')}"
            self.recommend_list.insert(tk.END, line)

        if not self.recommended_items:
            self.recommend_list.insert(
                tk.END,
                "추천 결과가 없습니다. 사실관계/주장/증거를 더 입력한 뒤 다시 시도하세요.",
            )
        else:
            messagebox.showinfo(
                "자동추천 완료",
                "추천 근거를 생성했습니다. 목록에서 선택 후 '선택 근거를 인용란에 반영'을 눌러주세요.",
            )

    @staticmethod
    def _score_reference(item: dict[str, object], context: str, case_type: str) -> int:
        score = 0
        if case_type in item.get("case_types", []):
            score += 3
        for kw in item.get("keywords", []):
            kw_text = str(kw).lower()
            if kw_text in context:
                score += 2
        return score

    def _apply_selected_references(self) -> None:
        selected_indices = self.recommend_list.curselection()
        if not selected_indices:
            messagebox.showwarning("선택 필요", "반영할 자동추천 근거를 선택해주세요.")
            return

        lines = []
        for idx in selected_indices:
            if idx >= len(self.recommended_items):
                continue
            item = self.recommended_items[idx]
            lines.append(
                f"[자동추천(검증전)] {item.get('type', '근거')} | {item.get('title', '')} | "
                f"식별자: {item.get('id', '')} | 요지: {item.get('summary', '')} | 출처: {item.get('source_hint', '')}"
            )

        if not lines:
            messagebox.showwarning("반영 실패", "선택 항목을 반영하지 못했습니다.")
            return

        existing = self.answers.get("reference_text", "").strip()
        merged = "\n".join(lines) if not existing else existing + "\n" + "\n".join(lines)
        self.answers["reference_text"] = merged
        self._append_log(
            Question("reference_text", "자동추천 근거 반영", required=False, multiline=True, group="내사결과"),
            f"{len(lines)}건 반영",
        )
        self._refresh_preview()
        messagebox.showinfo("반영 완료", f"{len(lines)}건의 추천 근거를 인용란에 반영했습니다.")

    def _collect_missing_via_popup(self) -> bool:
        missing = self._get_missing_required_keys()
        if not missing:
            messagebox.showinfo("확인 완료", "필수 항목이 모두 입력되어 있습니다.")
            return True

        key_to_question = {q.key: q for q in self.questions}
        for key in missing:
            q = key_to_question[key]
            prompt = f"{q.text}\n\n(누락 항목 자동 보완)"
            value = simpledialog.askstring("누락 항목 입력", prompt, parent=self)
            if value is None:
                messagebox.showwarning("중단", "누락 항목 입력이 중단되어 보고서 생성을 멈췄습니다.")
                return False
            value = value.strip()
            if not value and q.required:
                messagebox.showwarning("입력 필요", "값이 비어 있어 다음 항목으로 진행할 수 없습니다.")
                return False
            self.answers[key] = value

        self._refresh_preview()
        return True

    def _get_missing_required_keys(self) -> list[str]:
        missing: list[str] = []
        for q in self.questions:
            if q.required and not self.answers.get(q.key, "").strip():
                missing.append(q.key)
        return missing

    def _validate_for_export(self) -> bool:
        if not self._collect_missing_via_popup():
            return False

        rrn_keys = ["complainant_rrn", "respondent_rrn"]
        for k in rrn_keys:
            value = self.answers.get(k, "")
            if value and not RRN_PATTERN.match(value):
                messagebox.showwarning("형식 오류", f"{k} 값 형식이 올바르지 않습니다. (######-#######)")
                return False

        phone_keys = ["complainant_phone", "respondent_phone"]
        for k in phone_keys:
            value = self.answers.get(k, "")
            if value and not PHONE_PATTERN.match(value):
                messagebox.showwarning("형식 오류", f"{k} 값 형식이 올바르지 않습니다. (예: 010-1234-5678)")
                return False

        workers = self.answers.get("workplace_workers", "").replace(",", "").strip()
        if workers and not workers.isdigit():
            messagebox.showwarning("형식 오류", "상시근로자수는 숫자로 입력해주세요.")
            return False

        return True

    def _save_markdown(self) -> None:
        if not self._validate_for_export():
            return

        # 결과는 콤보값 우선 반영
        if not self.answers.get("result"):
            self.answers["result"] = self.result_var.get()

        markdown = self._build_markdown()
        path = filedialog.asksaveasfilename(
            title="내사보고서 Markdown 저장",
            defaultextension=".md",
            filetypes=[("Markdown", "*.md"), ("Text", "*.txt"), ("All Files", "*.*")],
        )
        if not path:
            return

        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(markdown)
            messagebox.showinfo("저장 완료", f"보고서를 저장했습니다.\n{path}")
        except OSError as exc:
            messagebox.showerror("저장 실패", f"파일 저장 중 오류가 발생했습니다.\n{exc}")

    def _build_markdown(self) -> str:
        data = self.answers
        mask = self.use_masking_var.get()

        complainant_rrn = self._mask_rrn(data.get("complainant_rrn", ""), mask)
        respondent_rrn = self._mask_rrn(data.get("respondent_rrn", ""), mask)

        # 할루시네이션 억제를 위해 입력되지 않은 판단근거는 자동 생성하지 않는다.
        raw_judgment = data.get("inspector_judgment", "").strip()
        inspector_judgment = self._safe_text(raw_judgment)
        if not raw_judgment:
            inspector_judgment = "추가 확인 필요: 근거자료 확인 후 판단 입력"

        references = self._build_reference_block()
        case_type_block = self._build_case_type_block()

        lines = [
            "# 내사 보고서",
            "",
            "## 1. 기본정보",
            f"- 사건번호: {self._safe_text(data.get('case_id', ''))}",
            f"- 내사 검토 기간: {self._safe_text(data.get('investigation_period', ''))}",
            "- 진정인정보:",
            f"  - 이름: {self._safe_text(data.get('complainant_name', ''))}",
            f"  - 주민번호: {complainant_rrn}",
            f"  - 주소: {self._safe_text(data.get('complainant_address', ''))}",
            f"  - 전화번호: {self._safe_text(data.get('complainant_phone', ''))}",
            "- 피진정인정보:",
            f"  - 이름: {self._safe_text(data.get('respondent_name', ''))}",
            f"  - 주민번호: {respondent_rrn}",
            f"  - 주소: {self._safe_text(data.get('respondent_address', ''))}",
            f"  - 전화번호: {self._safe_text(data.get('respondent_phone', ''))}",
            "- 사업장정보:",
            f"  - 명칭: {self._safe_text(data.get('workplace_name', ''))}",
            f"  - 주소: {self._safe_text(data.get('workplace_address', ''))}",
            f"  - 업종: {self._safe_text(data.get('workplace_industry', ''))}",
            f"  - 상시근로자수: {self._safe_text(data.get('workplace_workers', ''))}",
            "",
            "## 2. 내사검토",
            "### 2.1 인정되는 사실",
            self._as_bullets(data.get("recognized_facts", "")),
            "",
            "### 2.2 진정인 주장",
            self._as_bullets(data.get("claimant_claim", "")),
            "",
            "### 2.3 피진정인 주장",
            self._as_bullets(data.get("respondent_claim", "")),
            "",
            "### 2.4 증거자료",
            self._as_bullets(data.get("evidence_summary", "")),
            "",
            case_type_block,
            "",
            "## 3. 내사결과",
            "### 3.1 근로감독관 판단",
            self._as_bullets(inspector_judgment),
            "",
            "### 3.2 근거 인용(판례/질의회시/지침/법령)",
            references,
            "",
            "### 3.3 결과",
            f"- {self._safe_text(data.get('result', self.result_var.get()))}",
            "",
            "## 4. 검증메모",
            "- 본 보고서의 판단 문장은 사용자 입력값을 기반으로 작성되었음.",
            "- 자동 생성된 추정 문장을 사용하지 않으며, 누락 시 '추가 확인 필요'로 표기함.",
            "- 판례/질의회시/지침 원문 대조 후 최종 결재 필요.",
        ]
        return "\n".join(lines).strip() + "\n"

    def _build_case_type_block(self) -> str:
        case_type = self.case_type_var.get()
        keys = [q.key for q in CASE_QUESTIONS.get(case_type, [])]

        lines = [f"### 2.5 사건유형 추가사항 ({case_type})"]
        if not keys:
            lines.append("- 추가사항 없음")
            return "\n".join(lines)

        for key in keys:
            value = self._safe_text(self.answers.get(key, ""))
            if not value:
                value = "추가 확인 필요"
            label = key
            lines.append(f"- {label}: {value}")
        return "\n".join(lines)

    def _build_reference_block(self) -> str:
        # 입력 편의를 위해 자유형식 한 칸에 입력하도록 제공한다.
        raw = self.answers.get("reference_text", "").strip()
        if not raw:
            raw = (
                "추가 확인 필요: 관련 판례 사건번호/선고일, 질의회시 문서번호/회시일자, "
                "지침명/시행일, 법령 조문을 입력하세요."
            )
        return self._as_bullets(raw)

    def _mask_rrn(self, value: str, mask: bool) -> str:
        if not value:
            return ""
        digits = value.replace("-", "")
        if len(digits) != 13:
            return value
        if not mask:
            return f"{digits[:6]}-{digits[6:]}"
        return f"{digits[:6]}-{digits[6]}******"

    @staticmethod
    def _safe_text(value: str) -> str:
        value = (value or "").strip()
        return value if value else "추가 확인 필요"

    @staticmethod
    def _as_bullets(value: str) -> str:
        text = (value or "").strip()
        if not text:
            return "- 추가 확인 필요"
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        if not lines:
            return "- 추가 확인 필요"
        return "\n".join(f"- {line}" for line in lines)

    @staticmethod
    def _set_text(widget: tk.Text, value: str) -> None:
        widget.config(state="normal")
        widget.delete("1.0", tk.END)
        widget.insert("1.0", value)
        widget.config(state="disabled")


def main() -> None:
    app = ReportApp()
    # 근거 인용 입력용 초기 프롬프트를 답변 딕셔너리에 미리 넣는다.
    app.answers.setdefault(
        "reference_text",
        "판례: 사건번호/선고일/요지\n질의회시: 문서번호/회시일/요지\n지침: 지침명/시행일/핵심\n법령: 조문번호/핵심",
    )
    app.mainloop()


if __name__ == "__main__":
    main()
