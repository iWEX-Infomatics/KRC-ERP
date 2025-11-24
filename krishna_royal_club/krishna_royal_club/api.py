# -*- coding: utf-8 -*-
# Copyright (c) 2024, Krishna Royal Club and contributors
# For license information, please see license.txt

from __future__ import unicode_literals
import frappe
from frappe import _
import re
import json
import base64
from frappe.utils import now_datetime
from frappe.utils.file_manager import save_file


@frappe.whitelist(allow_guest=True)
def create_customer(**kwargs):
	"""
	API endpoint to create a LEAD and USER in ERPNext (instead of Customer)
	
	Args:
		**kwargs: Lead information
			- full_name: Lead full name (required)
			- email: Lead email address (required)
			- phone: Lead phone number (required)
			- password: User password (required)
			- customer_group: Not used for Lead (kept for compatibility)
			- customer_type: Not used for Lead (kept for compatibility)
	
	Returns:
		Dictionary with success status and lead details
	"""
	try:
		# Get data from kwargs
		data = kwargs
		
		# Log the received data for debugging
		frappe.logger().info("=== CREATE LEAD API CALLED ===")
		frappe.logger().info(f"Received data: {data}")
		
		# Validate required fields
		required_fields = ['full_name', 'email', 'phone', 'password']
		for field in required_fields:
			if not data.get(field):
				error_msg = f"{field.replace('_', ' ').title()} is required"
				frappe.logger().error(f"Validation failed: {error_msg}")
				return {
					"success": False,
					"error": error_msg
				}
		
		# Validate email format
		email = data.get('email', '').strip().lower()
		email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
		if not re.match(email_pattern, email):
			frappe.logger().error(f"Invalid email format: {email}")
			return {
				"success": False,
				"error": "Invalid email format"
			}
		
		# Validate password length
		password = data.get('password', '')
		if len(password) < 6:
			frappe.logger().error("Password too short")
			return {
				"success": False,
				"error": "Password must be at least 6 characters long"
			}
		
		# Check if lead with this email already exists
		existing_lead = frappe.db.exists("Lead", {"email_id": email})
		if existing_lead:
			frappe.logger().warning(f"Lead already exists with email: {email}")
			return {
				"success": False,
				"error": "A lead with this email already exists"
			}
		
		# Check if user with this email already exists
		existing_user = frappe.db.exists("User", email)
		if existing_user:
			frappe.logger().warning(f"User already exists with email: {email}")
			return {
				"success": False,
				"error": "A user with this email already exists"
			}
		
		# Get lead name from full_name
		lead_name = data.get('full_name', '').strip()
		phone = data.get('phone', '').strip()
		
		frappe.logger().info(f"Creating lead with name: {lead_name}")
		
		# Prepare lead data
		lead_doc = frappe.get_doc({
			"doctype": "Lead",
			"lead_name": lead_name,
			"email_id": email,
			"mobile_no": phone,
			"phone": phone,  # Primary phone field
			"status": "Lead",  # Initial status
			# "source": "Website",  # Lead source
			"territory": "All Territories",
			"company": frappe.defaults.get_user_default("Company") or frappe.db.get_single_value("Global Defaults", "default_company")
		})
		
		# Insert lead
		lead_doc.insert(ignore_permissions=True)
		frappe.logger().info(f"Lead created successfully: {lead_doc.name}")
		
		# Now create User account for login
		frappe.logger().info(f"Creating user account for: {email}")
		
		# Split full name into first and last name
		name_parts = lead_name.split()
		first_name = name_parts[0] if len(name_parts) > 0 else "User"
		last_name = " ".join(name_parts[1:]) if len(name_parts) > 1 else ""
		
		# Create User document
		user_doc = frappe.get_doc({
			"doctype": "User",
			"email": email,
			"first_name": first_name,
			"last_name": last_name,
			"enabled": 1,
			"user_type": "Website User",
			"send_welcome_email": 0,
			"mobile_no": phone,
			"new_password": password  # Set the password
		})
		
		# Insert user
		user_doc.insert(ignore_permissions=True)
		frappe.logger().info(f"User created successfully: {user_doc.name}")
		
		# Add role to user (Customer role for website users)
		try:
			user_doc.add_roles("Customer")
			frappe.logger().info("Customer role added to user")
		except Exception as role_error:
			frappe.logger().warning(f"Could not add Customer role: {str(role_error)}")
		
		# Link User to Lead (using custom field or notes)
		try:
			# Option 1: Add a note in Lead
			lead_doc.add_comment("Comment", f"User account created: {email}")
			
			# Option 2: If you have a custom field 'user' in Lead doctype, you can link it
			# frappe.db.set_value("Lead", lead_doc.name, "user", email)
			
			frappe.logger().info(f"User information added to Lead: {lead_doc.name}")
		except Exception as link_error:
			frappe.logger().warning(f"Could not link user to lead: {str(link_error)}")
		
		# Commit the transaction
		frappe.db.commit()
		
		frappe.logger().info(f"Lead and User created successfully: {lead_doc.name}")
		
		return {
			"success": True,
			"message": "Account created successfully",
			"lead": {
				"name": lead_doc.name,
				"lead_name": lead_doc.lead_name,
				"email": lead_doc.email_id,
				"phone": lead_doc.mobile_no,
				"status": lead_doc.status
			}
		}
		
	except frappe.ValidationError as e:
		frappe.db.rollback()
		error_msg = str(e)
		frappe.logger().error(f"Validation error: {error_msg}")
		return {
			"success": False,
			"error": error_msg
		}
	except Exception as e:
		frappe.db.rollback()
		error_msg = str(e)
		frappe.log_error(f"Error creating lead: {error_msg}", "Lead Creation API")
		frappe.logger().error(f"Unexpected error: {error_msg}")
		return {
			"success": False,
			"error": f"Failed to create account: {error_msg}"
		}


