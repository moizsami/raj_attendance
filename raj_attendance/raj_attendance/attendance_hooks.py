import frappe
from frappe.utils import get_first_day, get_last_day, time_diff_in_seconds
from datetime import datetime, timedelta

DAILY_WORKER_SHIFTS = {
    "Daily Worker 12 Hours Night Shift",
    "Daily Worker 8 and Half Hours",
    "Daily Worker 12 Hours Shift",
}

MONTHLY_MINUTE_LIMIT = 120


def _get_salary_assignment(employee):
    """Fetch latest submitted Salary Structure Assignment or throw."""
    latest = frappe.get_all(
        "Salary Structure Assignment",
        filters={"docstatus": 1, "employee": employee},
        fields=["name", "base", "custom_payment_days"],
        order_by="from_date desc",
        limit=1,
    )
    if not latest:
        frappe.throw(f"No submitted Salary Structure Assignment found for employee {employee}")
    return latest[0]


def _calc_amount_per_day(ssa, shift_name):
    """
    Returns amount_per_day based on whether the employee is a daily worker or not.
    For daily workers: base is already the daily rate.
    For others: base / payment_days.
    """
    base = ssa.base or 0
    if shift_name in DAILY_WORKER_SHIFTS:
        return base
    payment_days = ssa.custom_payment_days or 30
    return base / payment_days if payment_days else 0


def _calc_deduction_amount(early_minutes, late_minutes, amount_per_day):
    """Quarter-day or full-day deduction based on total late/early minutes."""
    total = early_minutes + late_minutes
    if total <= 60:
        return round(amount_per_day / 4, 2)
    return round(amount_per_day, 2)


def _build_reason(attendance_date, late_minutes, early_minutes, shift_start, shift_end, check_in, check_out):
    reason  = "Reason of Deduction (Late Check_In or Early Check_Out):\n\n"
    reason += f"Attendance Date  : {attendance_date}\n\n"
    reason += f"Came Late by     : {round(late_minutes, 1)} Minutes\n"
    reason += f"Left Early by    : {round(early_minutes, 1)} Minutes\n\n"
    reason += f"Shift Start Time : {shift_start}\n"
    reason += f"Check In Time    : {check_in}\n\n"
    reason += f"Shift End Time   : {shift_end}\n"
    reason += f"Check Out Time   : {check_out}\n\n"
    return reason


def _insert_deduction(doc, shift_doc, attendance_date, late_minutes, early_minutes,
                       shift_start, shift_end, check_in, check_out):
    """Create and insert an Additional Salary deduction record."""

    # Duplicate guard
    existing = frappe.db.exists("Additional Salary", {
        "custom_attendance_record": doc.name,
        "docstatus": ["!=", 2]
    })
    if existing:
        return

    ssa = _get_salary_assignment(doc.employee)
    amount_per_day = _calc_amount_per_day(ssa, doc.shift)
    amount_to_deduct = _calc_deduction_amount(early_minutes, late_minutes, amount_per_day)

    if amount_to_deduct <= 0:
        return

    salary_component = (
        "worker Deduction -Late Arrive / Early Left"
        if shift_doc.custom_late_and_early_deduction_type == "Deduct"
        else "Admin Deduction -Late Arrive / Early Left"
    )

    rec = frappe.new_doc("Additional Salary")
    rec.employee                       = doc.employee
    rec.salary_component               = salary_component
    rec.amount                         = amount_to_deduct
    rec.payroll_date                   = attendance_date
    rec.custom_attendance_record       = doc.name
    rec.custom_reason_of_deduct_or_earn = _build_reason(
        attendance_date, late_minutes, early_minutes,
        shift_start, shift_end, check_in, check_out
    )
    rec.insert()


# ── Main Hook ─────────────────────────────────────────────────────────────────

@frappe.whitelist()
def run_create_new_record(attendance_name):
    doc = frappe.get_doc("Attendance", attendance_name)
    create_new_record(doc, method=None)
    return "ok"
  
