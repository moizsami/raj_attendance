import frappe
from frappe import _
from frappe.utils import flt, getdate, get_first_day, get_last_day, today

# Import your existing helpers
from raj_attendance.raj_attendance.employee_advance_validation import (
    _get_employee_shift_type,
    _get_salary_structure_assignment,
    _get_present_days_count,
    _get_existing_advance_amount_for_month,
    _get_allowed_advance_for_bracket,
    SOLAF_TYPE_60_PERCENT,
    SOLAF_TYPE_1500_AFTER_7_DAYS,
    SOLAF_TYPE_WORKER_60_PERCENT,
    DEFAULT_PAYMENT_DAYS,
    ADVANCE_PER_7_DAYS,
    DAYS_PER_BRACKET,
)


@frappe.whitelist()
def check_advance_limit(employee, advance_amount, posting_date, doc_name=""):
    """
    Returns dict:
      { "exceeded": True/False, "details": "HTML string with reason" }
    Called from client script before save.
    """
    advance_amount = flt(advance_amount)
    if advance_amount <= 0:
        return {"exceeded": False}

    shift_name, solaf_type = _get_employee_shift_type(employee)
    if not shift_name or not solaf_type:
        return {"exceeded": False}

    exclude_name = doc_name if doc_name and doc_name != "New Employee Advance 1" else None

    if solaf_type == SOLAF_TYPE_60_PERCENT:
        return _check_60_percent(employee, advance_amount, posting_date, exclude_name)

    elif solaf_type == SOLAF_TYPE_1500_AFTER_7_DAYS:
        return _check_1500_after_7_days(employee, advance_amount, posting_date, exclude_name)

    elif solaf_type == SOLAF_TYPE_WORKER_60_PERCENT:
        return _check_worker_60_percent(employee, advance_amount, posting_date, exclude_name)

    return {"exceeded": False}


def _check_60_percent(employee, advance_amount, posting_date, exclude_name):
    posting_date = getdate(posting_date)
    current_date = getdate(today())
    days_passed = current_date.day

    ssa = _get_salary_structure_assignment(employee, posting_date)
    if not ssa:
        return {"exceeded": False}  # Let server validation handle missing SSA

    base = ssa.get("base")
    payment_days = ssa.get("custom_payment_days") or DEFAULT_PAYMENT_DAYS

    daily_rate = flt(base) / flt(payment_days)
    earned_salary = flt(days_passed) * daily_rate
    allowed_advance = flt(earned_salary * 0.60, 2)

    existing_advance = _get_existing_advance_amount_for_month(employee, posting_date, exclude_name)
    total_advance = flt(existing_advance) + flt(advance_amount)

    if total_advance > allowed_advance:
        remaining = max(0, flt(allowed_advance - existing_advance, 2))
        details = (
            f"Days Passed: {days_passed} | الأيام المنقضية: {days_passed}<br>"
            f"Allowed (60%): {frappe.format_value(allowed_advance, {'fieldtype':'Currency'})} | "
            f"المسموح (60%): {frappe.format_value(allowed_advance, {'fieldtype':'Currency'})}<br>"
            f"Existing Advances: {frappe.format_value(existing_advance, {'fieldtype':'Currency'})} | "
            f"السلف الحالية: {frappe.format_value(existing_advance, {'fieldtype':'Currency'})}<br>"
            f"Remaining Allowance: {frappe.format_value(remaining, {'fieldtype':'Currency'})} | "
            f"المتبقي: {frappe.format_value(remaining, {'fieldtype':'Currency'})}"
        )
        return {"exceeded": True, "details": details}

    return {"exceeded": False}


def _check_worker_60_percent(employee, advance_amount, posting_date, exclude_name):
    posting_date = getdate(posting_date)
    current_date = getdate(today())
    month_start = get_first_day(posting_date)
    month_end = get_last_day(posting_date)
    attendance_end = min(month_end, current_date)

    present_days = _get_present_days_count(employee, month_start, attendance_end)

    ssa = _get_salary_structure_assignment(employee, posting_date)
    if not ssa:
        return {"exceeded": False}

    base = ssa.get("base")
    badal_wagba = ssa.get("custom_badal_wagba")
    daily_rate = flt(base) + flt(badal_wagba)

    total_earned = daily_rate * flt(present_days)
    allowed_advance = flt(total_earned * 0.60, 2)

    existing_advance = _get_existing_advance_amount_for_month(employee, posting_date, exclude_name)
    total_advance = flt(existing_advance) + flt(advance_amount)

    if total_advance > allowed_advance:
        remaining = max(0, flt(allowed_advance - existing_advance, 2))
        details = (
            f"Present Days: {present_days} | أيام الحضور: {present_days}<br>"
            f"Daily Rate: {frappe.format_value(daily_rate, {'fieldtype':'Currency'})} | "
            f"المعدل اليومي: {frappe.format_value(daily_rate, {'fieldtype':'Currency'})}<br>"
            f"Allowed (60%): {frappe.format_value(allowed_advance, {'fieldtype':'Currency'})} | "
            f"المسموح (60%): {frappe.format_value(allowed_advance, {'fieldtype':'Currency'})}<br>"
            f"Remaining Allowance: {frappe.format_value(remaining, {'fieldtype':'Currency'})} | "
            f"المتبقي: {frappe.format_value(remaining, {'fieldtype':'Currency'})}"
        )
        return {"exceeded": True, "details": details}

    return {"exceeded": False}


def _check_1500_after_7_days(employee, advance_amount, posting_date, exclude_name):
    posting_date = getdate(posting_date)
    month_start = get_first_day(posting_date)
    month_end = get_last_day(posting_date)

    present_days = _get_present_days_count(employee, month_start, month_end)
    allowed_advance = _get_allowed_advance_for_bracket(present_days)

    existing_advance = _get_existing_advance_amount_for_month(employee, posting_date, exclude_name)
    total_advance = flt(existing_advance) + flt(advance_amount)

    exceeded = (advance_amount > ADVANCE_PER_7_DAYS) or (present_days < DAYS_PER_BRACKET) or (total_advance > allowed_advance)

    if exceeded:
        bracket = present_days // DAYS_PER_BRACKET
        remaining = max(0, flt(allowed_advance - existing_advance, 2))
        details = (
            f"Present Days: {present_days} | أيام الحضور: {present_days}<br>"
            f"Complete Weeks: {bracket} | أسابيع كاملة: {bracket}<br>"
            f"Allowed Advance: {frappe.format_value(allowed_advance, {'fieldtype':'Currency'})} | "
            f"السلفة المسموحة: {frappe.format_value(allowed_advance, {'fieldtype':'Currency'})}<br>"
            f"Remaining Allowance: {frappe.format_value(remaining, {'fieldtype':'Currency'})} | "
            f"المتبقي: {frappe.format_value(remaining, {'fieldtype':'Currency'})}"
        )
        return {"exceeded": True, "details": details}

    return {"exceeded": False}