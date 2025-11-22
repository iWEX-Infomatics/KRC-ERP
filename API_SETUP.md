# API Setup Documentation

## Customer Creation API

This document describes the customer creation API endpoint that has been created for the Krishna Royal Club application.

### API Endpoint

**URL:** `/api/method/krishna_royal_club.krishna_royal_club.api.create_customer`

**Method:** `POST`

**Authentication:** Guest access allowed (no authentication required)

### Request Format

```json
{
  "full_name": "John Doe",
  "email": "john.doe@example.com",
  "phone": "1234567890",
  "customer_group": "Individual",
  "customer_type": "Individual"
}
```

### Required Fields

- `full_name` (string): Customer's full name
- `email` (string): Customer's email address (must be valid email format)
- `phone` (string): Customer's phone number

### Optional Fields

- `customer_group` (string): Customer group (default: "Individual")
- `customer_type` (string): Customer type (default: "Individual")

### Response Format

**Success Response:**
```json
{
  "message": {
    "success": true,
    "message": "Customer created successfully",
    "customer": {
      "name": "john-doe",
      "customer_name": "John Doe",
      "email": "john.doe@example.com",
      "phone": "1234567890"
    }
  }
}
```

**Error Response:**
```json
{
  "message": {
    "success": false,
    "error": "Error message here"
  }
}
```

### Error Handling

The API handles the following error cases:

1. **Missing Required Fields**: Returns error if any required field is missing
2. **Invalid Email Format**: Validates email format using regex
3. **Duplicate Email**: Checks if a customer with the same email already exists
4. **Database Errors**: Handles and logs any database-related errors

### CORS Configuration

CORS is already configured in `hooks.py` to allow requests from:
- `http://localhost:3000`
- `http://127.0.0.1:3000`
- `http://localhost:5173`
- `http://127.0.0.1:5173`
- `http://localhost:5174`
- `http://127.0.0.1:5174`

### Testing the API

You can test the API using curl:

```bash
curl -X POST http://localhost:8000/api/method/krishna_royal.krishna_royal_club.api.create_customer \
  -H "Content-Type: application/json" \
  -d '{
    "full_name": "Test User",
    "email": "test@example.com",
    "phone": "1234567890"
  }'
```

### Frontend Integration

The frontend React application uses this API through the `erpApi.js` service file located at:
`krishna-royal-club/src/services/erpApi.js`

The service is already integrated into the Signup page and will automatically create a customer when a user completes the signup form.

### Configuration

Make sure your Frappe/ERPNext server is running and accessible. The frontend expects the backend URL to be configured via the `VITE_ERP_URL` environment variable (default: `http://localhost:8000`).

