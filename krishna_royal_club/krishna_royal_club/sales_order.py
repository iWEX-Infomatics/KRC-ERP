import frappe
from frappe import _


def ensure_single_sales_order(doc, method):
    """
    Prevent creation of more than one active Sales Order per customer.
    Allows updates to the same document or cancelled orders (docstatus = 2).
    """
    customer = doc.get("customer")
    if not customer:
        return

    current_name = doc.get("name")

    existing_so = frappe.db.sql(
        """
        SELECT name
        FROM `tabSales Order`
        WHERE customer = %s
          AND docstatus < 2
          AND name != %s
        LIMIT 1
        """,
        (customer, current_name or ""),
        as_dict=True
    )

    if existing_so:
        frappe.throw(
            _(
                "Customer {0} already has an active Sales Order ({1}). "
                "Only one Sales Order is allowed per customer."
            ).format(customer, existing_so[0].name)
        )

def create_project_template(doc, method):
    """
    Hooked on Sales Order on_submit.
    Creates a Project Template whose task list mirrors the submitted SO items.
    """
    if doc.docstatus != 1:
        return

    template_name = f"Template-{doc.name}"

    # Avoid creating duplicate templates if submit is triggered again (e.g. amend-resubmit)
    if frappe.db.exists("Project Template", template_name):
        frappe.msgprint(
            f"Project Template <b>{template_name}</b> already exists.",
            alert=True
        )
        return

    if not doc.items:
        frappe.msgprint("Sales Order has no items to create project tasks from.", alert=True)
        return

    template = frappe.new_doc("Project Template")
    template.__newname = template_name

    for item in doc.items:
        subject = (
            (getattr(item, "item_name", None) or None)
            or (item.description if item.description else None)
            or item.item_code
        )

        task_doc = frappe.new_doc("Task")
        task_doc.subject = subject
        task_doc.description = item.description or subject
        task_doc.insert(ignore_permissions=True)

        template.append("tasks", {
            "task": task_doc.name,
            "subject": task_doc.subject
        })

    template.insert(ignore_permissions=True)

    # frappe.msgprint(f"Project Template <b>{template.name}</b> created.")


import frappe

def on_cancel_unlink_guest_onboarding(doc, method):
    """
    Sales Order cancel hone par:
    - SO.custom_guest_onboarding_id clear
    - Guest Onboarding.reference_name & reference_doctype clear
    """

    if not doc.custom_guest_onboarding_id:
        return

    try:
        guest_onboarding = frappe.get_doc(
            "Guest Onboarding",
            doc.custom_guest_onboarding_id
        )

        # Clear Guest Onboarding side link
        guest_onboarding.db_set("reference_name", None, update_modified=False)
        guest_onboarding.db_set("reference_doctype", None, update_modified=False)

        # Clear Sales Order side link
        doc.db_set("custom_guest_onboarding_id", None, update_modified=False)

    except frappe.DoesNotExistError:
        frappe.log_error(
            f"Guest Onboarding not found for SO {doc.name}",
            "SO Cancel Unlink Error"
        )

def before_cancel_unlink_guest_onboarding(doc, method):
    """
    BEFORE cancel:
    - Break link so Frappe link validation does not block cancel
    """

    if not doc.custom_guest_onboarding_id:
        return

    try:
        guest = frappe.get_doc(
            "Guest Onboarding",
            doc.custom_guest_onboarding_id
        )

        # Break Guest Onboarding → SO link
        guest.db_set("reference_name", None, update_modified=False)
        guest.db_set("reference_doctype", None, update_modified=False)

        # Break SO → Guest Onboarding link
        doc.db_set("custom_guest_onboarding_id", None, update_modified=False)

    except frappe.DoesNotExistError:
        pass