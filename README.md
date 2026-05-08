<div align="center">
  <h1>⚙️ HealthAI Clinical OS (Backend)</h1>
  <p><i>A Robust, Event-Driven Microservices Architecture for Modern Healthcare</i></p>
</div>

<br />

> **HealthAI Backend** is the mission-critical engine powering the HealthAI Clinical OS. Designed with enterprise-grade patterns, it orchestrates complex clinical workflows, real-time appointments, and cutting-edge AI decision support while maintaining strict data consistency and high availability.

---

## 1. 🎯 System Goals & Capabilities

This platform is engineered to handle the comprehensive lifecycle of a modern healthcare facility:

- **Identity & Access:** Secure JWT-based authentication with OTP verification.
- **Entity Management:** Comprehensive Patient and Doctor profile lifecycles.
- **Resource Booking:** High-concurrency appointment slot management and queueing.
- **FinTech Integration:** Real-time VNPAY online payment processing.
- **Clinical Informatics:** Digital EMR management (Diagnoses, Medications, SOAP Notes).
- **Advanced AI Triage:** Dynamic, stateful symptom-checking conversational agents.
- **Human-in-the-Loop AI:** Automated lab result analysis with mandatory physician review pipelines.
- **Real-time Communications:** WebSocket-driven notification push system.

### 🏗 Design Philosophy

- **Resilience:** Fault tolerance via asynchronous, broker-based communication (RabbitMQ).
- **Consistency:** Saga orchestration and Outbox patterns for distributed transactions.
- **Scalability:** True database-per-service isolation within a clean architecture context.


## 2. 🏛 Architecture Overview

### 2.1 Core Components

| Component | Description |
|---|---|
| **API Gateway** | Kong — handles JWT validation, header injection, and routing |
| **Auth Service** | User registration, login, JWT tokens, OTP verification |
| **Patient Service** | Patient profiles, vitals tracking |
| **Doctor Service** | Doctor profiles, schedules, specialties, ratings |
| **Appointment Service** | Booking, slot management, queue, lifecycle transitions |
| **Payment Service** | VNPAY integration, payment lifecycle |
| **Notification Service** | In-app notifications, WebSocket real-time push |
| **Clinical Service** | Diagnoses, medications, clinical notes, vaccinations |
| **EMR Result Service** | Lab orders, lab results, HITL AI review pipeline |
| **AI Service** | Triage/symptom check, lab analysis, EMR summarization, speech, auscultation |
| **AI Worker** | Celery worker for background AI tasks (lab analysis, speech processing) |
| **Database** | PostgreSQL per service (Auth, Patient, Doctor, Appointment, Payment, Notification, Clinical, EMR Result, Triage) |
| **Event Bus** | RabbitMQ |
| **Cache** | Redis (shared instance with multiple DB indices) |
| **Vector DB** | Qdrant (Clinical guidelines knowledge base) |
| **Local LLM** | Ollama (for RAG / specialized local inference) |
| **Tracing** | Jaeger (OpenTelemetry collector) |
| **Docs Hub** | Nginx serving static API/Architecture documentation |

### 2.2 Architectural Principles

- 📦 **Database-per-service**: each service owns its schema and data.
- 🧹 **Clean Architecture**: Application, Domain, Infrastructure, Presentation separation.
- 📮 **Outbox Pattern**: business data and integration events are persisted in the same transaction.
- 🔄 **Saga/Compensation**: multi-step workflow control (especially Appointment + Payment).
- ⚡ **Event-driven integration**: services communicate through domain events instead of deep synchronous coupling.
- 👨‍⚕️ **Human-in-the-Loop (HITL)**: critical AI decisions (lab results, urgent triage) require physician validation before publication.

### 2.3 🔀 Kong Route Map

| Kong Path | Backend Service | Auth |
|---|---|---|
| `/auth` | `auth_service:8000` | Partial |
| `/patients` | `patient_service:8000` | JWT |
| `/doctors` | `doctor_service:8000` | JWT (read: anonymous) |
| `/appointments` | `appointment_service:8000` | JWT |
| `/payments` | `payment_service:8000` | JWT |
| `/notifications` | `notification_service:8000` | JWT |
| `/clinical` | `clinical_service:8000` | JWT |
| `/lab-orders` | `emr_result_service:8000` | JWT |
| `/lab-results` | `emr_result_service:8000` | JWT |
| `/ai` | `ai_service:8000` | JWT |

