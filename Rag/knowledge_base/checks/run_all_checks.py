"""
Master verification runner — executes all 8 check scripts in order,
collects pass/fail/warn status from output, and prints a final summary table.

Run from knowledge_base/:
    python checks/run_all_checks.py

Or from the workspace root:
    python "AI Service/knowledge_base/checks/run_all_checks.py"
"""

import subprocess
import sys
from pathlib import Path

# Resolve the knowledge_base/ directory so we can set cwd correctly for subprocesses
KNOWLEDGE_BASE_DIR = Path(__file__).parent.parent.resolve()
CHECKS_DIR         = KNOWLEDGE_BASE_DIR / "checks"

CHECKS = [
    ("1.1+1.2", "Infra health (Qdrant + Ollama)",  "check_01_infra.py"),
    ("2.1",     "Points per department",             "check_02_counts.py"),
    ("3.1–3.4", "Payload completeness",              "check_03_payload.py"),
    ("4.1–4.2", "Parent-child link integrity",       "check_04_parentchild.py"),
    ("5.1",     "Retrieval quality (20 queries)",    "check_05_retrieval.py"),
    ("6.1–6.4", "Vector health",                     "check_06_vectors.py"),
    ("7.1–7.3", "Table chunk integrity",             "check_07_tables.py"),
    ("8.1–8.3", "Deduplication",                     "check_08_dedup.py"),
]

print("=" * 68)
print("  HealthAI Knowledge Base — Full Verification Run")
print(f"  Working directory: {KNOWLEDGE_BASE_DIR}")
print("=" * 68 + "\n")

results: list[tuple[str, str, str]] = []   # (check_id, label, status)

for check_id, label, script_name in CHECKS:
    script_path = CHECKS_DIR / script_name
    if not script_path.exists():
        print(f"  [SKIP] CHECK {check_id:<10} {label}")
        print(f"         Script not found: {script_path}")
        results.append((check_id, label, "SKIP"))
        continue

    print(f"─── CHECK {check_id}: {label} {'─' * max(0, 50 - len(label) - len(check_id))}")

    proc = subprocess.run(
        [sys.executable, "-X", "utf8", str(script_path)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=str(KNOWLEDGE_BASE_DIR),   # scripts must run from knowledge_base/
    )

    output   = proc.stdout + proc.stderr
    has_fail = "[FAIL]" in output
    has_warn = "[WARN]" in output
    has_pass = "[PASS]" in output
    non_zero = proc.returncode != 0

    if has_fail or (non_zero and not has_pass):
        status = "FAIL"
    elif has_warn:
        status = "WARN"
    else:
        status = "PASS"

    results.append((check_id, label, status))

    # Print lines that contain status markers or score info
    for line in output.split("\n"):
        stripped = line.strip()
        if any(tag in stripped for tag in
               ["[PASS]", "[FAIL]", "[WARN]", "[INFO]", "[ERROR]",
                "Score:", "RESULT:", "Total", "Found"]):
            print(f"  {stripped}")

    if non_zero and not has_pass:
        print(f"  [NOTE] Script exited with code {proc.returncode}.")
        if proc.stderr.strip():
            # Print first few lines of stderr (import errors, tracebacks, etc.)
            for line in proc.stderr.strip().split("\n")[:15]:
                print(f"  STDERR: {line}")

    print()

# ── Final summary table ──────────────────────────────────────────────────────
print("=" * 68)
print("  FINAL SUMMARY")
print("=" * 68)

ICONS = {"PASS": "✓", "FAIL": "✗", "WARN": "~", "SKIP": "-"}

for check_id, label, status in results:
    icon = ICONS.get(status, "?")
    print(f"  {icon} CHECK {check_id:<12} {label:<40} {status}")

total  = len([r for r in results if r[2] != "SKIP"])
passed = len([r for r in results if r[2] == "PASS"])
warned = len([r for r in results if r[2] == "WARN"])
failed = len([r for r in results if r[2] == "FAIL"])

print(f"\n  Total: {passed}/{total} PASS   {warned} WARN   {failed} FAIL")

# Check 5 (retrieval) is the hard gate
retrieval_status = next(
    (r[2] for r in results if r[0] == "5.1"), "SKIP"
)

print()
if failed == 0 and retrieval_status == "PASS":
    print("  VERDICT: ✓ PASS")
    print("           Knowledge base is ready for AI service integration.")
    print("           Next: implement ai_service and wire retriever.retrieve().")
elif retrieval_status == "FAIL":
    print("  VERDICT: ✗ FAIL — CHECK 5 (retrieval) failed.")
    print("           Do NOT wire knowledge base to AI service.")
    print("           Fix retrieval quality before proceeding.")
elif failed > 0:
    print(f"  VERDICT: ✗ FAIL — {failed} check(s) failed.")
    print("           Resolve all FAILs before proceeding.")
else:
    print("  VERDICT: ~ PASS WITH WARNINGS")
    print("           No hard failures. Review warnings before production use.")

print("=" * 68)
