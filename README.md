# HealthAI Backend Microservices

This document is the official introduction to the HealthAI backend system. It describes the architecture, service responsibilities, and the end-to-end business flow in a production-oriented format.

## 1. System Goals

HealthAI Backend is built as a microservices platform to handle core capabilities of a healthcare appointment system:

- User authentication and authorization.
- Patient and doctor profile management.
- Real-time appointment booking by available slots.
- Online payments (VNPAY) per appointment.
- Real-time user notifications.

The platform is designed to prioritize:

- Business consistency across multi-service workflows.
- Fault tolerance through asynchronous broker-based communication.
- Independent scalability per component.

## 2. Architecture Overview

### 2.1 Core Components

- API Gateway: Kong.
- Business services:
  - Auth Service
  - Patient Service
  - Doctor Service
  - Appointment Service
  - Payment Service
  - Notification Service
- Data layer: PostgreSQL (database per service).
- Event bus: RabbitMQ.
- Cache/locking/idempotency: Redis.
- Observability: Jaeger + OpenTelemetry.

### 2.2 Architectural Principles

- Database-per-service: each service owns its schema and data.
- Clean Architecture: Application, Domain, Infrastructure, Presentation separation.
- Outbox Pattern: business data and integration events are persisted in the same transaction.
- Saga/Compensation: multi-step workflow control (especially Appointment + Payment).
- Event-driven integration: services communicate through domain events instead of deep synchronous coupling.

## 3. Service Responsibilities

### 3.1 Auth Service

Responsibilities:

- User registration.
- Sign in / sign out.
- Token refresh.
- Role-based authorization (PATIENT, DOCTOR, ADMIN).

Key endpoints:

- `POST /auth/register`
- `POST /auth/login`
- `POST /auth/logout`
- `POST /auth/refresh-token`
- `POST /auth/admin/register-staff`

### 3.2 Patient Service

Responsibilities:

- Initialize and update patient profiles.
- Manage baseline medical profile information.
- Expose internal profile endpoints for inter-service lookup.

### 3.3 Doctor Service

Responsibilities:

- Manage doctor profiles.
- Manage specialties.
- Manage schedules and appointment slots.

### 3.4 Appointment Service

Responsibilities:

- Create appointments.
- Manage appointment lifecycle: confirm, decline, cancel, reschedule, complete, no-show.
- Coordinate slot and payment-related business steps using saga-style orchestration.

### 3.5 Payment Service

Responsibilities:

- Create and track payment records per appointment.
- Process VNPAY callbacks (IPN/return).
- Maintain payment status transitions: awaiting, paid, failed, refunded.

### 3.6 Notification Service

Responsibilities:

- Persist notification history.
- Provide APIs to list notifications and mark as read.
- Push real-time notifications via WebSocket.

## 4. Standard Business Flow (Auth -> Appointment -> Doctor -> Payment -> Notification)

This section describes the complete customer journey from registration to completed appointment.

### 4.1 Step 1: Registration and Authentication (Auth)

1. Client calls `POST /auth/register` with email/password/role.
2. Auth Service:
	- Validates request data.
	- Hashes password.
	- Creates user record.
	- Writes registration event to outbox.
3. Client signs in via `POST /auth/login` and receives access token + refresh token.
4. Subsequent business requests pass through Kong with authenticated identity headers.

Outcome:

- User exists in the platform.
- Valid token is available for protected APIs.

### 4.2 Step 2: Patient Profile Completion (Patient)

1. After registration, Patient Service can consume the user-created event to initialize an empty profile.
2. Client calls patient profile update endpoint.
3. Patient Service:
	- Verifies ownership/permission.
	- Persists identity and baseline health information.

Outcome:

- Patient profile is ready for appointment workflows.

### 4.3 Step 3: Doctor and Slot Discovery (Doctor + Appointment)

1. Client calls Doctor Service APIs to retrieve doctors/specialties.
2. Client calls Appointment Service to fetch available slots by doctor/date.
3. Appointment Service coordinates with Doctor data/schedule context to return actual available slots.

Outcome:

- User selects a valid doctor and time slot.

### 4.4 Step 4: Appointment Creation (Appointment Saga)

