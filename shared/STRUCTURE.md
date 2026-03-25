# Shared Library Structure

```
shared/
├── healthai-db/
│   ├── pyproject.toml
│   ├── healthai_db/
│   │   ├── __init__.py
│   │   ├── base.py          # Base, UUIDMixin, TimestampMixin, SoftDeleteMixin
│   │   ├── outbox.py        # OutboxEvent, OutboxWriter
│   │   └── session.py       # create_session_factory, get_session
│   └── tests/
│       ├── __init__.py
│       └── test_outbox.py
│
├── healthai-cache/
│   ├── pyproject.toml
│   ├── healthai_cache/
│   │   ├── __init__.py
│   │   ├── client.py        # CacheClient facade
│   │   ├── lock.py          # DistributedLock (Lua-based)
│   │   ├── stampede.py      # StampedeProtectedCache (PER + single-flight)
│   │   └── idempotency.py   # IdempotencyStore
│   └── tests/
│       ├── __init__.py
│       └── test_lock.py
│
├── healthai-events/
│   ├── pyproject.toml
│   ├── healthai_events/
│   │   ├── __init__.py
│   │   ├── exceptions.py    # RetryableError, NonRetryableError
│   │   ├── publisher.py     # RabbitMQPublisher
│   │   ├── relay.py         # OutboxRelay (poll & publish)
│   │   └── consumer.py      # BaseConsumer (with DLQ, idempotency, retry)
│   └── tests/
│       ├── __init__.py
│       └── test_exceptions.py
│
├── healthai-common/
│   ├── pyproject.toml
│   ├── healthai_common/
│   │   ├── __init__.py
│   │   ├── idempotency.py    # @idempotent FastAPI decorator
│   │   ├── circuit_breaker.py # CircuitBreaker (Redis-backed state)
│   │   ├── saga.py            # SagaOrchestrator, SagaState (with compensation)
│   │   └── uuid_utils.py      # new_id(), extract_timestamp()
│   └── tests/
│       ├── __init__.py
│       └── test_uuid_utils.py
│
└── README.md                # This file + integration guide
```

## Key Design Decisions

### 1. UUID7 everywhere
- Time-ordered → better for B-tree indexes
- Extract timestamp without DB query
- Sortable lexicographically

### 2. Outbox Pattern
- Each service: entity + outbox_event in SAME transaction
- Atomicity guaranteed
- Background relay unblocked from business logic
- Retry with exponential backoff

### 3. Cache Stampede Protection (PER + Single-Flight)
- Probabilistic Early Recompute: spread recompute load
- Single-Flight: only 1 compute, rest wait
- Prevents "thundering herd" problem

### 4. Distributed Locks with Lua
- GET + DEL in atomic Lua script
- Prevents accidental release of others' locks
- Context manager for easy use

### 5. Event Consumer Resilience
- Idempotency via Redis: no duplicate processing
- Retry with backoff: [1s, 5s, 15s, 60s, 300s]
- DLQ: preserve failed messages
- RetryableError vs NonRetryableError distinction

### 6. Saga Orchestration
- Persist saga state: recover from crashes
- Automatic compensation on failure
- No distributed consensus needed
- Local DB per service + compensation logic

### 7. Circuit Breaker for Resilience
- Redis-backed state: shared between instances
- States: CLOSED → OPEN → HALF_OPEN → CLOSED
- Fallback support: use cache/stale data when service down

## Dependencies Graph

```
healthai-common
  ├─ healthai-cache
  ├─ healthai-db
  └─ (FastAPI, uuid-extension)

healthai-events
  ├─ healthai-cache
  ├─ healthai-db
  └─ (aio-pika)

healthai-cache
  └─ (redis, uuid-extension)

healthai-db
  ├─ (SQLAlchemy, asyncpg)
  └─ (uuid-extension)
```

Each library is independent; services can use any combination.
Recommend using all 4 together for full benefits.