@frappe.whitelist(allow_guest=True)
def login_customer(email, password):
	"""
	API endpoint to authenticate a user (who may be linked to a Lead)
	
	Args:
		email: User email address (required)
		password: User password (required)
	
	Returns:
		Dictionary with success status and user/lead details
	"""
	try:
		frappe.logger().info("=== LOGIN USER API CALLED ===")
		frappe.logger().info(f"Login attempt for email: {email}")
		
		# Validate required fields
		if not email or not password:
			frappe.logger().error("Email and password are required")
			return {
				"success": False,
				"error": "Email and password are required"
			}
		
		# Normalize email
		email = email.strip().lower()
		
		# Check if User exists
		user_exists = frappe.db.exists("User", email)
		
		if not user_exists:
			frappe.logger().warning(f"No user account found for email: {email}")
			return {
				"success": False,
				"error": "Invalid email or password"
			}
		
		# Get user details to check if enabled
		user_details = frappe.db.get_value(
			"User",
			email,
			["enabled"],
			as_dict=True
		)
		
		if not user_details or not user_details.get('enabled'):
			frappe.logger().warning(f"User account is disabled: {email}")
			return {
				"success": False,
				"error": "Your account has been disabled. Please contact support."
			}
		
		# Try to authenticate using Frappe's built-in authentication
		try:
			# Login the user
			frappe.local.login_manager.authenticate(email, password)
			frappe.local.login_manager.post_login()
			
			frappe.logger().info(f"User logged in successfully: {email}")
			
			# Get full user details
			user = frappe.get_doc("User", email)
			
			# Try to get associated lead (if exists)
			lead = frappe.db.get_value(
				"Lead",
				{"email_id": email},
				["name", "lead_name", "email_id", "mobile_no", "status"],
				as_dict=True
			)
			
			response = {
				"success": True,
				"message": "Login successful",
				"user": {
					"email": user.email,
					"first_name": user.first_name,
					"last_name": user.last_name,
					"full_name": user.full_name,
					"mobile_no": user.mobile_no
				}
			}
			
			# Add lead info if exists
			if lead:
				response["lead"] = {
					"name": lead.get('name'),
					"lead_name": lead.get('lead_name'),
					"email": lead.get('email_id'),
					"phone": lead.get('mobile_no'),
					"status": lead.get('status')
				}
			
			return response
			
		except frappe.AuthenticationError as auth_error:
			frappe.logger().warning(f"Authentication failed for email: {email}")
			return {
				"success": False,
				"error": "Invalid email or password"
			}
		
	except Exception as e:
		frappe.db.rollback()
		error_msg = str(e)
		frappe.log_error(f"Error during login: {error_msg}", "User Login API")
		frappe.logger().error(f"Unexpected error during login: {error_msg}")
		return {
			"success": False,
			"error": "An error occurred during login. Please try again."
		}


