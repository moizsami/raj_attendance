import frappe

def remove_late_on_cancel(doc, method):
    attendance_name = doc.name

    parents = frappe.get_all(
        "Employee Early Late Checkins",
        fields=["name"]
    )

    for parent in parents:
        parent_doc = frappe.get_doc("Employee Early Late Checkins", parent.name)

        if not parent_doc.lates:
            continue

        updated = False
        total_minutes = parent_doc.total_minutes or 0
        new_lates = []

        for row in parent_doc.lates:
            if row.attendance == attendance_name:
                total_minutes -= (row.difference or 0)
                updated = True
            else:
                new_lates.append(row)

        if updated:
            parent_doc.lates = new_lates
            parent_doc.total_minutes = max(total_minutes, 0)
            parent_doc.save(ignore_permissions=True)

    frappe.db.commit()
