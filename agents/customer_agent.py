"""
agents/customer_agent.py
고객 DB를 조회하여 가입 보험 정보를 반환합니다.
"""

import pandas as pd
from datetime import datetime
from pathlib import Path

# ==========================================
# 고객 DB 로드
# ==========================================
DB_PATH = Path(__file__).parent.parent / "customers.csv"
df = None

def get_df():
    global df
    if df is None:
        df = pd.read_csv(DB_PATH)
    return df

def get_customer_info(customer_id: str) -> dict:
    """
    로그인한 고객의 보험 가입 정보 조회
    반환: {customer_id, name, phone, policies: [...]}
    """
    rows = get_df()[get_df()["customer_id"] == customer_id]
    if rows.empty:
        return {}

    customer = {
        "customer_id": customer_id,
        "name": rows.iloc[0]["customer_name"],
        "phone": rows.iloc[0]["phone"],
        "policies": []
    }

    for _, row in rows.iterrows():
        policy = {
            "product_name":   row["product_name"],
            "product_id":     row["product_id"],
            "policy_number":  row["policy_number"],
            "joined_year":    int(row["joined_year"]),
            "coverage_limit": row["coverage_limit"],
            "riders":         row["riders"],
            "vehicle_number": row.get("vehicle_number", ""),
        }
        customer["policies"].append(policy)

    return customer


def get_subscribed_domains(customer_info: dict) -> list:
    """
    고객이 가입한 보험의 도메인 목록 반환
    예: ["auto", "teeth"]
    """
    from utils.llm_setup import PRODUCT_TO_DOMAIN

    domains = []
    for policy in customer_info.get("policies", []):
        domain = PRODUCT_TO_DOMAIN.get(policy["product_id"])
        if domain and domain not in domains:
            domains.append(domain)
    return domains


def format_customer_info(customer: dict) -> str:
    """
    고객 정보를 LLM 프롬프트용 텍스트로 변환
    """
    if not customer:
        return "고객 정보 없음"

    current_year = datetime.now().year
    lines = [f"고객명: {customer['name']} (ID: {customer['customer_id']})"]

    for p in customer["policies"]:
        years = current_year - p["joined_year"]
        line = (
            f"- {p['product_name']} | "
            f"가입연도: {p['joined_year']}년 ({years}년차) | "
            f"보장한도: {p['coverage_limit']} | "
            f"특약: {p['riders']}"
        )
        if p.get("vehicle_number"):
            line += f" | 차량번호: {p['vehicle_number']}"
        lines.append(line)

    return "\n".join(lines)


def login(customer_id: str, password: str) -> dict | None:
    """
    간단한 로그인 검증
    반환: 고객 정보 dict (실패 시 None)
    """
    rows = get_df()[
        (get_df()["customer_id"] == customer_id) &
        (get_df()["password"].astype(str) == str(password))
    ]
    if rows.empty:
        return None
    return get_customer_info(customer_id)