@frappe.whitelist(allow_guest=True)
def forgot_password(email):
	"""
	API endpoint to initiate password reset process
	Sends password reset email to the user
	"""
	try:
		frappe.logger().info("=== FORGOT PASSWORD API CALLED ===")
		frappe.logger().info(f"Password reset requested for email: {email}")
		
		# Validate required field
		if not email:
			frappe.logger().error("Email is required")
			return {
				"success": False,
				"error": "Email is required"
			}
		
		# Normalize email
		email = email.strip().lower()
		
		# Validate email format
		email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
		if not re.match(email_pattern, email):
			frappe.logger().error(f"Invalid email format: {email}")
			return {
				"success": False,
				"error": "Invalid email format"
			}
		
		# Check if user exists
		user_exists = frappe.db.exists("User", email)
		
		if not user_exists:
			frappe.logger().warning(f"No user found with email: {email}")
			# For security, return success even if user doesn't exist
			return {
				"success": True,
				"message": "If this email is registered, you will receive a password reset link shortly."
			}
		
		# Get user document
		user = frappe.get_doc("User", email)
		
		# Check if user is enabled
		if not user.enabled:
			frappe.logger().warning(f"User account is disabled: {email}")
			return {
				"success": False,
				"error": "Your account has been disabled. Please contact support."
			}
		
		# Generate password reset key
		from frappe.utils import random_string, get_url, now_datetime, add_to_date
		
		# Generate a random reset key
		reset_key = random_string(32)
		
		# Set reset key and expiry (24 hours from now)
		user.reset_password_key = reset_key
		user.last_reset_password_key_generated_on = now_datetime()
		user.save(ignore_permissions=True)
		
		frappe.db.commit()
		
		frappe.logger().info(f"Password reset key generated for: {email}")
		frappe.logger().info(f"Reset key: {reset_key}")
		
		frontend_url = frappe.local.conf.get("frontend_url", "http://localhost:3000")

		# Create full reset link
		reset_link = f"{frontend_url}/reset-password?key={reset_key}"

		frappe.logger().info(f"Reset link: {reset_link}")

		
		# Email subject and message
		subject = "Password Reset - Krishna Royal Club"
		
		message = f"""
			<div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
				<h2 style="color: #333; border-bottom: 2px solid #4CAF50; padding-bottom: 10px;">Password Reset Request</h2>
				<p>Hello {user.first_name or 'User'},</p>
				<p>We received a request to reset your password for your Krishna Royal Club account.</p>
				<p>Click the button below to reset your password:</p>
				<div style="text-align: center; margin: 30px 0;">
					<a href="{reset_link}" 
					   style="background-color: #4CAF50; color: white; padding: 14px 40px; 
					          text-decoration: none; border-radius: 5px; display: inline-block;
					          font-weight: bold; font-size: 16px;">
						Reset Password
					</a>
				</div>
				<p>Or copy and paste this link into your browser:</p>
				<p style="word-break: break-all; background-color: #f5f5f5; padding: 10px; border-radius: 5px; color: #666;">
					{reset_link}
				</p>
				<div style="background-color: #fff3cd; border: 1px solid #ffc107; border-radius: 5px; padding: 15px; margin: 20px 0;">
					<strong>⚠️ Important:</strong>
					<ul style="margin: 10px 0; padding-left: 20px;">
						<li>This link will expire in 24 hour If you didn't request this, please ignore this email.
					</p>
					<hr style="border: none; border-top: 1px solid #eee; margin: 20px 0;">
					<p style="color: #999; font-size: 12px;">
						Krishna Royal Club<br>
						This is an automated message, please do not reply.
					</p>
				</div>
			"""
			
		frappe.sendmail(
			recipients=[email],
			subject=subject,
			message=message,
			delayed=False
		)
		
		frappe.logger().info(f"Password reset email sent to: {email}")
		
		return {
			"success": True,
			"message": "Password reset link has been sent to your email address. Please check your inbox."
		}
			
	except Exception as email_error:
		frappe.logger().error(f"Error sending reset email: {str(email_error)}")
		# Still return success to not reveal if email exists
		return {
			"success": True,
			"message": "If this email is registered, you will receive a password reset link shortly."
		}
		
	except Exception as e:
		error_msg = str(e)
		frappe.log_error(f"Error in forgot password: {error_msg}", "Forgot Password API")
		frappe.logger().error(f"Unexpected error in forgot password: {error_msg}")
		return {
			"success": False,
			"error": "An error occurred. Please try again later."
		}


@frappe.whitelist(allow_guest=True)
def reset_password(key, new_password):
    if not key or not new_password:
        return {"success": False, "error": "Key and new password are required"}

    if len(new_password) < 6:
        return {"success": False, "error": "Password must be at least 6 characters long"}

    # Find the user with matching reset key, and check expiry (if your setup stores expiry)
    user = frappe.db.get_value("User",
                        {"reset_password_key": key},
                        ["name", "reset_password_key", "last_reset_password_key_generated_on"],
                        as_dict=True)
    if not user:
        return {"success": False, "error": "Invalid or expired reset link"}

    # Optional: check if key expired (for example, older than 24 h)
    # if user.last_reset_password_key_generated_on + 1 day < now_datetime():
    #     return {"success": False, "error": "Reset link has expired"}

    # Update password
    from frappe.utils.password import update_password
    update_password(user.name, new_password)

    # Clear reset key so it can’t be reused
    frappe.get_doc("User", user.name).db_set("reset_password_key", None)

    frappe.db.commit()

    return {"success": True, "message": "Password has been reset successfully"}


@frappe.whitelist(allow_guest=True)
def test_connection():
	"""
	Test endpoint to verify API is working and accessible
	
	Returns:
		Dictionary with connection status and timestamp
	"""
	try:
		frappe.logger().info("Test connection endpoint called")
		return {
			"success": True,
			"message": "Connection successful",
			"timestamp": frappe.utils.now(),
			"server": "ERPNext"
		}
	except Exception as e:
		frappe.logger().error(f"Test connection failed: {str(e)}")
		return {
			"success": False,
			"error": str(e)
		}


