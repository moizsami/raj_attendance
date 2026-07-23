import frappe

@frappe.whitelist()
def get_incomplete_attendance(start_date, end_date, employees):
    if isinstance(employees, str):
        employees = frappe.parse_json(employees)
    if not employees:
        return []

    records = frappe.db.get_all(
        "Attendance",
        filters={
            "employee": ["in", employees],
            "attendance_date": ["between", [start_date, end_date]],
            "docstatus": ["!=", 2],
        },
        fields=["name", "employee", "employee_name", "attendance_date",
                "in_time", "out_time", "status", "shift"],
        order_by="employee, attendance_date",
    )

    # keep only rows where exactly one of in_time/out_time is filled
    incomplete = [
        r for r in records
        if bool(r.in_time) != bool(r.out_time)
    ]

    return incomplete