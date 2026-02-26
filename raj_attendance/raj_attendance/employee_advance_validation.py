import frappe
from frappe import _
from frappe.utils import flt, getdate, get_first_day, get_last_day, today

# Constants for Solaf Types
SOLAF_TYPE_60_PERCENT = "60% of Salary"
SOLAF_TYPE_1500_AFTER_7_DAYS = "1500 after 7 days"
SOLAF_TYPE_WORKER_60_PERCENT = "Worker 60%"

# Constants for 1500-after-7-days brackets
ADVANCE_PER_7_DAYS = 1500
DAYS_PER_BRACKET = 7

# Default payment days if custom_payment_days is not set
DEFAULT_PAYMENT_DAYS = 30


def validate_employee_advance(doc, method=None):
    """
    Main validation hook for Employee Advance.
    Called on 'validate' event.

    Args:
        doc: Employee Advance document
        method: Hook method name (unused)
    """
    # Only validate if advance_amount is set and positive
    if not doc.advance_amount or flt(doc.advance_amount) <= 0:
        return

    # Get employee's shift and solaf type
    shift_name, solaf_type = _get_employee_shift_type(doc.employee)

    # If no shift assigned or no solaf_type, skip validation (allow advance)
    if not shift_name or not solaf_type:
        return

    # Route to appropriate validation based on solaf type
    if solaf_type == SOLAF_TYPE_60_PERCENT:
        _validate_60_percent_salary(doc)
    elif solaf_type == SOLAF_TYPE_1500_AFTER_7_DAYS:
        _validate_1500_after_7_days(doc)
    elif solaf_type == SOLAF_TYPE_WORKER_60_PERCENT:
        _validate_worker_60_percent(doc)
    # If unknown solaf_type, no validation applied


def _get_employee_shift_type(employee):
    """
    Get the employee's default shift and its custom_solaf_type value.

    Args:
        employee: Employee ID

    Returns:
        tuple: (shift_type_name, custom_solaf_type) or (None, None) if not found
    """
    # Get default_shift from Employee
    default_shift = frappe.db.get_value("Employee", employee, "default_shift")

    if not default_shift:
        return None, None

    # Get custom_solaf_type from Shift Type
    solaf_type = frappe.db.get_value("Shift Type", default_shift, "custom_solaf_type")

    return default_shift, solaf_type


def _get_present_days_count(employee, start_date, end_date):
    """
    Count submitted Attendance records with status 'Present' for employee
    within the date range.

    Args:
        employee: Employee ID
        start_date: Start of period
        end_date: End of period

    Returns:
        int: Count of present days
    """
    count = frappe.db.count(
        "Attendance",
        filters={
            "employee": employee,
            "attendance_date": ["between", [start_date, end_date]],
            "status": "Present",
            "docstatus": 1  # Submitted only
        }
    )
    return count or 0


def _get_salary_structure_assignment(employee, as_of_date):
    """
    Get the latest submitted Salary Structure Assignment for the employee.

    Args:
        employee: Employee ID
        as_of_date: Date to check against (typically posting_date)

    Returns:
        dict: {'base': float, 'custom_payment_days': float} or None
    """
    # Following pattern from overtime_calculation.py
    rows = frappe.db.sql(
        """
        SELECT base, COALESCE(custom_payment_days, %s) AS custom_payment_days
        FROM `tabSalary Structure Assignment`
        WHERE employee = %s AND docstatus = 1 AND from_date <= %s
        ORDER BY from_date DESC
        LIMIT 1
        """,
        (DEFAULT_PAYMENT_DAYS, employee, as_of_date),
        as_dict=True,
    )

    if not rows:
        return None

    return {
        "base": flt(rows[0].get("base")),
        "custom_payment_days": flt(rows[0].get("custom_payment_days")) or DEFAULT_PAYMENT_DAYS
    }


