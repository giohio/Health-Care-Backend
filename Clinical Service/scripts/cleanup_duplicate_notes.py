import asyncio
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from Domain.value_objects.note_type import NoteType
from infrastructure.database.models import ClinicalNoteModel
from infrastructure.database.session import AsyncSessionLocal
from sqlalchemy import delete, select


DEDUP_NOTE_TYPES = {NoteType.SOAP, NoteType.SUMMARY}


async def main() -> None:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(ClinicalNoteModel)
            .where(ClinicalNoteModel.note_type.in_(DEDUP_NOTE_TYPES))
            .order_by(ClinicalNoteModel.created_at.desc())
        )
        notes = list(result.scalars().all())

        grouped = defaultdict(list)
        for note in notes:
            key = (note.patient_id, note.appointment_id, note.note_type)
            grouped[key].append(note)

        delete_ids = []
        for group in grouped.values():
            if len(group) <= 1:
                continue
            # Query is already newest-first; keep the first, delete the rest.
            delete_ids.extend(note.id for note in group[1:])

        if not delete_ids:
            print("No duplicate SOAP/summary notes found.")
            return

        await session.execute(
            delete(ClinicalNoteModel).where(ClinicalNoteModel.id.in_(delete_ids))
        )
        await session.commit()
        print(f"Deleted {len(delete_ids)} duplicate SOAP/summary notes.")


if __name__ == "__main__":
    asyncio.run(main())
