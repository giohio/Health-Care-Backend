# E2E Test Setup Guide

## Prerequisites

### 1. Install Test Dependencies
```bash
pip install pytest pytest-asyncio httpx websockets python-dotenv passlib bcrypt sqlalchemy
```

### 2. Configure Environment (`.env.test`)
Update `.env.test` with your service ports and database connection:
```env
# Service URLs
AUTH_URL=http://localhost:8001
PATIENT_URL=http://localhost:8002
DOCTOR_URL=http://localhost:8003
APPOINTMENT_URL=http://localhost:8004
NOTIFICATION_URL=http://localhost:8005
PAYMENT_URL=http://localhost:8006

# Database (for seeding)
AUTH_SERVICE_DB_URL=postgresql+asyncpg://admin:admin@localhost:5432/auth_db

# Admin credentials for tests
ADMIN_EMAIL=admin@healthai.test
ADMIN_PASSWORD=Admin123!
```

### 3. Start Services
```bash
docker-compose up -d
```

### 4. Seed Admin Account
```bash
python scripts/seed_admin.py
```

Expected output:
```
🔧 Seeding admin account...
   Email: admin@healthai.test
   DB: admin@localhost/auth_db
✅ Created new admin account
💾 Admin account saved successfully!
```

### 5. Run Tests
```bash
# All E2E tests
pytest tests/e2e -v

# Single test file
pytest tests/e2e/test_01_auth.py -v

# Specific test
pytest tests/e2e/test_04_booking_auto_confirm.py::TestBookingAutoConfirm::test_full_auto_confirm_flow -v

# With real-time logging
pytest tests/e2e -v --log-cli-level=INFO

# Parallel (requires pytest-xdist)
pytest tests/e2e -v -n 4
```

## Troubleshooting

### ❌ `seed_admin.py` not found
Run from workspace root:
```bash
cd d:\microservice
python scripts/seed_admin.py
```

### ❌ Database connection error
- Check AUTH_SERVICE_DB_URL in `.env.test` is correct
- Ensure Auth service PostgreSQL is running
- Verify network connectivity: `telnet localhost 5432`

### ❌ passlib/bcrypt not installed
```bash
pip install passlib bcrypt
```

### ❌ Tests timeout waiting for events
- Increase `EVENT_PROPAGATION_TIMEOUT` in `.env.test` (default 10s)
- Check RabbitMQ is running and consumers are processing

### ❌ VNPAY payment simulation fails
- Verify `VNPAY_HASH_SECRET` in `.env.test` is correct
- Check Payment Service is running

## Database Schema

### Auth Service Schema (for reference)
```sql
CREATE TABLE users (
    id UUID PRIMARY KEY,
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    role VARCHAR(50) DEFAULT 'patient' NOT NULL,
    is_active BOOLEAN DEFAULT TRUE,
    is_profile_completed BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
```

## Environment Variables

| Variable | Purpose | Example |
|---|---|---|
| `AUTH_URL` | Auth service HTTP endpoint | `http://localhost:8001` |
| `AUTH_SERVICE_DB_URL` | Auth DB for seeding | `postgresql+asyncpg://user:pass@host/db` |
| `ADMIN_EMAIL` | Test admin email | `admin@healthai.test` |
| `ADMIN_PASSWORD` | Test admin password | `Admin123!` |
| `EVENT_PROPAGATION_TIMEOUT` | RabbitMQ event poll timeout | `10` (seconds) |
| `VNPAY_HASH_SECRET` | VNPAY sandbox secret | `<your_secret>` |

## Notes

- All test accounts are created fresh per test session
- No persistent state between test files
- Tests run against real services, not mocks
- WebSocket connections are real-time via `websockets` library