@frappe.whitelist(allow_guest=True, methods=['GET', 'POST'])
def get_service_items(item_group=None):
	"""
	API endpoint to get all Item records where item_group matches the specified group
	
	Args:
		item_group: Item group name (default: "Services")
		Can be passed as query parameter (GET) or in request body (POST)
	
	Returns:
		Dictionary with success status and list of service items
	"""
	try:
		frappe.logger().info("=== GET SERVICE ITEMS API CALLED ===")
		
		# Handle both GET (query params) and POST (request body) methods
		if not item_group:
			# Try to get from request args (for GET requests)
			item_group = frappe.form_dict.get('item_group', 'Services')
		
		frappe.logger().info(f"Fetching items for item_group: {item_group}")
		
		# Get all items with the specified item_group
		items = frappe.get_all(
			"Item",
			filters={
				"item_group": item_group,
				"disabled": 0  # Only get enabled items
			},
			fields=[
				"name",
				"item_code",
				"item_name",
				"item_group",
				"description",
				"image"
			],
			order_by="item_name asc"
		)
		
		frappe.logger().info(f"Found {len(items)} items for item_group: {item_group}")
		
		# Format the response with rate information
		service_items = []
		for item in items:
			item_code = item.get("item_code")
			item_doc = frappe.get_doc("Item", item_code)
			
			# Get item's standard rate (from price list or item itself)
			rate = 0
			if item_doc.standard_rate:
				rate = item_doc.standard_rate
			else:
				# Try to get price from Price List
				price_list = frappe.db.get_value("Price List", {"selling": 1, "enabled": 1}, "name")
				if price_list:
					item_price = frappe.db.get_value(
						"Item Price",
						{"item_code": item_code, "price_list": price_list},
						"price_list_rate"
					)
					if item_price:
						rate = item_price
			
			service_items.append({
				"name": item.get("name"),
				"item_code": item_code,
				"item_name": item.get("item_name") or item_code,
				"item_group": item.get("item_group"),
				"description": item.get("description") or "",
				"image": item.get("image") or "",
				"rate": rate
			})
		
		return {
			"success": True,
			"items": service_items,
			"count": len(service_items)
		}
		
	except Exception as e:
		frappe.db.rollback()
		error_msg = str(e)
		frappe.log_error(f"Error fetching service items: {error_msg}", "Get Service Items API")
		frappe.logger().error(f"Unexpected error: {error_msg}")
		return {
			"success": False,
			"error": f"Failed to fetch service items: {error_msg}",
			"items": [],
			"count": 0
		}