def _get_existing_advance_amount_for_month(employee, posting_date, exclude_name=None):
    """
    Sum of advance_amount from all SUBMITTED Employee Advance records
    for the same month as posting_date.

    Args:
        employee: Employee ID
        posting_date: Date to determine the month
        exclude_name: Document name to exclude (current document if being edited)

    Returns:
        float: Total existing advance amount
    """
    posting_date = getdate(posting_date)
    month_start = get_first_day(posting_date)
    month_end = get_last_day(posting_date)

    # Build query to sum submitted advances for the month
    total = frappe.db.sql(
        """
        SELECT COALESCE(SUM(advance_amount), 0) as total
        FROM `tabEmployee Advance`
        WHERE employee = %s
          AND posting_date BETWEEN %s AND %s
          AND docstatus = 1
          AND name != %s
        """,
        (employee, month_start, month_end, exclude_name or ""),
        as_dict=True
    )

    return flt(total[0].get("total")) if total else 0


def _validate_60_percent_salary(doc):
    """
    Validation logic for '60% of Salary' solaf type.

    Args:
        doc: Employee Advance document

    Raises:
        frappe.ValidationError: If advance exceeds allowed amount
    """
    posting_date = getdate(doc.posting_date)

    # Use the actual current date (today) to determine days passed,
    # not posting_date, to prevent manipulation by selecting a future date.
    current_date = getdate(today())
    days_passed = current_date.day

    # Get SSA details
    ssa = _get_salary_structure_assignment(doc.employee, posting_date)

    if not ssa:
        frappe.throw(
            _("No submitted Salary Structure Assignment found for employee {0}").format(doc.employee)
            + "<br><br>"
            + "لم يتم العثور على تعيين هيكل الراتب المعتمد للموظف {0}".format(doc.employee),
            title=_("Salary Structure Assignment Required") + " / تعيين هيكل الراتب مطلوب"
        )

    base = ssa.get("base")
    payment_days = ssa.get("custom_payment_days")

    if not base or base <= 0:
        frappe.throw(
            _("Salary Structure Assignment has no base salary defined for employee {0}").format(doc.employee)
            + "<br><br>"
            + "لم يتم تحديد الراتب الأساسي في تعيين هيكل الراتب للموظف {0}".format(doc.employee),
            title=_("Base Salary Required") + " / الراتب الأساسي مطلوب"
        )

    if not payment_days or payment_days <= 0:
        payment_days = DEFAULT_PAYMENT_DAYS

    # Calculate daily rate and allowed advance
    daily_rate = flt(base) / flt(payment_days)
    earned_salary = flt(days_passed) * daily_rate
    allowed_advance = flt(earned_salary * 0.60, 2)

    # Get existing advances for this month
    existing_advance = _get_existing_advance_amount_for_month(
        doc.employee,
        posting_date,
        exclude_name=doc.name if not doc.is_new() else None
    )

    # Calculate total with current advance
    total_advance = flt(existing_advance) + flt(doc.advance_amount)

    if total_advance > allowed_advance:
        remaining = flt(allowed_advance - existing_advance, 2)
        remaining = max(0, remaining)  # Don't show negative remaining

        frappe.throw(
            _("Employee Advance exceeds the allowed limit.") + "<br><br>"
            + _("Days Passed in Month: {0}").format(days_passed) + "<br>"
            + _("Allowed Advance (60%): {0}").format(frappe.format_value(allowed_advance, {"fieldtype": "Currency"})) + "<br>"
            + _("Existing Advances this Month: {0}").format(frappe.format_value(existing_advance, {"fieldtype": "Currency"})) + "<br>"
            + _("Current Advance: {0}").format(frappe.format_value(flt(doc.advance_amount), {"fieldtype": "Currency"})) + "<br>"
            + _("Total: {0}").format(frappe.format_value(total_advance, {"fieldtype": "Currency"})) + "<br>"
            + _("Remaining Allowance: {0}").format(frappe.format_value(remaining, {"fieldtype": "Currency"})) + "<br><br>"
            + "تجاوزت السلفة الحد المسموح به." + "<br><br>"
            + "الأيام المنقضية في الشهر: {0}".format(days_passed) + "<br>"
            + "السلفة المسموحة (60%): {0}".format(frappe.format_value(allowed_advance, {"fieldtype": "Currency"})) + "<br>"
            + "السلف الحالية هذا الشهر: {0}".format(frappe.format_value(existing_advance, {"fieldtype": "Currency"})) + "<br>"
            + "السلفة الحالية: {0}".format(frappe.format_value(flt(doc.advance_amount), {"fieldtype": "Currency"})) + "<br>"
            + "الإجمالي: {0}".format(frappe.format_value(total_advance, {"fieldtype": "Currency"})) + "<br>"
            + "المتبقي المسموح: {0}".format(frappe.format_value(remaining, {"fieldtype": "Currency"})),
            title=_("Advance Limit Exceeded") + " / تجاوز حد السلفة"
        )


