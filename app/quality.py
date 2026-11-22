"""Transparent, deterministic DQ rules on synthetic institution interface data only."""
from datetime import date
import hashlib

COLUMNS = ["institution_id", "institution_name", "system_code", "status", "success_rate", "go_live_date"]
STATES = {"active", "testing", "inactive"}


def check_rows(rows: list[dict], limit: int = 1000) -> dict:
    if not isinstance(rows, list) or not 1 <= len(rows) <= limit:
        raise ValueError(f"请导入1至{limit}行数据")
    seen = set()
    errors = []
    for idx, row in enumerate(rows, start=2):
        if not isinstance(row, dict) or set(row) != set(COLUMNS):
            raise ValueError("CSV列必须与提供的数据字典完全一致，禁止上传患者或其他额外字段")
        if any(not isinstance(v, (str, int, float, type(None))) or len(str(v or "")) > 200 for v in row.values()):
            raise ValueError("数据格式或字段长度不符合要求")
        ident = str(row["institution_id"] or "").strip()
        name = str(row["institution_name"] or "").strip()
        code = str(row["system_code"] or "").strip()
        state = str(row["status"] or "").strip()
        rate = str(row["success_rate"] if row["success_rate"] is not None else "").strip()
        day = str(row["go_live_date"] or "").strip()
        checks = []
        if not ident: checks.append("institution_id_missing")
        if not name: checks.append("institution_name_missing")
        if not code: checks.append("system_code_missing")
        if ident and ident in seen: checks.append("institution_id_duplicate")
        if ident: seen.add(ident)
        if state not in STATES: checks.append("status_invalid")
        try:
            n = float(rate)
            if not (0 <= n <= 100): checks.append("success_rate_out_of_range")
        except ValueError:
            checks.append("success_rate_invalid")
        try:
            if date.fromisoformat(day).isoformat() != day: raise ValueError()
        except ValueError:
            checks.append("go_live_date_invalid")
        for rule in checks:
            key = f"{idx}:{ident}:{rule}"
            errors.append({"row": idx, "institution_id": ident, "rule": rule,
                           "fingerprint": hashlib.sha256(key.encode()).hexdigest()})
    bad = len({a["row"] for a in errors})
    return {"total": len(rows), "bad_count": bad, "passed": len(rows)-bad,
            "pass_rate": round((len(rows)-bad)*100/len(rows), 2), "errors": errors}