@frappe.whitelist(allow_guest=True)
def create_guest_onboarding(**kwargs):
	"""
	Create Guest Onboarding document based on data submitted from the frontend
	"""
	try:
		data = {}

		# Merge kwargs and JSON body
		if kwargs:
			data.update(kwargs)
		
		if frappe.request and frappe.request.data:
			try:
				json_data = frappe.request.get_json(force=True, silent=True)
				if json_data:
					data.update(json_data)
			except Exception:
				pass

		data = frappe._dict(data)

		# Determine user email
		if frappe.session.user and frappe.session.user != "Guest":
			user_email = frappe.session.user
		else:
			user_email = data.get("user_email") or data.get("email")
		
		if not user_email:
			return {
				"success": False,
				"error": "Authentication required. Please log in to continue."
			}

		if not frappe.db.exists("User", user_email):
			return {
				"success": False,
				"error": "User not found. Please contact support."
			}

		user = frappe.get_doc("User", user_email)

		# Get or Create Customer
		customer_name = None
		
		# Try to find existing customer by email
		customer_exists = frappe.db.exists("Customer", {"email_id": user_email})
		
		if customer_exists:
			customer_name = customer_exists
			frappe.logger().info(f"Found existing customer: {customer_name}")
		else:
			# Create new Customer
			customer_name = user.full_name or f"{user.first_name} {user.last_name}".strip() or "Customer"
			
			# Generate unique customer name if duplicate exists
			base_customer_name = customer_name
			counter = 1
			while frappe.db.exists("Customer", customer_name):
				customer_name = f"{base_customer_name}-{counter}"
				counter += 1
			
			frappe.logger().info(f"Creating new customer: {customer_name}")
			
			customer_doc = frappe.get_doc({
				"doctype": "Customer",
				"customer_name": customer_name,
				"customer_type": "Individual",
				"customer_group": "Individual",
				"territory": "All Territories",
				"email_id": user_email,
				"mobile_no": user.mobile_no if hasattr(user, 'mobile_no') else None
			})
			customer_doc.insert(ignore_permissions=True)
			frappe.db.commit()
			customer_name = customer_doc.name
			frappe.logger().info(f"Customer created successfully: {customer_name}")

		# Validate required fields
		required_fields = ["from_date", "to_date", "no_of_guests", "nationality"]
		for field in required_fields:
			if not data.get(field):
				return {
					"success": False,
					"error": f"{field.replace('_', ' ').title()} is required"
				}

		# Helper to ensure list data
		def ensure_list(value):
			if not value:
				return []
			if isinstance(value, str):
				try:
					return json.loads(value)
				except Exception:
					return []
			return value

		service_type_entries = ensure_list(data.get("service_type"))
		roommate_entries = ensure_list(data.get("roommates"))

		# Normalize time values (HH:MM -> HH:MM:SS)
		def normalize_time(value):
			if not value:
				return None
			value = str(value)
			return value if len(value.split(":")) == 3 else f"{value}:00"

		onboarding_doc = frappe.get_doc({
			"doctype": "Guest Onboarding",
			"guest": customer_name,
			"from_date": data.get("from_date"),
			"to_date": data.get("to_date"),
			"no_of_guests": data.get("no_of_guests"),
			"nationality": data.get("nationality"),
			"id_proof_type": data.get("id_proof_type"),
			"id_proof_number": data.get("id_proof_number"),
			"passport_number": data.get("passport_number"),
			"visa_number": data.get("visa_number"),
			"check_in_time": None,
			"check_out_time": None
		})

		# Append service type child table
		for service in service_type_entries:
			service_code = service.get("service_type") or service.get("item_code")
			if not service_code:
				continue
			onboarding_doc.append("service_type", {
				"service_type": service_code,
				"rate": service.get("rate") or 0
			})

		# Append roommates child table
		roommate_photos = []  # Store photos to process after insert
		for roommate in roommate_entries:
			onboarding_doc.append("roommates", {
				"guest": roommate.get("guest"),
				"service_type": roommate.get("service_type"),
				"from_date": roommate.get("from_date"),
				"to_date": roommate.get("to_date"),
				"no_of_guests": roommate.get("no_of_guests"),
				"nationality": roommate.get("nationality"),
				"id_proof_type": roommate.get("id_proof_type"),
				"id_proof_number": roommate.get("id_proof_number")
			})
			# Store photo data for processing after insert
			if roommate.get("user_photo"):
				roommate_photos.append({
					"photo_data": roommate.get("user_photo"),
					"photo_filename": roommate.get("user_photo_filename"),
					"idx": len(roommate_photos) + 1
				})

		onboarding_doc.insert(ignore_permissions=True)

		# Explicitly clear check_in_time and check_out_time to ensure they remain blank
		onboarding_doc.db_set("check_in_time", None)
		onboarding_doc.db_set("check_out_time", None)

		# Handle user photo upload
		user_photo_data = data.get("user_photo")
		if user_photo_data:
			try:
				file_content = user_photo_data
				if "base64," in file_content:
					file_content = file_content.split("base64,")[-1]
				file_bytes = base64.b64decode(file_content)
				file_name = data.get("user_photo_filename") or f"user-photo-{onboarding_doc.name}.png"
				saved_file = save_file(file_name, file_bytes, onboarding_doc.doctype, onboarding_doc.name, is_private=0)
				onboarding_doc.db_set("user_photo", saved_file.file_url)
			except Exception as file_error:
				frappe.logger().warning(f"Could not save user photo: {str(file_error)}")

		# Handle roommate photos upload
		onboarding_doc.reload()
		for photo_info in roommate_photos:
			try:
				file_content = photo_info["photo_data"]
				if "base64," in file_content:
					file_content = file_content.split("base64,")[-1]
				file_bytes = base64.b64decode(file_content)
				file_name = photo_info["photo_filename"] or f"roommate-{photo_info['idx']}-photo-{onboarding_doc.name}.png"
				saved_file = save_file(file_name, file_bytes, "Roommate detail", onboarding_doc.name, is_private=0)
				# Update the roommate row's user_photo field using idx
				roommate_row = onboarding_doc.roommates[photo_info["idx"] - 1]
				roommate_row.user_photo = saved_file.file_url
				onboarding_doc.save(ignore_permissions=True)
			except Exception as file_error:
				frappe.logger().warning(f"Could not save roommate {photo_info['idx']} photo: {str(file_error)}")

		frappe.db.commit()

		return {
			"success": True,
			"message": "Guest onboarding created successfully",
			"guest_onboarding": onboarding_doc.name
		}

	except frappe.ValidationError as e:
		frappe.db.rollback()
		error_msg = str(e)
		frappe.logger().error(f"Validation error creating guest onboarding: {error_msg}")
		return {
			"success": False,
			"error": error_msg
		}
	except Exception as e:
		frappe.db.rollback()
		error_msg = str(e)
		frappe.log_error(f"Error creating guest onboarding: {error_msg}", "Create Guest Onboarding API")
		frappe.logger().error(f"Unexpected error creating guest onboarding: {error_msg}")
		return {
			"success": False,
			"error": f"Failed to create guest onboarding: {error_msg}"
		}

