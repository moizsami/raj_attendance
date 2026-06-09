import frappe

@frappe.whitelist()
def get_total_commission(from_date, to_date, sales_person):
    """Calculate total commission for a sales person within a date range.
    Reuses the report's logic to guarantee matching results."""
    total_commission = 0.0

    # 1. Fetch the commission rule linked to this sales person
    rule_name = frappe.db.get_value("Sales Person", sales_person, "custom_commission_rule")
    if not rule_name:
        frappe.throw(f"No rule found for sales_person='{sales_person}'")
        return total_commission

    # Clear document cache to avoid stale data across calls
    frappe.local.document_cache = {}
    commission_rule = frappe.get_doc("Commission Rules", rule_name)

    # 2. Own invoices — where customer_group matches the sales person
    own_invoices = frappe.db.sql("""
        SELECT si.name AS sales_invoice
        FROM `tabSales Invoice` si
        INNER JOIN `tabCustomer` c ON si.customer = c.name
        WHERE si.docstatus = 1
            AND si.customer_group = %(sp)s
            AND si.posting_date BETWEEN %(fd)s AND %(td)s
            AND (c.custom_include_in_commission = '' OR c.custom_include_in_commission IS NULL OR c.custom_include_in_commission = 'Yes')
    """, {"sp": sales_person, "fd": from_date, "td": to_date}, as_dict=True)

    for inv in own_invoices:
        items = frappe.db.sql("""
            SELECT sii.item_code, sii.item_group, sii.qty, sii.amount
            FROM `tabSales Invoice Item` sii WHERE sii.parent = %(inv)s
        """, {"inv": inv.sales_invoice}, as_dict=True)

        for item in items:
            # Try matching by item_code first, then fallback to item_group
            entry = next((r for r in commission_rule.item_commission if r.item == item.item_code), None)
            if not entry:
                entry = next((r for r in commission_rule.item_group_commission if r.item_group == item.item_group), None)
            if entry:
                total_commission += calculate_commission_for_entry(item, entry)

    # 3. Other invoices — helper commission from other sales persons' invoices
    if commission_rule.add_commission_for_other_sales_invoices and commission_rule.items_for_other_sales_invoices:
        other_invoices = frappe.db.sql("""
            SELECT si.name AS sales_invoice
            FROM `tabSales Invoice` si
            INNER JOIN `tabCustomer` c ON si.customer = c.name
            WHERE si.docstatus = 1
                AND si.customer_group != %(sp)s
                AND si.posting_date BETWEEN %(fd)s AND %(td)s
                AND (c.custom_include_in_commission = '' OR c.custom_include_in_commission IS NULL OR c.custom_include_in_commission = 'Yes')
        """, {"sp": sales_person, "fd": from_date, "td": to_date}, as_dict=True)

        for inv in other_invoices:
            items = frappe.db.sql("""
                SELECT sii.item_code, sii.item_group, sii.qty, sii.amount
                FROM `tabSales Invoice Item` sii WHERE sii.parent = %(inv)s
            """, {"inv": inv.sales_invoice}, as_dict=True)

            for item in items:
                # Match only against the helper items table
                entry = next((r for r in commission_rule.items_for_other_sales_invoices if r.item == item.item_code), None)
                if entry:
                    total_commission += calculate_commission_for_entry(item, entry)
    return total_commission



def calculate_commission_for_entry(item, commission_entry):
    commission_type = commission_entry.commission_type

    if commission_type == "Qty":
        return (item.qty or 0) * commission_entry.commission_rate_egp

    elif commission_type == "Kg" and commission_entry.get("item_group") == "الوان ميتالك":
        weight_per_unit = frappe.db.get_value("Item", item.item_code, "weight_per_unit") or 0
        if not weight_per_unit:
            return (item.qty or 0) * commission_entry.commission_rate_egp
        return weight_per_unit * (item.qty or 0) * commission_entry.commission_rate_egp

    elif commission_type == "Tax Deducted Amount":
        return calculate_tax_deducted_commission(item.amount, commission_entry.commission_percent)

    return 0


def calculate_tax_deducted_commission(amount, commission_percent):
    cal_a_two = amount * 1.14
    tax = cal_a_two * 0.15
    net_amount = cal_a_two - tax
    return net_amount * (commission_percent / 100)

def add_commission_to_salary_slip(doc, method):
    """Hook: before_validate on Salary Slip — sets the custom_total_commissions field."""
    if not (doc.start_date and doc.end_date and doc.employee):
        return
    # Find the Sales Person linked to this employee
    sales_person = frappe.db.get_value("Sales Person", {"employee": doc.employee}, "name")
    if not sales_person:
        return
    total_commission = get_total_commission(doc.start_date, doc.end_date, sales_person)
    doc.custom_total_commissions = total_commission or 0.0