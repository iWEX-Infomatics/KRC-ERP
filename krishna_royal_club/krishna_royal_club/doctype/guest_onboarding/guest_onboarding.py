import frappe
from frappe.model.document import Document

class GuestOnboarding(Document):

    def on_submit(self):
        self.create_sales_order()

    def create_sales_order(self):
        # Create Sales Order
        so = frappe.new_doc("Sales Order")
        so.customer = self.guest
        so.delivery_date = self.from_date
        so.transaction_date = frappe.utils.today()

        # Child table loop
        for row in self.service_type:
            item_code = row.service_type
            rate = row.rate

            # UOM get from Item master
            uom = frappe.db.get_value("Item", item_code, "stock_uom")

            so.append("items", {
                "item_code": item_code,
                "qty": 1,
                "rate": rate,
                "uom": uom
            })

        # Save and Submit SO
        so.insert(ignore_permissions=True)

        frappe.msgprint(f"Sales Order <b>{so.name}</b> created successfully.")