@frappe.whitelist(allow_guest=True)
def create_service_booking(**kwargs):
	"""
	API endpoint to create a Sales Order for service booking
	
	Args:
		**kwargs: Booking information
			- item_codes: List of item codes for the services (required) - can be single item or multiple
			- from_date: From date for the service (required)
			- to_date: To date for the service (required)
			- number_of_people: Number of people (required)
	
	Returns:
		Dictionary with success status and sales order name
	
	Note:
		- transaction_date = creation date (today)
		- delivery_date = from_date
		- qty = staying_days (difference in days between from_date and to_date)
		- Multiple items will create multiple line items in the Sales Order
	"""
	try:
		# Get data from kwargs
		data = kwargs
		
		# Log the received data for debugging
		frappe.logger().info("=== CREATE SERVICE BOOKING API CALLED ===")
		frappe.logger().info(f"Received data: {data}")
		
		# Get item_codes (support both single item_code and multiple item_codes)
		item_codes = data.get('item_codes', [])
		if not item_codes:
			# Fallback to single item_code for backward compatibility
			item_code_single = data.get('item_code')
			if item_code_single:
				item_codes = [item_code_single]
		
		# Ensure item_codes is a list
		if not isinstance(item_codes, list):
			item_codes = [item_codes] if item_codes else []
		
		# Validate required fields
		if not item_codes or len(item_codes) == 0:
			return {
				"success": False,
				"error": "At least one service item is required"
			}
		
		required_fields = ['from_date', 'to_date', 'number_of_people']
		for field in required_fields:
			if not data.get(field):
				error_msg = f"{field.replace('_', ' ').title()} is required"
				frappe.logger().error(f"Validation failed: {error_msg}")
				return {
					"success": False,
					"error": error_msg
				}
		
		frappe.logger().info(f"Creating booking for {len(item_codes)} service item(s): {item_codes}")
		
		# Validate and calculate days from date difference
		from frappe.utils import getdate, date_diff, formatdate
		
		try:
			from_date = getdate(data.get('from_date'))
			to_date = getdate(data.get('to_date'))
			
			if to_date < from_date:
				return {
					"success": False,
					"error": "To Date must be after or equal to From Date"
				}
			
			# Calculate difference in days (inclusive of both dates)
			calculated_days = date_diff(to_date, from_date) + 1
			
			# Ensure minimum 1 day
			if calculated_days < 1:
				calculated_days = 1
			
			# Format dates as DD-MM-YYYY
			from_date_formatted = formatdate(from_date, "dd-MM-yyyy")
			to_date_formatted = formatdate(to_date, "dd-MM-yyyy")
			
			frappe.logger().info(f"From Date: {from_date}, To Date: {to_date}, Calculated days: {calculated_days}")
		except Exception as e:
			frappe.logger().error(f"Invalid date value: {str(e)}")
			return {
				"success": False,
				"error": f"Invalid date format: {str(e)}"
			}
		
		# Get user email from request data or session
		# Try to get from session first (if authenticated)
		user_email = None
		if frappe.session.user and frappe.session.user != "Guest":
			user_email = frappe.session.user
			frappe.logger().info(f"Using session user: {user_email}")
		else:
			# If not in session, try to get from request data
			user_email = data.get('user_email') or data.get('email')
			if not user_email:
				frappe.logger().error("User email not provided and not authenticated")
				return {
					"success": False,
					"error": "Authentication required. Please log in to book a service."
				}
			frappe.logger().info(f"Using email from request: {user_email}")
		
		# Get User document
		if not frappe.db.exists("User", user_email):
			frappe.logger().error(f"User not found: {user_email}")
			return {
				"success": False,
				"error": "User account not found. Please contact support."
			}
		
		user = frappe.get_doc("User", user_email)
		
		# Get or Create Customer
		customer_name = None
		
		# Try to find existing customer by email
		customer_exists = frappe.db.exists("Customer", {"email_id": user_email})
		
		if customer_exists:
			customer_name = customer_exists
			frappe.logger().info(f"Found existing customer: {customer_name}")
		else:
			# Create new Customer
			customer_name = user.full_name or f"{user.first_name} {user.last_name}".strip() or "Customer"
			
			# Generate unique customer name if duplicate exists
			base_customer_name = customer_name
			counter = 1
			while frappe.db.exists("Customer", customer_name):
				customer_name = f"{base_customer_name}-{counter}"
				counter += 1
			
			frappe.logger().info(f"Creating new customer: {customer_name}")
			
			customer_doc = frappe.get_doc({
				"doctype": "Customer",
				"customer_name": customer_name,
				"customer_type": "Individual",
				"customer_group": "Individual",
				"territory": "All Territories",
				"email_id": user_email,
				"mobile_no": user.mobile_no or "",
				"phone_no": user.mobile_no or "",
				"company": frappe.defaults.get_user_default("Company") or frappe.db.get_single_value("Global Defaults", "default_company")
			})
			
			customer_doc.insert(ignore_permissions=True)
			customer_name = customer_doc.name
			frappe.logger().info(f"Customer created successfully: {customer_name}")
		
		# Create Address if address_data is provided
		address_name = None
		address_data = data.get('address_data')
		frappe.logger().info(f"=== ADDRESS DATA CHECK ===")
		frappe.logger().info(f"address_data received: {address_data}")
		frappe.logger().info(f"address_data type: {type(address_data)}")
		frappe.logger().info(f"address_data is None: {address_data is None}")
		frappe.logger().info(f"address_data is empty dict: {address_data == {}}")
		
		if address_data:
			try:
				frappe.logger().info("=== CREATING ADDRESS FROM CHECKOUT DATA ===")
				frappe.logger().info(f"Address data received: {address_data}")
				
				# Validate required address fields
				if not address_data.get('address_line1') or not address_data.get('city') or not address_data.get('state') or not address_data.get('pincode'):
					frappe.logger().warning("Incomplete address data provided, skipping address creation")
					frappe.logger().warning(f"Missing fields - address_line1: {bool(address_data.get('address_line1'))}, city: {bool(address_data.get('city'))}, state: {bool(address_data.get('state'))}, pincode: {bool(address_data.get('pincode'))}")
				else:
					# Generate address title if not provided
					address_title = address_data.get('address_title') or f"{customer_name}-{address_data.get('address_type', 'Shipping')}"
					
					frappe.logger().info(f"Creating Address with title: {address_title}")
					
					# Create Address document
					address_doc = frappe.get_doc({
						"doctype": "Address",
						"address_title": address_title,
						"address_type": address_data.get('address_type', 'Shipping'),
						"address_line1": address_data.get('address_line1', ''),
						"address_line2": address_data.get('address_line2', ''),
						"city": address_data.get('city', ''),
						"state": address_data.get('state', ''),
						"pincode": address_data.get('pincode', ''),
						"country": address_data.get('country', 'India'),
						"phone": address_data.get('phone', ''),
						"email_id": address_data.get('email_id', user_email),
						"is_primary_address": address_data.get('is_primary_address', False),
						"is_shipping_address": address_data.get('is_shipping_address', True),
						"is_billing_address": address_data.get('is_billing_address', False),
						"links": [{
							"link_doctype": "Customer",
							"link_name": customer_name
						}]
					})
					
					address_doc.insert(ignore_permissions=True)
					frappe.db.commit()  # Commit immediately after insert
					address_name = address_doc.name
					frappe.logger().info(f"✅ Address created successfully: {address_name}")
					frappe.logger().info(f"Address details - Title: {address_title}, Type: {address_data.get('address_type', 'Shipping')}, City: {address_data.get('city')}")
			except Exception as address_error:
				frappe.logger().error(f"❌ Error creating address: {str(address_error)}")
				frappe.log_error(f"Error creating address: {str(address_error)}", "Create Address API")
				# Continue with Sales Order creation even if address creation fails
		
		# Get Item details for all selected items
		sales_order_items = []
		total_amount = 0
		number_of_people = int(data.get('number_of_people', 1))
		
		for item_code in item_codes:
			if not frappe.db.exists("Item", item_code):
				frappe.logger().error(f"Item not found: {item_code}")
				return {
					"success": False,
					"error": f"Service item '{item_code}' not found"
				}
			
			item = frappe.get_doc("Item", item_code)
			
			# Get item's standard rate (from price list or item itself)
			rate = 0
			if item.standard_rate:
				rate = item.standard_rate
			else:
				# Try to get price from Price List
				price_list = frappe.db.get_value("Price List", {"selling": 1, "enabled": 1}, "name")
				if price_list:
					item_price = frappe.db.get_value(
						"Item Price",
						{"item_code": item_code, "price_list": price_list},
						"price_list_rate"
					)
					if item_price:
						rate = item_price
			
			# Calculate item total: rate * days
			item_total = rate * calculated_days
			total_amount += item_total
			
			# Format item description: "Double Room for 2 Occupants from 22-11-2025 till 24-11-2025"
			item_description = f"{item.item_name} for {number_of_people} Occupant{'s' if number_of_people > 1 else ''} from {from_date_formatted} till {to_date_formatted}"
			
			frappe.logger().info(f"Item {item_code} ({item.item_name}) - Rate: {rate}, Days: {calculated_days}, Total: {item_total}")
			frappe.logger().info(f"Item Description: {item_description}")
			
			# Get UOM from item (stock_uom) or default to "Day"
			item_uom = "Day"  # Default UOM
			if hasattr(item, 'stock_uom') and item.stock_uom:
				item_uom = item.stock_uom
			elif hasattr(item, 'uom') and item.uom:
				item_uom = item.uom
			
			# Add item to sales order items list
			sales_order_items.append({
				"item_code": item_code,
				"item_name": item.item_name,
				"description": item_description,  # Custom description with booking details
				"qty": calculated_days,  # Qty = days difference
				"rate": rate,  # Rate per day
				"uom": item_uom  # Use stock_uom if available, otherwise "Day"
			})
		
		# Create Sales Order
		frappe.logger().info(f"Creating Sales Order for customer: {customer_name}")
		
		# Prepare Sales Order data
		sales_order_data = {
			"doctype": "Sales Order",
			"customer": customer_name,
			"transaction_date": frappe.utils.today(),  # transaction_date = creation date (today)
			"delivery_date": from_date,  # delivery_date = from_date
			"company": frappe.defaults.get_user_default("Company") or frappe.db.get_single_value("Global Defaults", "default_company"),
			"items": sales_order_items,  # Multiple items
			# "po_no": f"Service Booking - {number_of_people} people, {calculated_days} day(s), {len(item_codes)} service(s)",
			# "po_date": from_date
		}
		
		# Set shipping address if address was created
		if address_name:
			sales_order_data["shipping_address_name"] = address_name
			frappe.logger().info(f"Setting shipping address in Sales Order: {address_name}")
		else:
			frappe.logger().warning("No address created, Sales Order will not have shipping address")
		
		sales_order = frappe.get_doc(sales_order_data)
		
		# Add booking details in comments
		booking_details = f"Service Booking Details:\n"
		booking_details += f"From Date: {from_date}\n"
		booking_details += f"To Date: {to_date}\n"
		booking_details += f"Number of Days: {calculated_days} day(s)\n"
		booking_details += f"Number of People: {number_of_people}\n"
		booking_details += f"Services Selected: {len(item_codes)} service(s)\n"
		for idx, item_code in enumerate(item_codes, 1):
			item_name = frappe.db.get_value("Item", item_code, "item_name") or item_code
			booking_details += f"  {idx}. {item_name} ({item_code})\n"
		booking_details += f"Total Amount: {total_amount}\n"
		
		# Insert Sales Order (in draft mode)
		sales_order.insert(ignore_permissions=True)
		frappe.logger().info(f"Sales Order created in draft mode: {sales_order.name}")
		
		# Add booking details as comment
		try:
			sales_order.add_comment("Comment", booking_details)
		except Exception as comment_error:
			frappe.logger().warning(f"Could not add comment: {str(comment_error)}")
		
		# Sales Order is created in draft mode (not submitted)
		# This allows for review and approval before finalizing
		
		# Commit the transaction
		frappe.db.commit()
		
		frappe.logger().info(f"Service booking created successfully in draft mode: {sales_order.name}")
		
		return {
			"success": True,
			"message": "Service booking created successfully",
			"sales_order": sales_order.name,
			"customer": customer_name
		}
		
	except frappe.ValidationError as e:
		frappe.db.rollback()
		error_msg = str(e)
		frappe.logger().error(f"Validation error: {error_msg}")
		return {
			"success": False,
			"error": error_msg
		}
	except Exception as e:
		frappe.db.rollback()
		error_msg = str(e)
		frappe.log_error(f"Error creating service booking: {error_msg}", "Service Booking API")
		frappe.logger().error(f"Unexpected error: {error_msg}")
		return {
			"success": False,
			"error": f"Failed to create service booking: {error_msg}"
		}