## 3. Service Responsibilities

### 3.1 Auth Service

- User registration (patient) with OTP email verification.
- Staff registration (doctor/admin) via admin endpoint.
- Login/logout with JWT (HttpOnly cookie) + refresh token rotation.
- Admin: system config management, user list, user status (activate/deactivate).

### 3.2 Patient Service

- Initialize and update patient profiles.
- Manage baseline medical profile information and health summaries.
- Track patient vitals (height, weight, blood pressure, heart rate, temperature) over time.
- Expose internal profile endpoints for inter-service lookup.

### 3.3 Doctor Service

- Manage doctor profiles and specialties.
- Manage precise availability (working hours, breaks, max patients) and day-offs.
- Manage custom service offerings and consultation fees.
- Handle patient ratings and reviews.
- Manage schedules and generate enhanced available slots.

### 3.4 Appointment Service

- Create appointments.
- Coordinate slot and payment-related business steps using saga-style orchestration.
- Manage appointment lifecycle: confirm, decline, cancel, reschedule, start (in progress), complete, no-show.
- Provide doctor daily queues and appointment statistics.
- Trigger automated appointment reminders (24h, 1h before start).
- Admin: aggregate statistics and chart data for dashboards.

### 3.5 Payment Service

- Create and track payment records per appointment.
- Process VNPAY callbacks (IPN/return).
- Maintain payment status transitions: awaiting, paid, failed, refunded.

### 3.6 Notification Service

- Persist notification history.
- Provide APIs to list notifications, fetch unread counts, and mark as read.
- Push real-time notifications via WebSocket.
- Process scheduled appointment reminders.
- Email notifications for user registration (OTP), appointment events, payment events.

### 3.7 Clinical Service

- Manage patient clinical records: diagnoses, medications, clinical notes, vaccinations.
- **Diagnoses**: ICD-10 codes, severity, status (active/resolved/chronic).
- **Medications**: drug name, dosage, frequency, route, duration, status (active/stopped/completed).
- **Clinical Notes**: SOAP notes, progress notes, summaries.
- Read-access control: patients can only view their own records.

### 3.8 EMR Result Service (Lab Orders & Results)

- Full HITL (Human-in-the-Loop) AI lab workflow:
  1. Doctor creates lab order → `POST /lab-orders`
  2. KTV/Doctor uploads file or manual entry → `POST /lab-results`
  3. AI pipeline processes background → status: `PENDING → AI_PROCESSING → AI_DRAFT → DOCTOR_REVIEW`
  4. Doctor reviews AI draft and publishes → status: `PUBLISHED`
- Lab order templates (SYSTEM + personal) for batch ordering.
- Lab readiness tracking per appointment.

### 3.9 AI Service

AI-powered clinical decision support across multiple tiers:

**Tier 1 — Triage (Conversational, Stateful)**
- `POST /ai/symptom-check` — Patient describes symptoms → AI asks follow-up questions → AI suggests specialty + urgency. Sessions are stored in DB.

**Tier 2 — Lab Analysis (Async, Celery)**
- `POST /ai/analyze-lab` — Triggered by EMR Result Service after file upload. AI (Gemini Vision or Groq) generates draft findings. Doctor reviews and publishes.

**Tier 2 — EMR Summary (Streaming SSE)**
- `POST /ai/summarize-emr` — Doctor requests AI summary of a patient's full clinical record. Streams as SSE.

**Tier 3 — Specialized AI Features**
- `POST /ai/lab-chat` — Patient or doctor asks questions about lab results. Plain language for patients, clinical language for doctors. Persistent session history.
- `POST /ai/clinical-assist` — Doctor asks clinical decision support questions. Differential diagnosis, treatment plans, guideline references via RAG. Persistent session history.
- `POST /ai/speech/transcribe` — Speech-to-Text using Groq Whisper.
- `POST /ai/speech/tts` — Text-to-Speech using Microsoft Edge TTS.
- `POST /ai/analyze-auscultation` — Analyze lung/heart sounds → mel-spectrogram → Gemini Vision → draft report for physician review.
- `POST /ai/suggest-lab-tests` — AI suggests lab tests based on patient symptoms (doctor only).

