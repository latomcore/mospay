# MosPay

A comprehensive payment gateway system that provides a unified interface for multiple payment services and microservices integration.

## Features

- **Client Management**: Onboard clients with unique App IDs and API credentials
- **Service Management**: Configure and manage different payment services
- **Microservice Integration**: Seamless integration with external microservices
- **JWT Authentication**: Secure API access with JWT tokens
- **Admin Portal**: Beautiful admin interface built with SB Admin 2 template
- **PostgreSQL Functions**: Dynamic function creation and execution
- **Transaction Tracking**: Complete transaction history and logging
- **API Logging**: Comprehensive API call logging and monitoring

## System Architecture

### Core Components

1. **Flask Application**: Main web application with RESTful API
2. **PostgreSQL Database**: Data storage with dynamic function execution
3. **Admin Portal**: Web-based administration interface
4. **Payment Processor**: Handles payment requests and microservice calls
5. **Authentication System**: JWT-based authentication for clients and admins

### Data Flow

1. Client authenticates using Basic Auth + App ID header
2. System validates credentials and returns JWT token
3. Client sends payment request with required fields (f000-f010)
4. System calls appropriate PostgreSQL function
5. Function returns service call details
6. System calls external microservice
7. Response is processed through response function
8. Final result is returned to client

## Installation

### Prerequisites

- Python 3.8+
- PostgreSQL 12+
- pip

### Setup

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd mospay
   ```

2. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

3. **Configure database**
   - Update `config.py` with your database credentials
   - Ensure PostgreSQL is running and accessible

4. **Run the application**
   ```bash
   python app.py
   ```

5. **Access the admin portal**
   - Navigate to `http://localhost:5000`
   - Default credentials: `admin` / `admin123`

## API Documentation

### Authentication

#### Get JWT Token
```http
POST /api/v1/auth/token
Authorization: Basic <base64(username:password)>
App-ID: <app_id>
```

#### Process Payment
```http
POST /api/v1/payment/process
Authorization: Basic <base64(username:password)>
App-ID: <app_id>
Content-Type: application/json

{
  "f000": "microservicename",
  "f001": "service",
  "f002": "microserviceroute",
  "f003": "appid",
  "f004": "amount",
  "f005": "mobileNumber",
  "f006": "username",
  "f007": "encrypted(password)",
  "f008": "pwd",
  "f009": "deviceid",
  "f010": "Uniqueid"
}
```

### Required Fields

| Field | Description | Example |
|-------|-------------|---------|
| f000 | Microservice name | "mtnmomorwa" |
| f001 | Service name | "collection" |
| f002 | Service route | "payment" |
| f003 | App ID | "app_ABC123" |
| f004 | Amount | "1000.00" |
| f005 | Mobile number | "+250123456789" |
| f006 | Username | "customer123" |
| f007 | Encrypted password | "encrypted_string" |
| f008 | Password | "password123" |
| f009 | Device ID | "device_abc123" |
| f010 | Unique ID | "txn_xyz789" |

## Database Schema

### Tables

- **users**: Admin users and their roles
- **clients**: Client information and API credentials
- **services**: Available payment services
- **service_fields**: Service field definitions
- **client_services**: Client-service assignments
- **transactions**: Payment transaction records
- **api_logs**: API call logging

### PostgreSQL Functions

The system automatically creates PostgreSQL functions with the naming convention:
- `{app_id}_{microservice_name}_{microservice_route}`
- `RESPONSE_{app_id}_{microservice_name}_{microservice_route}`

Example:
- `akaliza_mtnmomorwa_collection`
- `RESPONSE_akaliza_mtnmomorwa_collection`

## Admin Portal

### Dashboard
- Overview statistics
- Recent transactions
- Recent API calls

### Client Management
- Create new clients
- Generate API credentials
- Assign services to clients
- View client details

### Service Management
- Configure payment services
- Define service fields
- Set microservice URLs

### Monitoring
- Transaction history
- API call logs
- System statistics

## Configuration

### Environment Variables

```bash
SECRET_KEY=your-secret-key
JWT_SECRET_KEY=your-jwt-secret
DATABASE_URL=postgresql://user:password@host:port/db
```

### Database Configuration

Update `config.py` with your PostgreSQL connection details:

```python
SQLALCHEMY_DATABASE_URI = 'postgresql://username:password@host:port/database'
```

## Security Features

- **JWT Authentication**: Secure token-based authentication
- **Password Hashing**: Bcrypt password hashing
- **API Key Management**: Unique App IDs for each client
- **Request Validation**: Comprehensive input validation
- **API Logging**: Complete audit trail

## Microservice Integration

The system is designed to work with microservices running in Docker containers. Each service should:

1. Accept HTTP POST requests
2. Return JSON responses
3. Be accessible via the configured service URL
4. Handle the service payload format

## Development

### Project Structure

```
mospay/
├── app.py                 # Main application
├── config.py             # Configuration
├── models.py             # Database models
├── auth.py               # Authentication utilities
├── payment_processor.py  # Payment processing logic
├── api_routes.py         # API endpoints
├── admin_routes.py       # Admin portal routes
├── auth_routes.py        # Authentication routes
├── requirements.txt      # Python dependencies
├── templates/            # HTML templates
│   ├── admin/           # Admin portal templates
│   └── auth/            # Authentication templates
└── static/              # Static assets
```

### Adding New Services

1. Create service through admin portal
2. Define service fields
3. Assign to clients
4. System automatically creates PostgreSQL functions

### Customizing PostgreSQL Functions

You can customize the default function templates in `payment_processor.py` or create custom functions directly in PostgreSQL.

## Deployment

### Production Considerations

1. **Environment Variables**: Set proper SECRET_KEY and JWT_SECRET_KEY
2. **Database**: Use production PostgreSQL instance
3. **HTTPS**: Enable SSL/TLS for production
4. **Monitoring**: Set up logging and monitoring
5. **Backup**: Regular database backups

### Docker Deployment

```dockerfile
FROM python:3.9-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
EXPOSE 5000
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "app:app"]
```

## Support

For support and questions:
- Check the documentation
- Review the code comments
- Contact the development team

## License

This project is proprietary software. All rights reserved.

## Version

Current Version: 1.0.0