@frappe.whitelist(allow_guest=True)
def create_opportunity_from_cart(**kwargs):
	"""
	API endpoint to create an Opportunity when items are added to cart.
	Only sets the two required fields: opportunity_from and party_name.
	
	Args:
		**kwargs: Cart item information
			- user_email: Email of the logged-in user (required if not authenticated)
	
	Returns:
		Dictionary with success status and opportunity name
	"""
	try:
		data = kwargs
		frappe.logger().info("=== CREATE OPPORTUNITY FROM CART API CALLED ===")
		frappe.logger().info(f"Received data: {data}")
		
		# Get user email from request data or session
		user_email = None
		if frappe.session.user and frappe.session.user != "Guest":
			user_email = frappe.session.user
			frappe.logger().info(f"Using session user: {user_email}")
		else:
			user_email = data.get('user_email') or data.get('email')
			if not user_email:
				frappe.logger().error("User email not provided and not authenticated")
				return {
					"success": False,
					"error": "Authentication required. Please log in to add to cart."
				}
			frappe.logger().info(f"Using email from request: {user_email}")
		
		# Get User document
		if not frappe.db.exists("User", user_email):
			frappe.logger().error(f"User not found: {user_email}")
			return {
				"success": False,
				"error": "User account not found. Please contact support."
			}
		
		user = frappe.get_doc("User", user_email)
		
		# Get or find Lead for the user
		lead_name = None
		lead_list = frappe.get_all("Lead", filters={"email_id": user_email}, fields=["name", "lead_name"], limit=1)
		
		if lead_list and len(lead_list) > 0:
			lead_name = lead_list[0].name
			frappe.logger().info(f"Found existing lead: {lead_name}")
		else:
			# Create new Lead if doesn't exist
			lead_name = user.full_name or f"{user.first_name} {user.last_name}".strip() or "Customer"
			
			# Generate unique lead name if duplicate exists
			base_lead_name = lead_name
			counter = 1
			while frappe.db.exists("Lead", {"lead_name": lead_name}):
				lead_name = f"{base_lead_name}-{counter}"
				counter += 1
			
			frappe.logger().info(f"Creating new lead: {lead_name}")
			
			lead_doc = frappe.get_doc({
				"doctype": "Lead",
				"lead_name": lead_name,
				"email_id": user_email,
				"mobile_no": user.mobile_no or "",
				"phone": user.mobile_no or "",
				"status": "Lead",
				"territory": "All Territories",
				"company": frappe.defaults.get_user_default("Company") or frappe.db.get_single_value("Global Defaults", "default_company")
			})
			
			lead_doc.insert(ignore_permissions=True)
			lead_name = lead_doc.name
			frappe.logger().info(f"Lead created successfully: {lead_name}")
		
		# Create Opportunity with only the two required fields
		frappe.logger().info(f"Creating Opportunity for lead: {lead_name}")
		
		opportunity = frappe.get_doc({
			"doctype": "Opportunity",
			"opportunity_from": "Lead",
			"party_name": lead_name
		})
		
		opportunity.insert(ignore_permissions=True)
		frappe.db.commit()
		frappe.logger().info(f"Opportunity created successfully: {opportunity.name}")
		
		return {
			"success": True,
			"message": "Opportunity created successfully",
			"opportunity_name": opportunity.name
		}
		
	except frappe.ValidationError as e:
		frappe.db.rollback()
		error_msg = str(e)
		frappe.logger().error(f"Validation error creating opportunity: {error_msg}")
		return {
			"success": False,
			"error": error_msg
		}
	except Exception as e:
		frappe.db.rollback()
		error_msg = str(e)
		frappe.log_error(f"Error creating opportunity: {error_msg}", "Create Opportunity API")
		frappe.logger().error(f"Unexpected error creating opportunity: {error_msg}")
		return {
			"success": False,
			"error": f"Failed to create opportunity: {error_msg}"
		}