1. Client calls `POST /appointments`.
2. Appointment Service executes a multi-step workflow:
	- Locks/reserves slot (prevents double booking).
	- Creates appointment with initial status.
	- Initializes payment data for Payment Service via event/contract.
	- Writes outbox event in the same transaction.
3. Outbox relay publishes event(s) to RabbitMQ.

If a failure occurs mid-flow:

- Compensation logic runs to release slot and rollback corresponding business steps.

Outcome:

- Appointment is created consistently.
- Payment workflow is initialized.

### 4.5 Step 5: Doctor Decision on Appointment (Doctor action on Appointment)

1. Doctor reviews appointment queue.
2. Doctor performs one of the supported actions:
	- Confirm.
	- Decline.
	- Other lifecycle actions supported by business rules.
3. Appointment Service updates appointment state and emits related events.

Outcome:

- Appointment state reflects doctor decision and policy.

### 4.6 Step 6: VNPAY Processing (Payment)

1. User pays through VNPAY.
2. Payment Service receives IPN/return callbacks.
3. Payment Service:
	- Verifies callback signature.
	- Reconciles transaction by appointment.
	- Updates payment status (PAID/FAILED).
	- Publishes payment event.
4. Appointment Service consumes payment events and updates appointment lifecycle per business policy.

Outcome:

- Payment and appointment states remain consistent.

### 4.7 Step 7: User Notifications (Notification)

1. Notification Service consumes critical events:
	- Appointment created/confirmed/declined/cancelled/completed/no-show.
	- Payment paid/failed/refunded.
2. Notification Service:
	- Persists notification records.
	- Pushes real-time WebSocket messages to online users.
3. Client retrieves notifications and marks them as read via API.

Outcome:

- Users receive timely updates across all key lifecycle events.

## 5. Appointment and Payment State Management

### 5.1 Appointment lifecycle (typical)

- `PENDING`
- `CONFIRMED` or `DECLINED`
- `COMPLETED` or `NO_SHOW` or `CANCELLED`

Note: actual state set depends on domain enums per service, but transitions are guarded by business rules.

### 5.2 Payment lifecycle (typical)

- `AWAITING_PAYMENT`
- `PAID` or `FAILED`
- `REFUNDED` (if refund applies)

## 6. Integration and Reliability Model

### 6.1 Outbox + RabbitMQ

- Integration events are written to outbox in the same transaction as business changes.
- Background relay publishes events to the broker.
- Consumers process events idempotently to prevent duplicate side effects.

### 6.2 Idempotency and Concurrency

- Redis supports locking and idempotency keys.
- Booking flow protects against double booking.
- Payment callback processing protects against duplicate updates.

### 6.3 Fault Tolerance

- Consumer retry policy is applied for transient failures.
- DLQ can be extended for unrecoverable events.
- Service isolation limits failure blast radius.

## 7. Local Runtime

### 7.1 Run with Docker Compose

1. Prepare environment configuration (`.env`) based on project settings.
2. Start:

```bash
docker compose up --build
```

3. Verify:

- Kong gateway is reachable.
- All services are healthy.
- RabbitMQ/PostgreSQL/Redis/Jaeger are running.

### 7.2 Suggested Quick Validation Flow

1. Register and login.
2. Update patient profile.
3. Create an appointment.
4. Trigger a payment callback test.
5. Verify notification records and WebSocket delivery.

## 8. Observability

- Tracing: Jaeger for cross-service transaction flow.
- Logging: structured service-level logs.
- Metrics/alerts can be expanded for production SLO needs.

## 9. Current Strengths

- Clear domain boundaries via microservices.
- Stable event backbone for feature evolution.
- End-to-end primary flow from Auth to Notification is closed.
- Production hardening-ready direction: rate limiting, circuit breaker, DLQ policy, contract versioning.

## 10. Recommended Next Improvements

- Standardize event schema versioning.
- Add inter-service contract tests.
- Add operations dashboards (SLO, latency, error budget).
- Formalize rollback policies and incident runbooks.

---

If needed, this documentation can be split into:

- A concise onboarding README.
- An `ARCHITECTURE.md` for deep technical design.
- A `RUNBOOK.md` for operations and incident handling.
