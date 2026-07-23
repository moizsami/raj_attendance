frappe.ui.form.on("Payroll Entry", {
	refresh(frm) {
		if (!frm.is_new() && frm.doc.employees && frm.doc.employees.length) {
			render_incomplete_attendance(frm);
		}
	},
	after_save(frm) {
		render_incomplete_attendance(frm);
	},
});

function render_incomplete_attendance(frm) {
	if (!frm.fields_dict.custom_checkin_warnings) return;

	let employees = (frm.doc.employees || []).map((d) => d.employee);
	let $wrapper = frm.fields_dict.custom_checkin_warnings.$wrapper;

	if (!employees.length) {
		$wrapper.html("");
		return;
	}

	frappe.call({
		method: "raj_attendance.raj_attendance.incomplete_attendance.get_incomplete_attendance",
		args: {
			start_date: frm.doc.start_date,
			end_date: frm.doc.end_date,
			employees: employees,
		},
		callback(r) {
			let records = r.message || [];

			if (!records.length) {
				$wrapper.html("There is no incomplete attendance record for the selected period.");
				return;
			}

			let rows = records
				.map(
					(rec) => `
                <tr class="incomplete-attendance-row" data-name="${rec.name}" style="cursor:pointer;">
                    <td>${frappe.utils.escape_html(rec.employee)}</td>
                    <td>${frappe.utils.escape_html(rec.employee_name || "")}</td>
                    <td>${frappe.datetime.str_to_user(rec.attendance_date)}</td>
                    <td>${rec.in_time ? frappe.datetime.str_to_user(rec.in_time) : '<span class="text-muted">missing</span>'}</td>
                    <td>${rec.out_time ? frappe.datetime.str_to_user(rec.out_time) : '<span class="text-muted">missing</span>'}</td>
                    <td>${rec.status || ""}</td>
                </tr>
            `,
				)
				.join("");

			$wrapper.html(`
                <div class="alert alert-danger" style="margin-top:10px;">
                    <strong>Warning:</strong> ${records.length} Attendance record(s) have only one punch
                    (In Time or Out Time missing) for this period. Fix these before creating Salary Slips.
                </div>
                <table class="table table-bordered table-sm">
                    <thead>
                        <tr>
                            <th>Employee</th><th>Name</th><th>Date</th>
                            <th>In Time</th><th>Out Time</th><th>Status</th>
                        </tr>
                    </thead>
                    <tbody>${rows}</tbody>
                </table>
            `);

			$wrapper.find(".incomplete-attendance-row").on("click", function () {
				frappe.set_route("Form", "Attendance", $(this).data("name"));
			});
		},
	});
}