def _validate_worker_60_percent(doc):
    """
    Validation logic for 'Worker 60%' solaf type.

    For daily-wage workers whose Salary Structure Assignment 'base' is a daily rate.
    Allowed advance = base (daily rate) × present days up to today × 60%.
    Only attendance records with attendance_date <= today() are counted to prevent
    future-dated records from inflating the eligible amount.

    Args:
        doc: Employee Advance document

    Raises:
        frappe.ValidationError: If advance exceeds allowed amount
    """
    posting_date = getdate(doc.posting_date)

    # Always use actual today to prevent manipulation via future posting_date
    current_date = getdate(today())
    month_start = get_first_day(posting_date)
    month_end = get_last_day(posting_date)

    # Cap attendance lookup at today — ignore future-dated attendance records
    attendance_end = min(month_end, current_date)

    # Count present days from month start up to (and including) today
    present_days = _get_present_days_count(doc.employee, month_start, attendance_end)

    # Get SSA — base is the daily rate for these workers
    ssa = _get_salary_structure_assignment(doc.employee, posting_date)

    if not ssa:
        frappe.throw(
            _("No submitted Salary Structure Assignment found for employee {0}").format(doc.employee)
            + "<br><br>"
            + "لم يتم العثور على تعيين هيكل الراتب المعتمد للموظف {0}".format(doc.employee),
            title=_("Salary Structure Assignment Required") + " / تعيين هيكل الراتب مطلوب"
        )

    daily_rate = ssa.get("base")

    if not daily_rate or daily_rate <= 0:
        frappe.throw(
            _("Salary Structure Assignment has no base salary defined for employee {0}").format(doc.employee)
            + "<br><br>"
            + "لم يتم تحديد الراتب الأساسي في تعيين هيكل الراتب للموظف {0}".format(doc.employee),
            title=_("Base Salary Required") + " / الراتب الأساسي مطلوب"
        )

    # Calculate total earned and 60% allowance
    total_earned = flt(daily_rate) * flt(present_days)
    allowed_advance = flt(total_earned * 0.60, 2)

    # Get existing advances for this month
    existing_advance = _get_existing_advance_amount_for_month(
        doc.employee,
        posting_date,
        exclude_name=doc.name if not doc.is_new() else None
    )

    # Calculate total with current advance
    total_advance = flt(existing_advance) + flt(doc.advance_amount)

    if total_advance > allowed_advance:
        remaining = flt(allowed_advance - existing_advance, 2)
        remaining = max(0, remaining)

        frappe.throw(
            _("Employee Advance exceeds the allowed limit.") + "<br><br>"
            + _("Total Worked Days: {0}").format(present_days) + "<br>"
            + _("Daily Rate (Base): {0}").format(frappe.format_value(daily_rate, {"fieldtype": "Currency"})) + "<br>"
            + _("Total Earned ({0} days × {1}): {2}").format(
                present_days,
                frappe.format_value(daily_rate, {"fieldtype": "Currency"}),
                frappe.format_value(total_earned, {"fieldtype": "Currency"})
            ) + "<br>"
            + _("Allowed Advance (60%): {0}").format(frappe.format_value(allowed_advance, {"fieldtype": "Currency"})) + "<br>"
            + _("Existing Advances this Month: {0}").format(frappe.format_value(existing_advance, {"fieldtype": "Currency"})) + "<br>"
            + _("Current Advance: {0}").format(frappe.format_value(flt(doc.advance_amount), {"fieldtype": "Currency"})) + "<br>"
            + _("Total: {0}").format(frappe.format_value(total_advance, {"fieldtype": "Currency"})) + "<br>"
            + _("Remaining Allowance: {0}").format(frappe.format_value(remaining, {"fieldtype": "Currency"})) + "<br><br>"
            + "تجاوزت السلفة الحد المسموح به." + "<br><br>"
            + "إجمالي أيام العمل: {0}".format(present_days) + "<br>"
            + "المعدل اليومي (الأساسي): {0}".format(frappe.format_value(daily_rate, {"fieldtype": "Currency"})) + "<br>"
            + "الإجمالي المكتسب ({0} أيام × {1}): {2}".format(
                present_days,
                frappe.format_value(daily_rate, {"fieldtype": "Currency"}),
                frappe.format_value(total_earned, {"fieldtype": "Currency"})
            ) + "<br>"
            + "السلفة المسموحة (60%): {0}".format(frappe.format_value(allowed_advance, {"fieldtype": "Currency"})) + "<br>"
            + "السلف الحالية هذا الشهر: {0}".format(frappe.format_value(existing_advance, {"fieldtype": "Currency"})) + "<br>"
            + "السلفة الحالية: {0}".format(frappe.format_value(flt(doc.advance_amount), {"fieldtype": "Currency"})) + "<br>"
            + "الإجمالي: {0}".format(frappe.format_value(total_advance, {"fieldtype": "Currency"})) + "<br>"
            + "المتبقي المسموح: {0}".format(frappe.format_value(remaining, {"fieldtype": "Currency"})),
            title=_("Advance Limit Exceeded") + " / تجاوز حد السلفة"
        )


