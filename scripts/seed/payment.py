"""Seed payment DB tables (currently: lab fee configs)."""
import uuid
from datetime import datetime, timezone

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from .db_urls import _payment_db_url

DEFAULT_FEES = [
    {"test_id": "cbc", "test_name": "Complete Blood Count (CBC)", "fee": 150000},
    {"test_id": "crp", "test_name": "C-Reactive Protein (CRP)", "fee": 120000},
    {"test_id": "glucose", "test_name": "Blood Glucose (Fasting)", "fee": 80000},
    {"test_id": "hba1c", "test_name": "HbA1c", "fee": 180000},
    {"test_id": "liver", "test_name": "Liver Function Tests", "fee": 220000},
    {"test_id": "renal", "test_name": "Kidney Function (Renal Panel)", "fee": 200000},
    {"test_id": "lipid", "test_name": "Lipid Profile", "fee": 180000},
    {"test_id": "urinalysis", "test_name": "Urinalysis", "fee": 90000},
    {"test_id": "xray_chest", "test_name": "Chest X-Ray", "fee": 250000},
    {"test_id": "xray_abdominal", "test_name": "Abdominal X-Ray", "fee": 250000},
    {"test_id": "xray_skull", "test_name": "Skull X-Ray", "fee": 250000},
    {"test_id": "xray_spine", "test_name": "Spine X-Ray", "fee": 280000},
    {"test_id": "ct_chest", "test_name": "Chest CT Scan", "fee": 800000},
    {"test_id": "ct_brain", "test_name": "Brain CT Scan", "fee": 900000},
    {"test_id": "mri_brain", "test_name": "Brain MRI", "fee": 1500000},
    {"test_id": "ultrasound_abdomen", "test_name": "Abdominal Ultrasound", "fee": 350000},
    {"test_id": "lung_sounds", "test_name": "Lung Sound Recording", "fee": 180000},
    {"test_id": "heart_sounds", "test_name": "Heart Sound Recording", "fee": 220000},
]


async def seed_payment_db() -> None:
    """Upsert default lab fee configs into payment_db."""
    engine = create_async_engine(_payment_db_url(), echo=False)
    now = datetime.now(timezone.utc)

    upsert_sql = text(
        """
        INSERT INTO lab_fee_configs (id, test_id, test_name, fee, currency, created_at, updated_at)
        VALUES (:id, :test_id, :test_name, :fee, :currency, :created_at, :updated_at)
        ON CONFLICT (test_id) DO UPDATE
        SET test_name = EXCLUDED.test_name,
            fee = EXCLUDED.fee,
            currency = EXCLUDED.currency,
            updated_at = EXCLUDED.updated_at
        """
    )

    try:
        async with engine.begin() as conn:
            for item in DEFAULT_FEES:
                await conn.execute(
                    upsert_sql,
                    {
                        "id": uuid.uuid4(),
                        "test_id": item["test_id"],
                        "test_name": item["test_name"],
                        "fee": item["fee"],
                        "currency": "VND",
                        "created_at": now,
                        "updated_at": now,
                    },
                )
        print(f"  [payment] Upserted {len(DEFAULT_FEES)} lab fee config(s)")
    finally:
        await engine.dispose()
