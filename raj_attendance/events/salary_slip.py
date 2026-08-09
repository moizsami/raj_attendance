import frappe
from raj_customizations.raj_customizations.report.raj_sales_commission.raj_sales_commission import get_total_commission as calculate_commission

@frappe.whitelist()
def get_total_commission(from_date, to_date, sales_person):
    """Exposes the commission calculation to the client JS script and other functions"""
    return calculate_commission(from_date, to_date, sales_person)

def add_commission_to_salary_slip(doc, method):
    """Hook: before_validate on Salary Slip — sets the custom_total_commissions field and updates earnings."""

    if not (doc.start_date and doc.end_date and doc.employee):
        return

    # Find the Sales Person linked to this employee
    sales_person = frappe.db.get_value("Sales Person", {"employee": doc.employee}, "name")
    if not sales_person:
        return

    total_commission = get_total_commission(doc.start_date, doc.end_date, sales_person) or 0.0
    doc.custom_total_commissions = total_commission

    # Find existing Sales Commission row
    existing_row = None
    for row in doc.earnings:
        if row.salary_component == "Sales Commission":
            existing_row = row
            break

    if total_commission > 0:
        if existing_row:
            existing_row.amount = total_commission
        else:
            doc.append("earnings", {
                "salary_component": "Sales Commission",
                "amount": total_commission,
            })
    else:
        if existing_row:
            doc.earnings.remove(existing_row)


