# people_hr.py
# Thin wrapper over the People HR REST API. Used to enrich below-minimum
# visa hour violations with holiday + absence context so the operator can
# see whether a weekly shortfall is explained by approved leave.
#
# All three endpoints take POST with a JSON body that includes APIKey and
# Action. Holiday filters to Status == "Approved"; absence records are
# all assumed valid (the API has no separate approval flag).

from datetime import date, datetime, timedelta

import requests

from config import (
    PEOPLE_HR_BASE_URL,
    PEOPLE_HR_API_KEY,
    PEOPLE_HR_TIMEOUT,
    PEOPLE_HR_EMPLOYEE_RESOURCE,
    PEOPLE_HR_HOLIDAY_RESOURCE,
    PEOPLE_HR_ABSENCE_RESOURCE,
    PEOPLE_HR_ACTION_EMPLOYEES,
    PEOPLE_HR_ACTION_HOLIDAY,
    PEOPLE_HR_ACTION_ABSENCE,
    STANDARD_WORK_DAY_HOURS,
)


def _post(resource, payload):
    """POST to a People HR resource, return parsed JSON.

    Raises RuntimeError on transport failure or when the API reports
    IsError == "true". Callers convert these into Leave=Unknown.
    """
    url = PEOPLE_HR_BASE_URL.rstrip("/") + resource
    body = {"APIKey": PEOPLE_HR_API_KEY, **payload}
    resp = requests.post(url, json=body, timeout=PEOPLE_HR_TIMEOUT)
    resp.raise_for_status()
    data = resp.json()
    if str(data.get("IsError", "")).lower() == "true":
        raise RuntimeError(data.get("Message") or "People HR error")
    return data


def _dv(field):
    """Unwrap People HR's {DisplayValue: ...} envelope (returns '' if absent)."""
    if isinstance(field, dict):
        return str(field.get("DisplayValue", "") or "").strip()
    return ""


