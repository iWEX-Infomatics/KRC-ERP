import frappe
from frappe.model.document import Document

class GuestOnboarding(Document):
    def on_submit(self):

        # Use the real field name
        customer = self.guest   # <-- Your field is 'guest'

        if not customer:
            frappe.throw("Guest not selected in Guest Onboarding")

        # Get latest Sales Order for this guest
        latest_so = frappe.db.get_list(
            "Sales Order",
            filters={"customer": customer},
            fields=["name", "status", "docstatus"],
            order_by="creation desc",
            limit=1
        )

        if not latest_so:
            frappe.msgprint(f"No Sales Order found for guest {customer}")
            return

        so_name = latest_so[0].name
        so_doc = frappe.get_doc("Sales Order", so_name)

        # if so_doc.docstatus == 0:
        #     so_doc.submit()
        #     frappe.msgprint(f"Sales Order {so_name} submitted automatically.")
        # else:
        #     frappe.msgprint(f"Sales Order {so_name} is already submitted.")
