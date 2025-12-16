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
    },
    room_number: async function(frm) {
        if (!frm.doc.room_number) return;

        console.log("Updating Room for Guest:", frm.doc.guest);

        try {
            // Update Room fields in backend
            await frappe.db.set_value("Room", frm.doc.room_number, {
                status: "Occupied",
                current_guest: frm.doc.guest || "",
                rfid_key: frm.doc.rfid_card_no || ""
            });

            frappe.show_alert({
                message: __("✅ Room updated successfully: Occupied, Guest & RFID set"),
                indicator: "green"
            });
        } catch (e) {
            console.error("Room update failed:", e);
            frappe.msgprint(__("❌ Failed to update Room: ") + e.message);
        }
    }
});