**Triage Sessions Management**
- `GET /ai/triage-sessions` — List sessions (patients see own; doctors see all).
- `GET /ai/triage-sessions/{id}` — Session detail with full message history.
- `POST /ai/triage-sessions/{id}/confirm` — Doctor confirms AI specialty suggestion.
- `POST /ai/triage-sessions/{id}/refer-internal` — Doctor redirects patient to Internal Medicine.

## 4. Standard Business Flow

### 4.1 Registration and Authentication

```
1. POST /auth/register              → is_email_verified: false, OTP sent to email
2. POST /auth/verify-email          → body: { email, otp } (required before login)
3. POST /auth/resend-otp             → body: { email } (2-min cooldown)
4. POST /auth/login                 → access_token + refresh_token (HttpOnly cookies)

[DOCTOR / ADMIN — registered by admin, no OTP needed]
5. POST /auth/admin/register-staff  → is_email_verified: true
6. POST /auth/login
```

### 4.2 Patient Profile Setup

```
1. PUT /patients/profile   → full_name, date_of_birth, gender, phone, address
2. PUT /patients/health    → blood_type, height, weight, allergies, chronic_conditions
3. POST /patients/{id}/vitals → height_cm, weight_kg, blood_pressure, heart_rate, temperature
```

### 4.3 Appointment Booking (Patient)

```
1.  GET  /doctors/specialties
2.  GET  /doctors/specialty/{specialty_id}
3.  GET  /doctors/{doctor_id}
4.  GET  /appointments/doctor/{doctor_id}/slots (appointment_date, specialty_id)
5.  POST /appointments/         → status: pending_payment
6.  GET  /payments/payments/{appointment_id} → get VNPAY payment_url
7.  Redirect user to VNPAY
8.  VNPAY redirect to GET /payments/vnpay/return
9.  WebSocket: appointment.confirmed | appointment.created
```

### 4.4 Doctor Queue Management

```
1. GET /appointments/doctor/{doctor_id}/queue?appointment_date=YYYY-MM-DD
   → list with lab_readiness per appointment
2. PUT /appointments/{id}/confirm  OR  PUT /appointments/{id}/decline
3. PUT /appointments/{id}/start
4. PUT /appointments/{id}/complete  OR  PUT /appointments/{id}/no-show
```

### 4.5 Clinical Records (Doctor after consultation)

```
1. POST /clinical/patients/{id}/diagnoses     → record diagnosis
2. POST /clinical/patients/{id}/medications    → prescribe medication
3. POST /clinical/patients/{id}/notes          → create clinical note (SOAP)

[Update later]
4. PATCH /clinical/patients/{id}/diagnoses/{did} → change status: resolved/chronic
5. PATCH /clinical/medications/{mid}          → stop/complete medication

[Patient — view own records]
6. GET /clinical/patients/{id}/summary         → full summary (diagnoses + meds + vitals)
7. GET /clinical/patients/{id}/diagnoses?status=active
8. GET /clinical/patients/{id}/medications?status=active
9. GET /clinical/patients/{id}/vaccinations
```

### 4.6 AI Triage Flow (Patient)

```
1. POST /ai/symptom-check
   body: { patient_id, symptoms }  (no session_id → new session)
   ← event: session_id  data: <uuid>  ← SAVE THIS
   ← event: turn_type   data: question | recommendation
   ← data: <AI text chunks...>
   ← data: [DONE]

2. Continue answering questions:
   body: { patient_id, symptoms: "<answer>", session_id: "<uuid>" }
   ← (same SSE events)

3. When turn_type = recommendation:
   → AI gave final specialty + urgency suggestion
   → Use suggested specialty to book appointment

4. View session history:
   GET /ai/triage-sessions           → list all sessions
   GET /ai/triage-sessions/{id}      → full conversation + suggestion
```

### 4.7 AI Triage — Doctor Review (Urgent/Priority cases)