def _validate_1500_after_7_days(doc):
    """
    Validation logic for '1500 after 7 days' solaf type.

    Args:
        doc: Employee Advance document

    Raises:
        frappe.ValidationError: If advance exceeds allowed amount based on attendance brackets
    """
    # Check per-request limit first
    if flt(doc.advance_amount) > ADVANCE_PER_7_DAYS:
        frappe.throw(
            _("Advance amount cannot exceed {0} per request.").format(
                frappe.format_value(ADVANCE_PER_7_DAYS, {"fieldtype": "Currency"})
            )
            + "<br><br>"
            + "لا يمكن أن يتجاوز مبلغ السلفة {0} لكل طلب.".format(
                frappe.format_value(ADVANCE_PER_7_DAYS, {"fieldtype": "Currency"})
            ),
            title=_("Per-Request Limit Exceeded") + " / تجاوز الحد لكل طلب"
        )

    posting_date = getdate(doc.posting_date)
    month_start = get_first_day(posting_date)
    month_end = get_last_day(posting_date)

    # Count present days for the month
    present_days = _get_present_days_count(doc.employee, month_start, month_end)

    # Calculate allowed advance based on bracket
    allowed_advance = _get_allowed_advance_for_bracket(present_days)

    # Get existing advances for this month
    existing_advance = _get_existing_advance_amount_for_month(
        doc.employee,
        posting_date,
        exclude_name=doc.name if not doc.is_new() else None
    )

    # Calculate total with current advance
    total_advance = flt(existing_advance) + flt(doc.advance_amount)

    # Check if not eligible at all (less than 7 days)
    if present_days < DAYS_PER_BRACKET:
        frappe.throw(
            _("Not eligible for advance. Minimum {0} present days required.").format(DAYS_PER_BRACKET)
            + "<br><br>"
            + _("Current Present Days: {0}").format(present_days)
            + "<br><br>"
            + "غير مؤهل للسلفة. الحد الأدنى {0} أيام حضور مطلوب.".format(DAYS_PER_BRACKET)
            + "<br><br>"
            + "أيام الحضور الحالية: {0}".format(present_days),
            title=_("Not Eligible for Advance") + " / غير مؤهل للسلفة"
        )

    if total_advance > allowed_advance:
        # Determine bracket info for error message
        bracket = present_days // DAYS_PER_BRACKET
        next_bracket_days = (bracket + 1) * DAYS_PER_BRACKET
        remaining = flt(allowed_advance - existing_advance, 2)
        remaining = max(0, remaining)

        next_bracket_info = ""
        next_bracket_info_ar = ""
        if present_days < 28:
            days_needed = next_bracket_days - present_days
            next_allowed = allowed_advance + ADVANCE_PER_7_DAYS
            next_bracket_info = _("Need {0} more present days to unlock next bracket of {1}").format(
                days_needed,
                frappe.format_value(next_allowed, {"fieldtype": "Currency"})
            )
            next_bracket_info_ar = "تحتاج {0} أيام حضور إضافية للانتقال للشريحة التالية {1}".format(
                days_needed,
                frappe.format_value(next_allowed, {"fieldtype": "Currency"})
            )

        frappe.throw(
            _("Employee Advance exceeds the allowed limit based on attendance.") + "<br><br>"
            + _("Present Days: {0}").format(present_days) + "<br>"
            + _("Attendance Bracket: {0} complete week(s)").format(bracket) + "<br>"
            + _("Allowed Advance: {0}").format(frappe.format_value(allowed_advance, {"fieldtype": "Currency"})) + "<br>"
            + _("Existing Advances this Month: {0}").format(frappe.format_value(existing_advance, {"fieldtype": "Currency"})) + "<br>"
            + _("Current Advance: {0}").format(frappe.format_value(flt(doc.advance_amount), {"fieldtype": "Currency"})) + "<br>"
            + _("Total: {0}").format(frappe.format_value(total_advance, {"fieldtype": "Currency"})) + "<br>"
            + _("Remaining Allowance: {0}").format(frappe.format_value(remaining, {"fieldtype": "Currency"})) + "<br>"
            + (next_bracket_info + "<br>" if next_bracket_info else "")
            + "<br>"
            + "تجاوزت السلفة الحد المسموح به بناءً على الحضور." + "<br><br>"
            + "أيام الحضور: {0}".format(present_days) + "<br>"
            + "شريحة الحضور: {0} أسبوع/أسابيع كاملة".format(bracket) + "<br>"
            + "السلفة المسموحة: {0}".format(frappe.format_value(allowed_advance, {"fieldtype": "Currency"})) + "<br>"
            + "السلف الحالية هذا الشهر: {0}".format(frappe.format_value(existing_advance, {"fieldtype": "Currency"})) + "<br>"
            + "السلفة الحالية: {0}".format(frappe.format_value(flt(doc.advance_amount), {"fieldtype": "Currency"})) + "<br>"
            + "الإجمالي: {0}".format(frappe.format_value(total_advance, {"fieldtype": "Currency"})) + "<br>"
            + "المتبقي المسموح: {0}".format(frappe.format_value(remaining, {"fieldtype": "Currency"})) + "<br>"
            + (next_bracket_info_ar if next_bracket_info_ar else ""),
            title=_("Advance Limit Exceeded") + " / تجاوز حد السلفة"
        )


def _get_allowed_advance_for_bracket(present_days):
    """
    Calculate allowed advance amount based on attendance bracket.

    Rules:
        - 0-6 days: 0 (not eligible)
        - 7-13 days: 1500
        - 14-20 days: 3000
        - 21-27 days: 4500
        - etc. (1500 per complete 7-day bracket)

    Args:
        present_days: Number of present days

    Returns:
        float: Maximum allowed advance amount
    """
    if present_days < DAYS_PER_BRACKET:  # 0-6 days
        return 0

    # Calculate number of complete 7-day brackets
    complete_brackets = present_days // DAYS_PER_BRACKET

    return flt(complete_brackets * ADVANCE_PER_7_DAYS, 2)
