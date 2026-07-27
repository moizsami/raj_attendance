import frappe

def calculate_ignored_badal_wagba(doc, method):
    if not (doc.employee and doc.start_date and doc.end_date):
        return

    count = frappe.db.count("Attendance", {
        "employee": doc.employee,
        "attendance_date": ["between", [doc.start_date, doc.end_date]],
        "docstatus": 1,
        "custom_ignore_badal_wagba": 1
    })

    doc.custom_ignored_badal_wagba_days = count