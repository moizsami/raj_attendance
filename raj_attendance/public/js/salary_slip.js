frappe.ui.form.on('Salary Slip', {
    // Trigger calculation when the employee is selected or changed
    employee: function(frm) {
        frm.trigger('call_shared_calculation');
    },

    // Trigger calculation when the start date is modified
    start_date: function(frm) {
        frm.trigger('call_shared_calculation');
    },

    // Trigger calculation when the end date is modified
    end_date: function(frm) {
        frm.trigger('call_shared_calculation');
    },

    call_shared_calculation: function(frm) {
        // Ensure all required fields are filled before making the server call
        if (!frm.doc.employee || !frm.doc.start_date || !frm.doc.end_date) return;

        // First: find the Sales Person linked to this employee
        frappe.db.get_value("Sales Person", {"employee": frm.doc.employee}, "name", function(r) {
            if (!r || !r.name) return;

            frappe.call({
                method: 'raj_attendance.events.salary_slip.get_total_commission',
                args: {
                    sales_person: r.name,
                    from_date: frm.doc.start_date,
                    to_date: frm.doc.end_date,
                },
                callback: function(resp) {
                    // Check if response exists (using !== undefined to accept 0 as a valid value)
                    if (resp.message !== undefined) {
                        // Update the custom commission field in the UI
                        frm.set_value('custom_total_commissions', resp.message);
                        // Add or update the Sales Commission component in the client-side earnings table
                        let earnings = frm.doc.earnings || [];
                        let row = earnings.find(d => d.salary_component === 'Sales Commission');

                        if (flt(resp.message) > 0) {
                            // Add or update the row if commission has a value
                            if (!row) {
                                row = frm.add_child('earnings');
                                row.salary_component = 'Sales Commission';
                            }
                            row.amount = resp.message;
                        } else if (row) {
                            // Remove the row if commission is 0 or empty
                            frm.doc.earnings = frm.doc.earnings.filter(
                                d => d.salary_component !== 'Sales Commission'
                            );
                        }

                        frm.refresh_fields();
                    }
                }
            });
        });
    }
});