```
1. GET /ai/triage-sessions?status=pending_review
   → list sessions requiring doctor review

2. GET /ai/triage-sessions/{id}
   → view full conversation + suggested_department + urgency_level

3. [Confirm AI suggestion]
   POST /ai/triage-sessions/{id}/confirm
   body: { notes: "Đồng ý chuyển Thần kinh" }
   → status: doctor_confirmed, final_department = suggested_department

   [OR redirect to Internal Medicine]
   POST /ai/triage-sessions/{id}/refer-internal
   body: { notes: "Cần đánh giá thêm" }
   → status: referred_internal, final_department: internal_medicine
```

### 4.8 Lab Orders — HITL AI Workflow (Doctor)

```
1. POST /lab-orders              → create lab order
   [OR use template]
   POST /lab-orders/from-template → batch create from template

2. Upload result file:
   POST /upload (multipart) → get file_url
   POST /lab-results (body: order_id + file_url)
   → triggers AI pipeline (status: PENDING → AI_PROCESSING → AI_DRAFT → DOCTOR_REVIEW)

   [OR manual entry — no AI]
   POST /lab-results (file_type: "manual", manual_entries: [...] )

3. Doctor reviews AI draft:
   GET /lab-results/{id}
   → ai_draft_text, ai_confidence, ai_visual_findings

4. Publish or flag for manual review:
   PATCH /lab-results/{id}/verify         → status: PUBLISHED
   PATCH /lab-results/{id}/flag-manual   → status: NEEDS_MANUAL_REVIEW

5. Patient views published results:
   GET /lab-results?patient_id={id}       → only PUBLISHED results
   GET /lab-results/{id}                  → single result detail

6. Queue readiness dashboard:
   GET /lab-orders/{appointment_id}/readiness
   GET /appointments/doctor/{doctor_id}/queue → each item has lab_readiness field
```

### 4.9 AI Lab Analysis (Internal — triggered by EMR Service)

```
[EMR Result Service fires after POST /lab-results]
POST /ai/analyze-lab
body: { result_id, patient_id, file_url, input_type, department, test_name, tabular_data?, auth_token }
→ { "status": "queued" } (immediate return)

[AI Celery Worker — background]
→ Gemini Vision (image) or Groq (tabular) processes file
→ Updates EMR Result Service via PATCH /lab-results/{id}/ai-draft
→ status: PENDING → AI_PROCESSING → AI_DRAFT → DOCTOR_REVIEW

[Frontend polls or uses WebSocket notification]
Poll GET /lab-results/{id} every 3–5s until status ≠ PENDING
```

### 4.10 AI EMR Summary (Doctor — before consultation)

```
1. POST /ai/summarize-emr
   body: { patient_id, language: "vi" }
   → SSE stream: diagnoses + medications + allergies + vitals summary
   → data: [DONE] when complete

2. Display streamed content as AI summary panel
3. Doctor reviews → proceeds with consultation
```

### 4.11 AI Lab Q&A Chat (Patient or Doctor)

```
1. POST /ai/lab-chat
   body: { question, patient_id?, department?, session_id? }
   ← event: session_id  (only on first call — SAVE THIS)
   ← data: <AI explanation...>
   ← data: [DONE]

2. Continue conversation with saved session_id:
   body: { question, session_id: "<uuid>" }
   ← (same SSE events, no session_id event)
```

### 4.12 AI Clinical Decision Support (Doctor)

```
1. POST /ai/clinical-assist
   body: { question, patient_id?, department?, session_id? }
   ← event: session_id (first call only)
   ← SSE: differential diagnosis + treatment options + guideline references
   ← data: [DONE]

2. Continue with saved session_id for follow-up questions
```

### 4.13 Notifications (all users)

```
1. GET /notifications/unread-count
2. GET /notifications/me
3. PUT /notifications/{id}/read
4. PUT /notifications/read-all
5. WebSocket: ws://host/ws/{user_id}
   → real-time push for all appointment + payment + lab events
```

## 5. Appointment and Payment State Management

### 5.1 Appointment lifecycle

