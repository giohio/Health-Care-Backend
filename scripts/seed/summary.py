"""Print a summary table of all seeded users after the seed run."""
import sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from .patients import PATIENTS


def print_summary(
    user_ids: dict[str, str],
    patient_data: list[dict],
    triage_sessions: list[dict] | None = None,
) -> None:
    print("\n" + "=" * 60)
    print("SEED COMPLETE — User credentials summary")
    print("=" * 60)

    # Admin
    print("\n[Admin]")
    print("  Email:    admin@healthai.dev")
    print("  Password: Admin123!")

    # Doctors
    print("\n[Doctors]  (password: Doctor123!)")
    from .doctors import DOCTORS
    for doc in DOCTORS:
        uid = user_ids.get(doc["email"], "—")
        print(f"  {doc['email']:<40} id={uid[:8]}…  ({doc['specialty']})")

    # Patients
    print("\n[Patients] (password: Patient123!)")
    for pat in PATIENTS:
        uid = user_ids.get(pat["email"], "—")
        uid_short = f"{uid[:8]}…" if uid != "—" else "—"
        doctor = pat.get("doctor_email", "").split("@")[0].replace("dr.", "Dr. ").replace(".", " ").title()
        print(f"  {pat['email']:<42} id={uid_short:<12}  doctor={doctor}")

    print(f"  {pat['email']:<42} id={uid_short:<12}  doctor={doctor}")

    # Triage sessions
    if triage_sessions:
        print("\n[Triage Sessions]")
        for s in triage_sessions:
            dept = s.get("department") or "—"
            urgency = s.get("urgency", "—")
            status = s.get("status", "—")
            print(
                f"  session={s['session_id'][:8]}…  "
                f"patient={s['patient_email']:<42}  "
                f"dept={dept:<20}  "
                f"urgency={urgency:<15}  "
                f"status={status}"
            )

    print("\n" + "=" * 60 + "\n")
