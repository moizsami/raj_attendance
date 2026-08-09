import frappe
from frappe.utils import getdate

DAILY_WORKER_SHIFTS = {
	"Daily Worker 12 Hours Night Shift",
	"Daily Worker 8 and Half Hours",
	"Daily Worker 12 Hours Shift",
}

@frappe.whitelist()
def run_double_salary(attendance_name):
	doc = frappe.get_doc("Attendance", attendance_name)
	double_salary(doc, method=None)
	return "ok"

def double_salary(doc, method):
	if doc.status != "Present":
		return
	# if not doc.in_time:
	# 	return
	# if not doc.out_time:
	# 	return
	if not doc.attendance_date:
		return

	shift_doc = frappe.get_doc("Shift Type", doc.shift)
	if shift_doc.custom_pause_holiday:
		return

	attendance_date = getdate(doc.attendance_date)

	if not _is_holiday_or_friday(attendance_date, doc.employee):
		return

	# Get Salary Structure Assignment
	latest_assignment = frappe.get_all(
		"Salary Structure Assignment",
		filters={
			"docstatus": 1,
			"employee": doc.employee
		},
		fields=["name", "employee", "salary_structure", "from_date", "base", "custom_payment_days", "custom_badal_wagba"],
		order_by="from_date desc",
		limit=1
	)

	if not latest_assignment:
		frappe.throw("No submitted Salary Structure Assignment found for this Employee")

	ssa = latest_assignment[0]

	shift = doc.shift or ""
 
	daily_rate = 0
	payment_days = ssa.custom_payment_days or 30
	base = ssa.base or 0
 
	if shift in DAILY_WORKER_SHIFTS:
		daily_rate = base
	else:
		daily_rate = base / payment_days

	double_daily_rate = daily_rate * 2
 
	# badal_wagba = 0
	if shift in DAILY_WORKER_SHIFTS:
		# badal_wagba = ssa.custom_badal_wagba
		double_daily_rate = base
 
	amount = round(double_daily_rate, 2)

	if amount <= 0:
		frappe.throw(f"Cannot create double pay record: calculated amount is 0 for employee {doc.employee}")

	# Determine reason label
	day_name = attendance_date.strftime("%A")
	if attendance_date.weekday() == 4:
		day_reason = "Friday"
	else:
		day_reason = "Public Holiday"

	doc_additional = frappe.new_doc("Additional Salary")
	doc_additional.employee          = doc.employee
 
	salary_component_value = ""
	if shift_doc.custom_late_and_early_deduction_type == "Deduct":
		salary_component_value = "Bonus Worker"
	else:
		salary_component_value = "admin/ Rewards and incentives"
	doc_additional.salary_component  = salary_component_value
 
	doc_additional.amount            = amount
	doc_additional.payroll_date      = attendance_date
	doc_additional.custom_attendance_record = doc.name

	doc_additional.custom_reason_of_deduct_or_earn  = f"Reason of Earning (Holiday / Friday Double Pay):\n\n"
	doc_additional.custom_reason_of_deduct_or_earn += f"Attendance Date : {attendance_date}  ({day_name} - {day_reason})\n\n"

	if shift in DAILY_WORKER_SHIFTS:
		doc_additional.custom_reason_of_deduct_or_earn += f"Shift         : {shift}\n"
		doc_additional.custom_reason_of_deduct_or_earn += f"Base Salary   : {round(base, 2)}\n"
		# doc_additional.custom_reason_of_deduct_or_earn += f"Badal & Wagba : {round(badal_wagba, 2)}\n"
		doc_additional.custom_reason_of_deduct_or_earn += f"Daily Rate (Base) : {round(amount, 2)}\n\n"
	else:
		doc_additional.custom_reason_of_deduct_or_earn += f"Shift         : {shift or 'Admin'}\n"
		doc_additional.custom_reason_of_deduct_or_earn += f"Base Salary   : {round(base, 2)}\n"
		doc_additional.custom_reason_of_deduct_or_earn += f"Payment Days  : {ssa.custom_payment_days or 30}\n"
		doc_additional.custom_reason_of_deduct_or_earn += f"Daily Rate (Base / Payment Days) : {round(daily_rate, 2)}\n\n"

	doc_additional.custom_reason_of_deduct_or_earn += f"Multiplier    : x2 (Double Pay)\n"
	doc_additional.custom_reason_of_deduct_or_earn += f"Extra Amount  : {amount}\n"

	doc_additional.insert()


# ── Helper ────────────────────────────────────────────────────────────────────

def _is_holiday_or_friday(date, employee):
	# Friday check
	if date.weekday() == 4:
		return True

	# Holiday List check from Employee record
	holiday_list_name = frappe.db.get_value("Employee", employee, "holiday_list")
	if not holiday_list_name:
		return False

	exists = frappe.db.exists(
		"Holiday",
		{
			"parent": holiday_list_name,
			"holiday_date": date,
		}
	)
	return bool(exists)