```
PENDING_PAYMENT → PENDING → CONFIRMED → IN_PROGRESS → COMPLETED
                 ↓           ↓            ↓
              DECLINED    CANCELLED    NO_SHOW / CANCELLED
```

### 5.2 Payment lifecycle

```
UNPAID → PAID | FAILED | EXPIRED
         ↓
     REFUNDED
```

### 5.3 Lab Result HITL lifecycle

```
PENDING → AI_PROCESSING → AI_DRAFT → DOCTOR_REVIEW → PUBLISHED
                          ↕
                  NEEDS_MANUAL_REVIEW
```

### 5.4 Triage Session lifecycle

```
ACTIVE → AI_SUGGESTED → AUTO_CONFIRMED (routine urgency, no doctor needed)
                     → PENDING_REVIEW (priority/emergency)
                          ↓
              DOCTOR_CONFIRMED | REFERRED_INTERNAL
```

## 6. Integration and Reliability Model

### 6.1 Outbox + RabbitMQ

- Integration events are written to outbox in the same transaction as business changes.
- Background relay publishes events to the broker.
- Consumers process events idempotently to prevent duplicate side effects.

### 6.2 Idempotency and Concurrency

- Redis supports locking and idempotency keys.
- Booking flow protects against double booking.
- Payment callback processing protects against duplicate updates.
- Doctor queue cache invalidated on lab result events.

### 6.3 Fault Tolerance

- Consumer retry policy is applied for transient failures.
- Best-effort enrichment (lab_readiness, specialty enrichment) with graceful degradation.
- Service isolation limits failure blast radius.

## 7. Development Workflow

### 7.1 Branching Strategy
- `main`: Production-ready code.
- `develop`: Integration branch for new features.
- `feature/*`: Specific feature development.

### 7.2 Automated Pull Requests
The system is configured with a GitHub Action to automatically create a Pull Request from any `feature/*` branch to `develop` whenever code is pushed. This ensures a consistent review process and keeps the integration branch up to date.

---

## 8. 💻 Local Runtime

### 8.1 Prerequisites
- **Docker & Docker Compose** (v2+)
- `.env` file configured (copy from `.env.example`)
- API Keys for AI features (Groq, Gemini, Woku)

### 8.2 Run with Docker Compose

1. Prepare environment configuration (`.env`). *Make sure to never commit your actual `.env` file (it is ignored by git).*
2. Start the entire ecosystem (16+ containers):

```bash
docker compose up --build
```

3. Verify:
- Kong API Gateway is reachable at `localhost:8000`.
- All services (Auth, Patient, Doctor, etc.) are healthy.
- Infrastructure (RabbitMQ, PostgreSQL, Redis, Jaeger, Qdrant) is running.

### 8.3 Quick Validation Flow

1. Register and verify email (via OTP).
2. Complete patient profile setup.
3. Book an appointment and process VNPAY payment (sandbox).
4. Doctor confirms and starts the consultation.
5. Doctor records clinical notes and orders lab tests.
6. Doctor/KTV uploads lab results -> **AI Worker** generates draft.
7. Doctor reviews and publishes results -> Patient receives WebSocket notification.

---

## 9. 📊 Observability & Monitoring

- 🔍 **Distributed Tracing**: Jaeger is integrated via OpenTelemetry for cross-service request tracking.
- 📝 **Structured Logging**: Standardized service-level logs across all microservices.
- 📈 **Metrics Ready**: Extensible architecture for adding Prometheus/Grafana in production.

## 10. Current Strengths

- Clear domain boundaries via 9 well-scoped microservices.
- Stable event backbone for feature evolution.
- End-to-end primary flow from Auth to Notification is closed.
- AI-powered clinical decision support tier (triage, lab analysis, EMR summary, chat, speech).
- Human-in-the-Loop AI lab result workflow ensures physician oversight.
- Production hardening-ready direction: rate limiting, circuit breaker, DLQ policy, contract versioning.

## 11. Recommended Next Improvements

- Standardize event schema versioning.
- Add inter-service contract tests.
- Add operations dashboards (SLO, latency, error budget).
- Formalize rollback policies and incident runbooks.
- Expand RAG knowledge base for additional clinical departments.
