# Shared Libraries — HealthAI Backend

Tập hợp 4 thư viện shared cho tất cả services trong HealthAI backend system.

## 📦 Architecture

```
shared/
├── healthai-db/              # SQLAlchemy base + outbox pattern
├── healthai-cache/           # Redis utilities (lock, PER, idempotency)
├── healthai-events/          # RabbitMQ publisher + relay + consumer
└── healthai-common/          # Business logic utilities
```

## 🚀 Quick Start

### Setup

Mỗi service cần add dependencies vào `pyproject.toml`:

```toml
[tool.poetry.dependencies]
healthai-db = {path = "../../shared/healthai-db"}
healthai-cache = {path = "../../shared/healthai-cache"}
healthai-events = {path = "../../shared/healthai-events"}
healthai-common = {path = "../../shared/healthai-common"}
```

### Initialization

```python
# main.py
from healthai_db import create_session_factory, OutboxWriter
from healthai_cache import CacheClient
from healthai_events import RabbitMQPublisher, OutboxRelay

# Database
session_factory = create_session_factory(
    os.getenv("DATABASE_URL"),
    echo=False
)

# Cache
app.state.cache = CacheClient.from_url(
    os.getenv("REDIS_URL")
)

# Events
app.state.publisher = await RabbitMQPublisher.connect(
    os.getenv("RABBITMQ_URL")
)

# Outbox relay (background task)
relay = OutboxRelay(session_factory, app.state.publisher)
asyncio.create_task(relay.run())
```

## 📚 Library Reference

### 1. healthai-db

**Purpose**: Shared database layer với SQLAlchemy ORM base classes và outbox pattern.

**Components**:
- `Base` — DeclarativeBase cho tất cả models
- `UUIDMixin` — Auto-generated UUID7 primary keys
- `TimestampMixin` — created_at/updated_at auto-management
- `SoftDeleteMixin` — Logical delete (is_deleted flag)
- `OutboxEvent` — Transactional outbox table
- `OutboxWriter` — Helper để write events atomically
- `create_session_factory()` — AsyncSession factory
- `get_session()` — Context manager với auto-rollback

**Example Model**:

```python
from healthai_db import Base, UUIDMixin, TimestampMixin

class User(Base, UUIDMixin, TimestampMixin):
    __tablename__ = 'users'
    
    email: Mapped[str] = mapped_column(String(255), unique=True)
    is_active: Mapped[bool] = mapped_column(default=True)
```

**Example Outbox Usage**:

```python
async with session.begin():
    # Create entity
    user = User(email='user@example.com')
    session.add(user)
    await session.flush()
    
    # Write outbox event atomically
    await OutboxWriter.write(
        session,
        aggregate_id=user.id,
        aggregate_type='user_events',
        event_type='user.created',
        payload={'user_id': str(user.id), 'email': user.email}
    )
# Commit atomic: entity + outbox
```

---

### 2. healthai-cache

**Purpose**: Redis wrapper với distributed locks, cache stampede protection, idempotency.

**Components**:
- `DistributedLock` — Lua-based distributed locks
- `StampedeProtectedCache` — PER + single-flight pattern
- `IdempotencyStore` — Reject duplicate requests
- `CacheClient` — Facade tổng hợp

**Distributed Lock Example**:

```python
cache = CacheClient.from_url("redis://localhost:6379")

# Manual
token = await cache.lock.acquire("slot:doc:2025-03-19:10:00", ttl=15)
if not token:
    raise SlotTakenError()
try:
    # Business logic
    pass
finally:
    await cache.lock.release("slot:doc:2025-03-19:10:00", token)

# Context manager (recommended)
async with cache.lock.context("slot:doc:2025:10:00", ttl=15) as acquired:
    if not acquired:
        raise SlotTakenError()
    # Business logic
```

**Stampede-Protected Cache**:

```python
# Chỉ 1 request query DB, rest chờ result
slots = await cache.smart.get_or_compute(
    key=f"slots:{doctor_id}:{date}",
    fn=fetch_slots_from_db,  # async function
    ttl=300,                  # 5 minutes
    doctor_id=doctor_id,
    date=date
)
```

**Idempotency**:

```python
cache = CacheClient.from_url("redis://localhost:6379")

# Check before processing
idem_key = request.headers.get("Idempotency-Key")
cached = await cache.idempotency.get(idem_key)
if cached:
    return JSONResponse(cached['body'], cached['status_code'])

# Process
result = create_appointment(...)

# Store
await cache.idempotency.store(
    idem_key,
    status_code=200,
    body={'appointment_id': str(result.id)},
    ttl=86400  # 24h
)
```

---

### 3. healthai-events

**Purpose**: RabbitMQ event publishing/subscribing with outbox relay pattern.

**Components**:
- `RabbitMQPublisher` — Publish events to RabbitMQ
- `OutboxRelay` — Background worker relay outbox → RabbitMQ
- `BaseConsumer` — Base class for consumers
- `RetryableError`, `NonRetryableError` — Exception types

