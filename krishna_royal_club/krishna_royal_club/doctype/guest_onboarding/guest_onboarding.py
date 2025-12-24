import frappe
from frappe.model.document import Document
from datetime import datetime

class GuestOnboarding(Document):

    def before_save(self):
        # Validate check-in and check-out times
        if self.check_in_time and self.check_out_time:
            check_in = datetime.strptime(self.check_in_time, "%H:%M:%S")
            check_out = datetime.strptime(self.check_out_time, "%H:%M:%S")
            late_checkout = datetime.strptime("11:00:00", "%H:%M:%S")

            # If checkout after 11 AM → add 1 day
            if check_out > late_checkout:
                frappe.msgprint("Checkout after 11 AM — 1 extra day will be charged.")
        
        # Validate passport and visa requirement for non-Indian guests with Passport as ID proof
        # Only require passport/visa if nationality is not India AND ID Proof Type is Passport
        if self.nationality and self.nationality.lower() != "india" and self.nationality.lower() != "indian":
            if self.id_proof_type == "Passport":
                if not self.passport_number or not self.visa_number:
                    frappe.throw("For Non-Indian Guests, Passport and Visa details are mandatory when ID Proof Type is Passport.")

    def on_submit(self):
        # Set status to Onboarded
        self.db_set('status', 'Onboarded')
        
        # Submit linked Sales Order
        if self.reference_name:
            sales_order = frappe.get_doc("Sales Order", self.reference_name)
            if sales_order.docstatus == 0:
                sales_order.submit()
                frappe.msgprint(f"Sales Order {self.reference_name} submitted successfully")


def on_cancel_unlink_sales_order(doc, method):
    """
    Guest Onboarding cancel hone par:
    - Guest Onboarding.reference_name & reference_doctype clear
    - Sales Order.custom_guest_onboarding_id clear
    """

    if not doc.reference_name or doc.reference_doctype != "Sales Order":
        return

    try:
        so = frappe.get_doc("Sales Order", doc.reference_name)

        # Clear Sales Order side link
        so.db_set("custom_guest_onboarding_id", None, update_modified=False)

        # Clear Guest Onboarding side link
        doc.db_set("reference_name", None, update_modified=False)
        doc.db_set("reference_doctype", None, update_modified=False)

    except frappe.DoesNotExistError:
        frappe.log_error(
            f"Sales Order not found for Guest Onboarding {doc.name}",
            "Guest Onboarding Cancel Unlink Error"
        )

def before_cancel_unlink_sales_order(doc, method):
    """
    BEFORE cancel:
    - Break SO link so Guest Onboarding can be cancelled safely
    """

    if not doc.reference_name or doc.reference_doctype != "Sales Order":
        return

    try:
        so = frappe.get_doc("Sales Order", doc.reference_name)

        so.db_set("custom_guest_onboarding_id", None, update_modified=False)

        doc.db_set("reference_name", None, update_modified=False)
        doc.db_set("reference_doctype", None, update_modified=False)

    except frappe.DoesNotExistError:
        pass