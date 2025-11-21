# -*- coding: utf-8 -*-
# Copyright (c) 2024, Krishna Royal Club and contributors
# For license information, please see license.txt

from __future__ import unicode_literals
import frappe
from frappe import _
import re
import json
from frappe.utils import now_datetime


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