**Publisher Example**:

```python
publisher = await RabbitMQPublisher.connect(
    os.getenv("RABBITMQ_URL")
)

await publisher.publish(
    exchange='user_events',
    routing_key='user.created',
    payload={'user_id': '...', 'email': '...'}
)
```

**Outbox Relay** (run as background task):

```python
relay = OutboxRelay(session_factory, publisher)
asyncio.create_task(relay.run())
```

Relay sẽ:
1. Poll outbox_events WHERE status='pending' every 0.5s
2. Publish to RabbitMQ
3. Mark as 'published' atomically
4. Retry failed events dengan exponential backoff
5. Move to 'failed' status sau 5 retries

**Consumer Example**:

```python
class UserRegisteredConsumer(BaseConsumer):
    QUEUE = 'user_profile.register_queue'
    EXCHANGE = 'user_events'
    ROUTING_KEY = 'user.registered'
    
    async def handle(self, payload: dict):
        user_id = payload['user_id']
        # Create patient profile
        profile = PatientProfile(user_id=user_id)
        self.session.add(profile)
        await self.session.commit()

# Startup
consumer = UserRegisteredConsumer(connection, cache)
await consumer.start()
```

Consumer sẽ:
- Check idempotency (reject duplicates)
- Call `handle()`
- Auto-retry khi RetryableError
- Send to DLQ khi NonRetryableError
- Max 5 retries với backoff [1s, 5s, 15s, 60s, 300s]

---

### 4. healthai-common

**Purpose**: High-level business logic utilities.

**Components**:
- `@idempotent` — FastAPI decorator
- `CircuitBreaker` — Service resilience
- `SagaOrchestrator` — Distributed transaction coordination
- `new_id()`, `extract_timestamp()` — UUID7 helpers

**Idempotent Decorator**:

```python
@router.post("/appointments")
@idempotent(ttl=86400)
async def create_appointment(
    request: Request,
    body: CreateRequest,
    cache: CacheClient = Depends(get_cache)
):
    # Automatically caches response using Idempotency-Key header
    # Return same response if request retried with same key
    return appointment
```

Client sends:
```
POST /appointments
Idempotency-Key: <uuid>
```

**Circuit Breaker**:

```python
cb = CircuitBreaker(
    name='doctor_service',
    cache=cache,
    failure_threshold=5,
    recovery_timeout=30
)

# Call with fallback
result = await cb.call(
    fn=doctor_client.get_available_doctors,
    fallback=lambda **kw: get_cached_doctors(**kw),
    specialty_id=spec_id,
    date=date
)
```

States: CLOSED → OPEN (after 5 failures) → HALF_OPEN (after 30s) → CLOSED (if request succeeds)

**Saga Orchestrator**:

```python
class BookAppointmentSaga(SagaOrchestrator):
    SAGA_TYPE = 'book_appointment'
    
    STEPS = [
        'acquire_lock',
        'create_appointment',
        'write_outbox',
    ]
    
    COMPENSATIONS = {
        'create_appointment': 'cancel_appointment',
        'acquire_lock': 'release_lock',
    }
    
    async def execute_acquire_lock(self, ctx):
        token = await self.cache.lock.acquire(
            f"slot:{ctx['doctor_id']}:{ctx['date']}"
        )
        if not token:
            raise NonRetryableError("Slot taken")
        ctx['lock_token'] = token
    
    async def execute_create_appointment(self, ctx):
        appt = Appointment(...)
        self.session.add(appt)
        await self.session.flush()
        ctx['appointment_id'] = str(appt.id)
    
    async def compensate_release_lock(self, ctx):
        await self.cache.lock.release(
            f"slot:{ctx['doctor_id']}:{ctx['date']}",
            ctx['lock_token']
        )

# Execute
saga = BookAppointmentSaga(session, cache)
try:
    result = await saga.run({'doctor_id': ..., 'date': ...})
except SagaFailedError:
    # Compensation already ran
    pass
```

Saga sẽ:
1. Execute STEPS theo thứ tự
2. Nếu error: run COMPENSATIONS ngược lại
3. Persist state vào DB để recovery sau crash

---

## 🔌 Integration Pattern — Full Example

Appointment Service với tất cả libraries:

```python
# main.py
import asyncio
from fastapi import FastAPI
from healthai_db import create_session_factory, OutboxWriter
from healthai_cache import CacheClient
from healthai_events import RabbitMQPublisher, OutboxRelay
from healthai_common import SagaOrchestrator

app = FastAPI()

# ===== Initialization =====
@app.on_event("startup")
async def startup():
    # DB
    app.state.session_factory = create_session_factory(
        os.getenv("DATABASE_URL")
    )
    
    # Cache
    app.state.cache = CacheClient.from_url(
        os.getenv("REDIS_URL")
    )
    
    # Events
    app.state.publisher = await RabbitMQPublisher.connect(
        os.getenv("RABBITMQ_URL")
    )
    
    # Outbox relay
    relay = OutboxRelay(
        app.state.session_factory,
        app.state.publisher
    )
    asyncio.create_task(relay.run())

# ===== Saga =====
class BookAppointmentSaga(SagaOrchestrator):
    SAGA_TYPE = 'book_appointment'
    STEPS = ['acquire_lock', 'create_appointment', 'write_outbox']
    COMPENSATIONS = {
        'create_appointment': 'cancel_appointment',
        'acquire_lock': 'release_lock',
    }
    
    async def execute_acquire_lock(self, ctx):
        key = f"slot:{ctx['doctor_id']}:{ctx['date']}"
        token = await self.cache.lock.acquire(key, ttl=30)
        if not token:
            raise NonRetryableError("Slot taken")
        ctx['lock_key'] = key
        ctx['lock_token'] = token
    
    async def execute_create_appointment(self, ctx):
        appt = Appointment(
            patient_id=ctx['patient_id'],
            doctor_id=ctx['doctor_id'],
            date=ctx['date'],
            time=ctx['start_time']
        )
        self.session.add(appt)
        await self.session.flush()
        ctx['appointment_id'] = str(appt.id)
    
    async def execute_write_outbox(self, ctx):
        await OutboxWriter.write(
            self.session,
            aggregate_id=ctx['appointment_id'],
            aggregate_type='appointment_events',
            event_type='appointment.created',
            payload={
                'appointment_id': ctx['appointment_id'],
                'patient_id': ctx['patient_id'],
                'doctor_id': ctx['doctor_id'],
                'date': ctx['date'],
                'lock_key': ctx['lock_key'],
                'lock_token': ctx['lock_token'],
            }
        )
    
    async def compensate_cancel_appointment(self, ctx):
        if appt_id := ctx.get('appointment_id'):
            await self.session.execute(
                update(Appointment)
                .where(Appointment.id == appt_id)
                .values(status='cancelled')
            )
    
    async def compensate_release_lock(self, ctx):
        if ctx.get('lock_key') and ctx.get('lock_token'):
            await self.cache.lock.release(
                ctx['lock_key'],
                ctx['lock_token']
            )

# ===== Endpoint =====
@router.post("/appointments")
@idempotent(ttl=86400)
async def create_appointment(
    request: Request,
    body: CreateAppointmentRequest,
    cache: CacheClient = Depends(lambda: request.app.state.cache),
):
    session_factory = request.app.state.session_factory
    
    async with session_factory() as session:
        saga = BookAppointmentSaga(session, cache)
        try:
            async with session.begin():
                result = await saga.run({
                    'patient_id': request.state.user_id,
                    'doctor_id': body.doctor_id,
                    'date': body.date,
                    'start_time': body.start_time,
                })
        except SagaFailedError as e:
            raise HTTPException(409, str(e))
    
    return {
        'appointment_id': result['appointment_id'],
        'status': 'pending'
    }
```

**Flow**:
1. Client POST /appointments với Idempotency-Key
2. Decorator check cache → không ada → proceed
3. Saga `acquire_lock` → get Redis token
4. Saga `create_appointment` → save to DB
5. Saga `write_outbox` → write outbox event (atomic)
6. Commit: appointment + outbox + saga_state
7. Background relay detect outbox_event → publish to RabbitMQ
8. Consumer receive event → handle → idempotency check
9. Response cached để client retry tidak duplicate

---

## 🧪 Testing

```bash
cd shared/healthai-db && pytest tests/
cd shared/healthai-cache && pytest tests/
cd shared/healthai-events && pytest tests/
cd shared/healthai-common && pytest tests/
```

---

## 📋 Checklist — Integration vào Service Mới

- [ ] Add 4 dependencies vào pyproject.toml
- [ ] Tạo service models inherit từ Base, UUIDMixin, TimestampMixin
- [ ] Tạo session_factory ở main.py
- [ ] Setup CacheClient.from_url()
- [ ] Setup RabbitMQPublisher.connect()
- [ ] Start OutboxRelay ở background task
- [ ] Define Saga classes cho business flows
- [ ] Tạo Consumers extend BaseConsumer
- [ ] Use @idempotent decorator trên endpoints POST/PATCH/PUT
- [ ] Use CircuitBreaker cho inter-service calls
- [ ] Write tests cho Saga flows

---

## 🔗 Inter-Service Communication

Tất cả services share:
- **Database**: Riêng DB per service (isolation), nhưng shared models trong healthai-db
- **Cache**: Shared Redis instance (config per env)
- **Events**: Shared RabbitMQ (TOPIC exchange)
- **Schemas**: Each service phát events vào own exchange (appointment_events, user_events, etc.)

Example: Booking appointment → publish appointment.created → Patient service, Doctor service, Notification service consume via binding