def _parse_iso_date(s):
    if not s:
        return None
    try:
        return datetime.strptime(str(s)[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def fetch_all_employees():
    """Return a flat list of {employee_id, first_name, last_name, full_name}.

    Leavers are excluded server-side via IncludeLeavers=false.
    """
    data = _post(
        PEOPLE_HR_EMPLOYEE_RESOURCE,
        {"Action": PEOPLE_HR_ACTION_EMPLOYEES, "IncludeLeavers": "false"},
    )
    out = []
    for rec in data.get("Result", []) or []:
        emp_id = _dv(rec.get("EmployeeId"))
        first = _dv(rec.get("FirstName"))
        last = _dv(rec.get("LastName"))
        if not emp_id:
            continue
        full = (first + " " + last).strip()
        out.append({
            "employee_id": emp_id,
            "first_name": first,
            "last_name": last,
            "full_name": full,
        })
    return out


def fetch_holiday(employee_id, start, end):
    """Approved holiday records for one employee across [start, end] inclusive."""
    data = _post(
        PEOPLE_HR_HOLIDAY_RESOURCE,
        {
            "Action": PEOPLE_HR_ACTION_HOLIDAY,
            "EmployeeId": employee_id,
            "StartDate": start.isoformat(),
            "EndDate": end.isoformat(),
        },
    )
    return [r for r in (data.get("Result") or [])
            if str(r.get("Status", "")).lower() == "approved"]


def fetch_absence(employee_id, start, end):
    """All absence records for one employee across [start, end] inclusive.

    The absence response has no approval-status field, so every returned
    record is counted (sickness, emergency leave, etc.).
    """
    data = _post(
        PEOPLE_HR_ABSENCE_RESOURCE,
        {
            "Action": PEOPLE_HR_ACTION_ABSENCE,
            "EmployeeId": employee_id,
            "StartDate": start.isoformat(),
            "EndDate": end.isoformat(),
        },
    )
    return data.get("Result") or []


def _overlap_days(rec_start, rec_end, win_start, win_end):
    """Number of calendar days where [rec_start, rec_end] overlaps the window.

    All four args are date objects; range bounds inclusive.
    """
    if rec_start is None or rec_end is None:
        return 0
    lo = max(rec_start, win_start)
    hi = min(rec_end, win_end)
    if hi < lo:
        return 0
    return (hi - lo).days + 1


def _holiday_hours_in_window(rec, win_start, win_end):
    """Hours of one holiday record that fall inside [win_start, win_end].

    Uses DurationInMinutes (exact) when available; if the record spans
    multiple days we prorate by overlap_days / total_days.
    """
    rs = _parse_iso_date(rec.get("StartDate"))
    re_ = _parse_iso_date(rec.get("EndDate"))
    overlap = _overlap_days(rs, re_, win_start, win_end)
    if overlap == 0:
        return 0.0

    total_minutes = float(rec.get("DurationInMinutes") or 0)
    total_days = float(rec.get("DurationInDays") or 0)
    if total_minutes > 0 and total_days > 0:
        return (total_minutes / 60.0) * (overlap / total_days)
    if total_minutes > 0:
        return total_minutes / 60.0
    # Fall back to standard work-day hours when no minutes returned
    return overlap * STANDARD_WORK_DAY_HOURS


def _absence_hours_in_window(rec, win_start, win_end):
    """Hours of one absence record that fall inside [win_start, win_end].

    Absence has no minutes field, so we convert overlap_days using the
    STANDARD_WORK_DAY_HOURS config constant.
    """
    rs = _parse_iso_date(rec.get("StartDate"))
    re_ = _parse_iso_date(rec.get("EndDate"))
    overlap = _overlap_days(rs, re_, win_start, win_end)
    if overlap == 0:
        return 0.0
    total_days = float(rec.get("DurationDays") or rec.get("DurationInDaysThisPeriod") or 0)
    if total_days > 0:
        # Prorate by overlap when the record spans more than the window
        rec_span = max(1, (re_ - rs).days + 1) if rs and re_ else overlap
        hours_per_day = (total_days / rec_span) * STANDARD_WORK_DAY_HOURS
        return overlap * hours_per_day
    return overlap * STANDARD_WORK_DAY_HOURS


def summarize_leave_for_week(holiday_records, absence_records, week_start, week_end):
    """Compute (status, hours, details) for one week from cached records.

    holiday_records / absence_records are the full-period lists fetched
    once per employee; this function slices them to the week without
    making further API calls.

    Returns:
      status: "Yes" if any record overlaps the week, else "No"
      hours:  total leave hours falling inside the week (float)
      details: human-readable per-record breakdown
    """
    bits = []
    total_hours = 0.0

    for r in holiday_records:
        rs = _parse_iso_date(r.get("StartDate"))
        re_ = _parse_iso_date(r.get("EndDate"))
        if _overlap_days(rs, re_, week_start, week_end) == 0:
            continue
        hrs = _holiday_hours_in_window(r, week_start, week_end)
        total_hours += hrs
        part = r.get("PartOfDay") or ""
        part_str = f", {part}" if part and part not in ("", "All Day") else ""
        bits.append(
            f"Holiday {rs} to {re_} (Approved{part_str}, {hrs:.2f}h)"
        )

    for r in absence_records:
        rs = _parse_iso_date(r.get("StartDate"))
        re_ = _parse_iso_date(r.get("EndDate"))
        if _overlap_days(rs, re_, week_start, week_end) == 0:
            continue
        hrs = _absence_hours_in_window(r, week_start, week_end)
        total_hours += hrs
        reason = (r.get("Reason") or "").strip()
        emergency = str(r.get("EmergencyLeave", "")).lower() == "true"
        tail = []
        if reason:
            tail.append(reason)
        if emergency:
            tail.append("emergency")
        tail_str = f" - {', '.join(tail)}" if tail else ""
        bits.append(
            f"Absence {rs} to {re_}{tail_str} ({hrs:.2f}h)"
        )

    if not bits:
        return "No", 0.0, ""
    return "Yes", round(total_hours, 2), "; ".join(bits)