def create_new_record(doc, method):
    # frappe.throw("Shanab123azxc")
    if doc.status != "Present":
        return
    if not doc.in_time or not doc.out_time:
        return

    # ── Shift info ────────────────────────────────────────────────────────────
    shift_doc = frappe.get_doc("Shift Type", doc.shift)
    if shift_doc.custom_pause_attendance:
        return
    if not shift_doc.custom_late_and_early_deduction_type:
        return

    attendance_date = doc.attendance_date
    shift_start = datetime.strptime(f"{attendance_date} {shift_doc.start_time}", "%Y-%m-%d %H:%M:%S")
    shift_end   = datetime.strptime(f"{attendance_date} {shift_doc.end_time}",   "%Y-%m-%d %H:%M:%S")

    # Fix: night shift crosses midnight
    if shift_end <= shift_start:
        shift_end += timedelta(days=1)

    check_in  = doc.in_time
    check_out = doc.out_time

    late_seconds  = time_diff_in_seconds(check_in, shift_start)
    early_seconds = time_diff_in_seconds(shift_end, check_out)
    late_minutes  = max(0, late_seconds / 60)
    early_minutes = max(0, early_seconds / 60)

    # ── "Deduct" type: always deduct, no monthly accumulation ─────────────────
    if shift_doc.custom_late_and_early_deduction_type == "Deduct":
        if early_minutes + late_minutes <= 30:
            return
        _insert_deduction(
            doc, shift_doc, attendance_date,
            late_minutes, early_minutes,
            shift_start, shift_end, check_in, check_out
        )
        return

    # ── "Admin" type: accumulate monthly minutes ───────────────────────────────
    today_date = doc.attendance_date
    doc_name   = f"{doc.employee}:{get_first_day(today_date)}"

    try:
        exist_doc = frappe.get_doc("Employee Early Late Checkins", doc_name)
        existed   = True
    except Exception:
        existed   = False
        exist_doc = None

    if existed:
        # Already exceeded monthly limit → deduct immediately
        if exist_doc.total_minutes >= MONTHLY_MINUTE_LIMIT:
            if early_minutes + late_minutes <= 30:
                return
            # Set status AFTER the early return check
            exist_doc.status = "monthly limit exceeded"
            _insert_deduction(
                doc, shift_doc, attendance_date,
                late_minutes, early_minutes,
                shift_start, shift_end, check_in, check_out
            )
            exist_doc.save()
            return

        # Accumulate into the monthly tracker
        if late_seconds > 0:
            exist_doc.total_minutes += round(late_minutes)
            exist_doc.append("lates", {
                "date": attendance_date,
                "attendance": doc.name,
                "difference": late_minutes,
                "type": "Check In",
            })
        if early_seconds > 0:
            exist_doc.total_minutes += round(early_minutes)
            exist_doc.append("lates", {
                "date": attendance_date,
                "attendance": doc.name,
                "difference": early_minutes,
                "type": "Check Out",
            })
        exist_doc.save()

    else:
        # Create new monthly tracker
        attend_doc = frappe.new_doc("Employee Early Late Checkins")
        attend_doc.total_minutes    = 0
        attend_doc.employee_id      = doc.employee
        attend_doc.employee_name    = doc.employee_name
        attend_doc.month_start_date = get_first_day(today_date)
        attend_doc.month_end_date   = get_last_day(today_date)

        if late_seconds > 0:
            attend_doc.total_minutes += round(late_minutes)
            attend_doc.append("lates", {
                "date": attendance_date,
                "attendance": doc.name,
                "difference": late_minutes,
                "type": "Check In",
            })
        if early_seconds > 0:
            attend_doc.total_minutes += round(early_minutes)
            attend_doc.append("lates", {
                "date": attendance_date,
                "attendance": doc.name,
                "difference": early_minutes,
                "type": "Check Out",
            })
        attend_doc.insert()