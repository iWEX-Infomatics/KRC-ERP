frappe.ui.form.on("Quotation", {
    refresh(frm) {
            frm.add_custom_button("Create Membership Agreement", () => {

                frappe.model.with_doctype("Membership Agreement", () => {
                    let doc = frappe.model.get_new_doc("Membership Agreement");

                    doc.quotation = frm.doc.name;
                    doc.member_name = frm.doc.customer_name;
                    doc.agreement_date = frappe.datetime.get_today();
                    doc.membership_status = "Agreed";
                    doc.terms = frm.doc.terms;

                    if (frm.doc.items && frm.doc.items.length > 0) {
                        frm.doc.items.forEach((item) => {
                            let child = frappe.model.add_child(doc, "membership_items");
                            
                            child.item_code = item.item_code;
                            child.item_name = item.item_name;
                            child.description = item.description;
                            child.qty = item.qty;
                            child.rate = item.rate;
                            child.amount = item.amount;
                            child.uom = item.uom;
                        });
                    }

                    frappe.set_route("Form", "Membership Agreement", doc.name);
                });

            }, "Create");
            
            setTimeout(() => {
                frm.remove_custom_button("Sales Order", "Create");
            }, 100);
    }
});