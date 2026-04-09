#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""통상임금 계산기

2024년 대법원 판례를 반영하여 고정성 징표를 별도 요건으로 보지 않고,
지급 형태와 목적을 중심으로 통상임금 포함 여부를 안내합니다.
"""

import tkinter as tk
from tkinter import ttk
from tkinter import messagebox

COMMON_ITEM_RULES = {
    "기본급": True,
    "정액수당": True,
    "직책수당": True,
    "직무수당": True,
    "고정급": True,
    "정기상여금": True,
    "정기적 상여금": True,
    "정기 상여금": True,
    "성과급": False,
    "성과보수": False,
    "업적수당": False,
    "위험수당": True,
    "교통비": None,
    "식대": None,
    "식비": None,
    "복리후생비": None,
    "퇴직금계산용 지급액": None,
}

EXPLANATION = {
    True: "통상임금 포함 가능성이 높습니다.",
    False: "통상임금에 포함되지 않을 가능성이 큽니다.",
    None: "통상임금 포함 여부가 개별 판례와 계약 내용에 따라 달라질 수 있습니다."
}

FREQUENCY_HINT = "월, 분기, 연, 일시"


def classify_item(name, frequency, amount, performance):
    key = name.strip()
    if key in COMMON_ITEM_RULES:
        result = COMMON_ITEM_RULES[key]
    else:
        result = None

    if performance:
        return False, "성과급 또는 인센티브 요소로 판단되어 통상임금에서 제외됩니다."

    if amount <= 0:
        return False, "금액이 0이거나 입력되지 않았습니다."

    freq = frequency.lower().strip()
    if freq in ["월", "매월", "정기", "매달"]:
        if result is False:
            return False, EXPLANATION[False]
        return True, EXPLANATION[result] if result is not None else "정기적으로 지급되는 항목으로 통상임금 포함 가능성이 있습니다."

    if freq in ["분기", "반기", "년", "연"]:
        if result is True:
            return True, "정기적 상여금 등으로서 통상임금 산정에 포함될 수도 있습니다."
        return False, EXPLANATION[result] if result is not None else "정기적이지 않은 지급은 통상임금에서 제외되는 경향이 있습니다."

    if freq in ["일시", "일시금", "일회"]:
        return False, "일시금 성격으로 통상임금에서 제외됩니다."

    return result if result is not None else None, EXPLANATION[result] if result is not None else "지급 목적과 실질을 더 조사해야 합니다."


def calculate_ordinary_wage(base_salary, items):
    ordinary_wage_total = base_salary
    included = ["기본급"]
    excluded = []
    details = []

    for item in items:
        include, reason = classify_item(item[0], item[1], item[2], item[3])
        if include:
            ordinary_wage_total += item[2]
            included.append(item[0])
        else:
            excluded.append(item[0])
        details.append((item[0], item[2], include, reason))

    return ordinary_wage_total, included, excluded, details


def format_money(value):
    return f"{int(value):,}원"


class OrdinaryWageCalculator(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("통상임금 계산기")
        self.geometry("760x620")
        self.resizable(False, False)

        self.item_rows = []
        self._build_ui()

    def _build_ui(self):
        header = tk.Label(self, text="2024년 대법원 판례 반영 - 고정성 징표를 별도 요건으로 보지 않습니다.", font=("Malgun Gothic", 11), wraplength=740, justify="left")
        header.pack(padx=16, pady=(12, 6), anchor="w")

        base_frame = ttk.Frame(self)
        base_frame.pack(fill="x", padx=16, pady=6)

        ttk.Label(base_frame, text="기본급 (원):").grid(row=0, column=0, sticky="w")
        self.base_salary_var = tk.StringVar(value="0")
        base_entry = ttk.Entry(base_frame, textvariable=self.base_salary_var, width=20)
        base_entry.grid(row=0, column=1, sticky="w", padx=(4, 16))

        ttk.Label(base_frame, text="항목 수: ").grid(row=0, column=2, sticky="w")
        self.row_count_label = ttk.Label(base_frame, text="0")
        self.row_count_label.grid(row=0, column=3, sticky="w")

        self._build_items_table()

        button_frame = ttk.Frame(self)
        button_frame.pack(fill="x", padx=16, pady=(8, 0))

        add_button = ttk.Button(button_frame, text="항목 추가", command=self.add_item_row)
        add_button.pack(side="left")

        calculate_button = ttk.Button(button_frame, text="계산하기", command=self.calculate)
        calculate_button.pack(side="left", padx=8)

        clear_button = ttk.Button(button_frame, text="항목 초기화", command=self.clear_items)
        clear_button.pack(side="left")

        self.result_text = tk.Text(self, width=92, height=18, wrap="word", state="disabled", background="#f8f8f8")
        self.result_text.pack(padx=16, pady=(12, 16), fill="both", expand=True)

        note = tk.Label(self, text="참고: 이 계산기는 법률 전문가의 최종 판단을 대신하지 않습니다. 실제 분쟁 시 계약 내용, 지급 관행, 판례를 종합적으로 검토해야 합니다.", wraplength=740, justify="left", fg="#444444")
        note.pack(padx=16, pady=(0, 12), anchor="w")

        self.add_item_row()
        self.add_item_row()

    def _build_items_table(self):
        frame = ttk.Frame(self)
        frame.pack(fill="x", padx=16, pady=6)

        headers = ["항목 이름", "금액(원)", "지급 주기", "성과급 여부", "삭제"]
        for idx, text in enumerate(headers):
            ttk.Label(frame, text=text, font=("Malgun Gothic", 10, "bold")).grid(row=0, column=idx, padx=4, pady=2, sticky="w")

        self.items_container = ttk.Frame(frame)
        self.items_container.grid(row=1, column=0, columnspan=5, sticky="nsew")

    def add_item_row(self):
        row_frame = ttk.Frame(self.items_container)
        row_frame.pack(fill="x", pady=2)

        name_var = tk.StringVar()
        amount_var = tk.StringVar(value="0")
        frequency_var = tk.StringVar(value="월")
        performance_var = tk.BooleanVar(value=False)

        ttk.Entry(row_frame, textvariable=name_var, width=24).grid(row=0, column=0, padx=4)
        ttk.Entry(row_frame, textvariable=amount_var, width=16).grid(row=0, column=1, padx=4)
        ttk.Entry(row_frame, textvariable=frequency_var, width=12).grid(row=0, column=2, padx=4)
        ttk.Checkbutton(row_frame, variable=performance_var, text="예").grid(row=0, column=3, padx=4)

        delete_button = ttk.Button(row_frame, text="삭제", command=lambda: self.remove_item_row(row_frame))
        delete_button.grid(row=0, column=4, padx=4)

        self.item_rows.append((row_frame, name_var, amount_var, frequency_var, performance_var))
        self.row_count_label.config(text=str(len(self.item_rows)))

    def remove_item_row(self, row_frame):
        for row in self.item_rows:
            if row[0] == row_frame:
                row_frame.destroy()
                self.item_rows.remove(row)
                self.row_count_label.config(text=str(len(self.item_rows)))
                return

    def clear_items(self):
        for row_frame, *_ in list(self.item_rows):
            row_frame.destroy()
        self.item_rows.clear()
        self.row_count_label.config(text="0")

    def _parse_amount(self, value):
        try:
            return float(value.replace(",", ""))
        except ValueError:
            return None

    def calculate(self):
        base_value = self._parse_amount(self.base_salary_var.get())
        if base_value is None or base_value <= 0:
            messagebox.showwarning("입력 오류", "기본급은 0보다 큰 숫자로 입력해 주세요.")
            return

        items = []
        for _, name_var, amount_var, frequency_var, performance_var in self.item_rows:
            name = name_var.get().strip()
            if not name:
                continue
            amount = self._parse_amount(amount_var.get())
            if amount is None:
                messagebox.showwarning("입력 오류", f"{name} 항목의 금액을 올바른 숫자로 입력해 주세요.")
                return
            frequency = frequency_var.get().strip() or "월"
            performance = performance_var.get()
            items.append((name, frequency, amount, performance))

        ordinary_wage, included, excluded, details = calculate_ordinary_wage(base_value, items)
        self._display_result(base_value, ordinary_wage, included, excluded, details)

    def _display_result(self, base_salary, ordinary_wage, included, excluded, details):
        self.result_text.configure(state="normal")
        self.result_text.delete("1.0", tk.END)

        lines = [
            "=== 계산 결과 ===",
            f"기본급: {format_money(base_salary)}",
            f"통상임금 포함 합계: {format_money(ordinary_wage)}",
            f"일당(30일 기준): {format_money(ordinary_wage / 30)}",
            f"시급(8시간 기준): {format_money(ordinary_wage / 30 / 8)}",
            "",
            "=== 항목별 판단 ===",
        ]

        for name, amount, include, reason in details:
            status = "포함" if include else "제외"
            lines.append(f"- {name}: {format_money(amount)} -> {status} ({reason})")

        lines.extend([
            "",
            f"포함 항목: {', '.join(included)}",
            f"제외 항목: {', '.join(excluded) if excluded else '없음'}",
        ])

        self.result_text.insert(tk.END, "\n".join(lines))
        self.result_text.configure(state="disabled")


if __name__ == "__main__":
    app = OrdinaryWageCalculator()
    app.mainloop()
