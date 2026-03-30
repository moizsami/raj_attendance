import frappe
from frappe.utils import time_diff_in_seconds
from datetime import datetime, timedelta

DAILY_WORKER_SHIFTS = {
	"Daily Worker 12 Hours Night Shift",
	"Daily Worker 8 and Half Hours",
	"Daily Worker 12 Hours Shift",
}

@frappe.whitelist()
def run_calc_bonus(attendance_name):
	doc = frappe.get_doc("Attendance", attendance_name)
	calc_bonus(doc, method=None)
	return "ok"
  
def calc_bonus(doc, method):
	if not doc.in_time:
		return
	if not doc.out_time:
		return
	shift_doc = frappe.get_doc("Shift Type", doc.shift)
	if shift_doc.custom_pause_overtime:
		return
	shift_start_time = shift_doc.start_time
	shift_end_time   = shift_doc.end_time
	attendance_date = doc.attendance_date
	shift_start = datetime.strptime(f"{attendance_date} {shift_start_time}", "%Y-%m-%d %H:%M:%S")
	shift_end   = datetime.strptime(f"{attendance_date} {shift_end_time}", "%Y-%m-%d %H:%M:%S")
	# For night shifts where end time is next day (e.g. 20:30 -> 08:30)
	if shift_end <= shift_start:
		shift_end += timedelta(days=1)
	check_out = doc.out_time

	shift_seconds = time_diff_in_seconds(shift_end, shift_start)
	shift_hours = round(shift_seconds / 3600, 1)
 
	bonus_hours = 0
	bonus_seconds = time_diff_in_seconds(check_out, shift_end)
	if bonus_seconds > 0:
		bonus_hours = bonus_seconds / 3600
		doc.custom_bonus_time = round(bonus_hours, 1)
		
	if bonus_hours >= 1 :
		# Get Salary
		#################################################
		latest_assignment = frappe.get_all(
				"Salary Structure Assignment",
				filters={
						"docstatus": 1,
						"employee": doc.employee
				},
				fields=["name", "employee", "salary_structure", "from_date"],
				order_by="from_date desc",
				limit=1
		)
		doc_latest_assignment = None
		if latest_assignment:
				latest_assignment = latest_assignment[0]
				doc_latest_assignment = frappe.get_doc("Salary Structure Assignment", latest_assignment.name)
		else:
				frappe.throw("No submitted Salary Structure Assignment found for this Employee")
		#############################################################

		

		amount_per_day = 0
		payment_days = doc_latest_assignment.custom_payment_days or 30
  
		if doc.shift in DAILY_WORKER_SHIFTS:
			return
		else:
			amount_per_day = doc_latest_assignment.base / payment_days
   


		amount_of_hour = amount_per_day / shift_hours

		nine_pm = datetime.strptime(f"{attendance_date} 21:00:00", "%Y-%m-%d %H:%M:%S")
		
		amount_of_bonus = 0
		
		bonus_before_9 = 0
		bonus_after_9 = 0

		if check_out <= nine_pm:
				bonus_before_9 = time_diff_in_seconds(check_out, shift_end)
		else:
				bonus_before_9 = max(0, time_diff_in_seconds(nine_pm, shift_end))
				bonus_after_9 = time_diff_in_seconds(check_out, nine_pm)     
				
		# More Accurate for Calc Bonus and more fair    
		# hours_before_9 = bonus_before_9 / 3600
		# hours_after_9 = bonus_after_9 / 3600
		hours_before_9 = int(bonus_before_9 / 3600)
		hours_after_9 = int(bonus_after_9 / 3600)

		amount_of_bonus = (
			(hours_before_9 * amount_of_hour * 1.35) +
			(hours_after_9 * amount_of_hour * 1.70)
		)
		amount_of_bonus = round(amount_of_bonus, 2)
  
		if amount_of_bonus <= 0:
			return

		doc_deduct_salary = frappe.new_doc("Additional Salary")
		doc_deduct_salary.employee = doc.employee
  
		salary_component_value = ""
		if shift_doc.custom_late_and_early_deduction_type == "Deduct":
			salary_component_value = "Over Time / WORKERS"
		else:
			salary_component_value = "Over Time / ADMIN"
   
		existing = frappe.db.exists("Additional Salary", {
			"custom_attendance_record": doc.name,
			"salary_component": salary_component_value,
			"docstatus": ["!=", 2]
		})
		if existing:
			return  # Already created, skip
  
		doc_deduct_salary.salary_component = salary_component_value

		doc_deduct_salary.amount = amount_of_bonus
		doc_deduct_salary.payroll_date = attendance_date
		doc_deduct_salary.custom_attendance_record = doc.name
  
		doc_deduct_salary.custom_reason_of_deduct_or_earn = f"Reason of Earning (Working Over Time):\n\n"
		doc_deduct_salary.custom_reason_of_deduct_or_earn += f"Attendance Date : {attendance_date}\n\n"
		doc_deduct_salary.custom_reason_of_deduct_or_earn += f"Over Time Hours (Before 9pm): {hours_before_9}\n"
		doc_deduct_salary.custom_reason_of_deduct_or_earn += f"Over Time Hours (After 9pm): {hours_after_9}\n"
		doc_deduct_salary.custom_reason_of_deduct_or_earn += f"All Over Time Hours: {hours_before_9 + hours_after_9}\n\n"
		doc_deduct_salary.custom_reason_of_deduct_or_earn += f"Base Salary : {round(doc_latest_assignment.base,2)}\n"
		doc_deduct_salary.custom_reason_of_deduct_or_earn += f"Payment Days : {payment_days}\n"
		doc_deduct_salary.custom_reason_of_deduct_or_earn += f"Amount of Hour: {round(amount_of_hour,2)}\n\n"
		doc_deduct_salary.custom_reason_of_deduct_or_earn += f"Bonus Before 9pm : 1.35\n"
		doc_deduct_salary.custom_reason_of_deduct_or_earn += f"Bonus After 9pm : 1.7\n\n"
		doc_deduct_salary.custom_reason_of_deduct_or_earn += f"Shift : {doc.shift}\n\n"
		doc_deduct_salary.custom_reason_of_deduct_or_earn += f"Shift Start Time : {shift_start}\n"
		doc_deduct_salary.custom_reason_of_deduct_or_earn += f"Shift End Time : {shift_end}\n"
		doc_deduct_salary.custom_reason_of_deduct_or_earn += f"Check out Time : {check_out}\n\n"
  
		doc_deduct_salary.insert()
		