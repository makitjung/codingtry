#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""퇴직금 산정 프로그램

한국 노동법에 따른 퇴직금을 계산합니다.
퇴직금 = 평균임금 × 근속연수 × 30일
"""

import tkinter as tk
from tkinter import ttk
from tkinter import messagebox
from datetime import datetime, date
import calendar

def calculate_service_years(start_date, end_date):
    """근속연수 계산 (년 단위)"""
    delta = end_date - start_date
    years = delta.days / 365.25
    return years

def calculate_average_wage(monthly_wages):
    """평균임금 계산 (최근 3개월 임금 총액 ÷ 90)"""
    if len(monthly_wages) != 3:
        raise ValueError("최근 3개월 임금을 입력하세요.")
    total_wage = sum(monthly_wages)
    average_wage = total_wage / 90  # 3개월 × 30일
    return average_wage

def calculate_severance_pay(average_wage, service_years):
    """퇴직금 계산"""
    return average_wage * service_years * 30

def format_money(value):
    return f"{int(value):,}원"

class SeverancePayCalculator(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("퇴직금 산정 프로그램")
        self.geometry("600x500")
        self.resizable(False, False)

        self._build_ui()

    def _build_ui(self):
        header = tk.Label(self, text="한국 노동법에 따른 퇴직금 계산", font=("Malgun Gothic", 12), wraplength=580, justify="left")
        header.pack(padx=16, pady=(12, 6), anchor="w")

        # 입사일, 퇴사일 입력
        date_frame = ttk.Frame(self)
        date_frame.pack(fill="x", padx=16, pady=6)

        ttk.Label(date_frame, text="입사일 (YYYY-MM-DD):").grid(row=0, column=0, sticky="w")
        self.start_date_var = tk.StringVar(value=date.today().replace(day=1).strftime("%Y-%m-%d"))
        start_entry = ttk.Entry(date_frame, textvariable=self.start_date_var, width=15)
        start_entry.grid(row=0, column=1, sticky="w", padx=(4, 16))

        ttk.Label(date_frame, text="퇴사일 (YYYY-MM-DD):").grid(row=1, column=0, sticky="w")
        self.end_date_var = tk.StringVar(value=date.today().strftime("%Y-%m-%d"))
        end_entry = ttk.Entry(date_frame, textvariable=self.end_date_var, width=15)
        end_entry.grid(row=1, column=1, sticky="w", padx=(4, 16))

        # 최근 3개월 임금 입력
        wage_frame = ttk.Frame(self)
        wage_frame.pack(fill="x", padx=16, pady=6)

        ttk.Label(wage_frame, text="최근 3개월 월별 임금 (원):", font=("Malgun Gothic", 10, "bold")).grid(row=0, column=0, columnspan=2, sticky="w")

        self.monthly_wages = []
        for i in range(3):
            ttk.Label(wage_frame, text=f"{i+1}개월 전:").grid(row=i+1, column=0, sticky="w")
            wage_var = tk.StringVar(value="0")
            entry = ttk.Entry(wage_frame, textvariable=wage_var, width=15)
            entry.grid(row=i+1, column=1, sticky="w", padx=(4, 16))
            self.monthly_wages.append(wage_var)

        # 계산 버튼
        button_frame = ttk.Frame(self)
        button_frame.pack(fill="x", padx=16, pady=(8, 0))

        calculate_button = ttk.Button(button_frame, text="퇴직금 계산", command=self.calculate)
        calculate_button.pack(side="left")

        # 결과 표시
        self.result_text = tk.Text(self, width=70, height=12, wrap="word", state="disabled", background="#f8f8f8")
        self.result_text.pack(padx=16, pady=(12, 16), fill="both", expand=True)

        note = tk.Label(self, text="참고: 이 프로그램은 기본적인 계산을 제공하며, 실제 퇴직금은 근로계약, 회사 규정에 따라 달라질 수 있습니다.", wraplength=580, justify="left", fg="#444444")
        note.pack(padx=16, pady=(0, 12), anchor="w")

    def _parse_date(self, date_str):
        try:
            return datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            raise ValueError("날짜 형식을 YYYY-MM-DD로 입력하세요.")

    def _parse_wage(self, wage_str):
        try:
            return float(wage_str.replace(",", ""))
        except ValueError:
            raise ValueError("임금을 숫자로 입력하세요.")

    def calculate(self):
        try:
            start_date = self._parse_date(self.start_date_var.get())
            end_date = self._parse_date(self.end_date_var.get())

            if start_date >= end_date:
                messagebox.showwarning("입력 오류", "퇴사일은 입사일보다 늦어야 합니다.")
                return

            monthly_wages = [self._parse_wage(var.get()) for var in self.monthly_wages]

            service_years = calculate_service_years(start_date, end_date)
            average_wage = calculate_average_wage(monthly_wages)
            severance_pay = calculate_severance_pay(average_wage, service_years)

            self._display_result(start_date, end_date, service_years, average_wage, severance_pay, monthly_wages)

        except ValueError as e:
            messagebox.showwarning("입력 오류", str(e))

    def _display_result(self, start_date, end_date, service_years, average_wage, severance_pay, monthly_wages):
        self.result_text.configure(state="normal")
        self.result_text.delete("1.0", tk.END)

        lines = [
            "=== 퇴직금 산정 결과 ===",
            f"입사일: {start_date}",
            f"퇴사일: {end_date}",
            f"근속연수: {service_years:.2f}년",
            "",
            "최근 3개월 월별 임금:",
        ]

        for i, wage in enumerate(monthly_wages):
            lines.append(f"  {i+1}개월 전: {format_money(wage)}")

        lines.extend([
            "",
            f"평균임금 (일당): {format_money(average_wage)}",
            f"퇴직금 총액: {format_money(severance_pay)}",
            "",
            "계산식: 평균임금 × 근속연수 × 30일",
            f"        {format_money(average_wage)} × {service_years:.2f} × 30 = {format_money(severance_pay)}"
        ])

        self.result_text.insert(tk.END, "\n".join(lines))
        self.result_text.configure(state="disabled")


if __name__ == "__main__":
    app = SeverancePayCalculator()
    app.mainloop()