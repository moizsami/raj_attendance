import frappe
from frappe.utils import get_first_day, get_last_day, time_diff_in_seconds
from datetime import datetime

def create_new_record(doc, method):
	if doc.status != "Present":
		return
	if not doc.in_time:
		return
	if not doc.out_time:
		return
	today_date = doc.attendance_date
	doc_name = f"{doc.employee}:{get_first_day(today_date)}"

	existed = False
	existDoc = None
	try:
		existDoc = frappe.get_doc("Employee Early Late Checkins", doc_name)
		existed = True
	except Exception as e:
		existed = False
  
	shift_doc = frappe.get_doc("Shift Type", doc.shift)
	if shift_doc.custom_pause_attendance:
		return
	shift_start_time = shift_doc.start_time
	shift_end_time   = shift_doc.end_time
	attendance_date = doc.attendance_date
	shift_start = datetime.strptime(f"{attendance_date} {shift_start_time}", "%Y-%m-%d %H:%M:%S")
	shift_end   = datetime.strptime(f"{attendance_date} {shift_end_time}", "%Y-%m-%d %H:%M:%S")
	check_in = doc.in_time
	check_out = doc.out_time
 
	if not shift_doc.custom_late_and_early_deduction_type:
		return

	if shift_doc.custom_late_and_early_deduction_type == "Deduct":
		late_seconds = time_diff_in_seconds(check_in, shift_start)
		late_minutes = 0
		if late_seconds > 0:
			late_minutes = late_seconds / 60

		early_seconds = time_diff_in_seconds(shift_end, check_out)
		early_minutes = 0
		if early_seconds > 0:
			early_minutes = early_seconds / 60
	
		if early_minutes + late_minutes <= 30:
			return

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
		
		payment_days = doc_latest_assignment.custom_payment_days or 30
		amount_per_day = doc_latest_assignment.base / payment_days
		# if doc_latest_assignment.salary_structure == "Admin Monthly 2025":
		# 	amount_per_day = doc_latest_assignment.base / 30
		# if doc_latest_assignment.salary_structure == "Workers Monthly 2025 v2":
		# 	amount_per_day = doc_latest_assignment.base / 26

		amount_to_deduct = 0
		if early_minutes + late_minutes <= 60:
			amount_to_deduct = amount_per_day / 4
		else:
			amount_to_deduct = amount_per_day

		doc_deduct_salary = frappe.new_doc("Additional Salary")
		doc_deduct_salary.employee = doc.employee
  
		salary_component_value = ""
		if shift_doc.custom_late_and_early_deduction_type == "Deduct":
			salary_component_value = "worker Deduction -Late Arrive / Early Left"
		else:
			salary_component_value = "Admin Deduction -Late Arrive / Early Left"
		doc_deduct_salary.salary_component = salary_component_value

		doc_deduct_salary.amount = amount_to_deduct
		doc_deduct_salary.payroll_date = attendance_date
		doc_deduct_salary.custom_attendance_record = doc.name
  
		doc_deduct_salary.custom_reason_of_deduct_or_earn = f"Reason of Deduction (Late Check_In or Early Check_Out):\n\n"
		doc_deduct_salary.custom_reason_of_deduct_or_earn += f"Attendance Date : {attendance_date}\n\n"
		doc_deduct_salary.custom_reason_of_deduct_or_earn += f"Came Late by {late_minutes} Minutes\n"
		doc_deduct_salary.custom_reason_of_deduct_or_earn += f"Leave out Early by {early_minutes} Minutes\n\n"
		doc_deduct_salary.custom_reason_of_deduct_or_earn += f"Shift Start Time : {shift_start}\n"
		doc_deduct_salary.custom_reason_of_deduct_or_earn += f"Check in Time : {check_in}\n\n"
		doc_deduct_salary.custom_reason_of_deduct_or_earn += f"Shift End Time : {shift_end}\n"
		doc_deduct_salary.custom_reason_of_deduct_or_earn += f"Check out Time : {check_out}\n\n"

		doc_deduct_salary.insert()
		
		return
  
	if existed:
		if existDoc.total_minutes >= 120:
			existDoc.status = "monthly limit exceeded"
			late_seconds = time_diff_in_seconds(check_in, shift_start)
			late_minutes = 0
			if late_seconds > 0:
				late_minutes = late_seconds / 60

			early_seconds = time_diff_in_seconds(shift_end, check_out)
			early_minutes = 0
			if early_seconds > 0:
				early_minutes = early_seconds / 60
   
			if early_minutes + late_minutes <= 30:
				return
  
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
			
			payment_days = doc_latest_assignment.custom_payment_days or 30
			amount_per_day = doc_latest_assignment.base / payment_days
			# if doc_latest_assignment.salary_structure == "Admin Monthly 2025":
			# 	amount_per_day = doc_latest_assignment.base / 30
			# if doc_latest_assignment.salary_structure == "Workers Monthly 2025 v2":
			# 	amount_per_day = doc_latest_assignment.base / 26

			amount_to_deduct = 0
			if early_minutes + late_minutes <= 60:
				amount_to_deduct = amount_per_day / 4
			else:
				amount_to_deduct = amount_per_day

			doc_deduct_salary = frappe.new_doc("Additional Salary")
			doc_deduct_salary.employee = doc.employee

			salary_component_value = ""
			if shift_doc.custom_late_and_early_deduction_type == "Deduct":
				salary_component_value = "worker Deduction -Late Arrive / Early Left"
			else:
				salary_component_value = "Admin Deduction -Late Arrive / Early Left"
			doc_deduct_salary.salary_component = salary_component_value

			doc_deduct_salary.amount = amount_to_deduct
			doc_deduct_salary.payroll_date = attendance_date
			doc_deduct_salary.custom_attendance_record = doc.name

			doc_deduct_salary.custom_reason_of_deduct_or_earn = f"Reason of Deduction (Late Check_In or Early Check_Out):\n\n"
			doc_deduct_salary.custom_reason_of_deduct_or_earn += f"Attendance Date : {attendance_date}\n\n"
			doc_deduct_salary.custom_reason_of_deduct_or_earn += f"Came Late by {late_minutes} Minutes\n"
			doc_deduct_salary.custom_reason_of_deduct_or_earn += f"Leave out Early by {early_minutes} Minutes\n\n"
			doc_deduct_salary.custom_reason_of_deduct_or_earn += f"Shift Start Time : {shift_start}\n"
			doc_deduct_salary.custom_reason_of_deduct_or_earn += f"Check in Time : {check_in}\n\n"
			doc_deduct_salary.custom_reason_of_deduct_or_earn += f"Shift End Time : {shift_end}\n"
			doc_deduct_salary.custom_reason_of_deduct_or_earn += f"Check out Time : {check_out}\n\n"
   
			doc_deduct_salary.insert()
			
			existDoc.save()
			return
  
		late_seconds = time_diff_in_seconds(check_in, shift_start)
		if late_seconds > 0:
			late_minutes = late_seconds / 60
			existDoc.total_minutes += int(late_minutes)
			existDoc.append("lates", {
				"date": attendance_date,
				"attendance": doc.name,
				"difference": late_minutes,
				"type": "Check In",
			})

		early_seconds = time_diff_in_seconds(shift_end, check_out)
		if early_seconds > 0:
			early_minutes = early_seconds / 60
			existDoc.total_minutes += int(early_minutes)
			existDoc.append("lates", {
				"date": attendance_date,
				"attendance": doc.name,
				"difference": early_minutes,
				"type": "Check Out",
			})
		existDoc.save()
	else:
		attendDoc = frappe.new_doc("Employee Early Late Checkins")
		attendDoc.total_minutes = 0
  
		late_seconds = time_diff_in_seconds(check_in, shift_start)
		if late_seconds > 0:
			late_minutes = late_seconds / 60
			attendDoc.total_minutes += int(late_minutes)
			attendDoc.append("lates", {
				"date": attendance_date,
				"attendance": doc.name,
				"difference": late_minutes,
				"type": "Check In",
			})

		early_seconds = time_diff_in_seconds(shift_end, check_out)
		if early_seconds > 0:
			early_minutes = early_seconds / 60
			attendDoc.total_minutes += int(early_minutes)
			attendDoc.append("lates", {
				"date": attendance_date,
				"attendance": doc.name,
				"difference": early_minutes,
				"type": "Check Out",
			})

		attendDoc.employee_id = doc.employee
		attendDoc.employee_name = doc.employee_name
		attendDoc.month_start_date = get_first_day(today_date)
		attendDoc.month_end_date   = get_last_day(today_date)
		attendDoc.insert()
	
