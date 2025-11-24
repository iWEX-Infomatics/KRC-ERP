frappe.ui.form.on('Guest Onboarding', {
    check_in_time(frm) {
        if (frm.doc.check_in_time) {
            frm.set_value('status', 'Checked In');
        }
    },

    check_out_time(frm) {
        if (frm.doc.check_out_time) {
            frm.set_value('status', 'Checked Out');
        }
    }
});
