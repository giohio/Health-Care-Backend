from Application.symptom_check import _format_availability_en


def test_format_availability_unsupported_department():
    msg = _format_availability_en(
        {
            "status": "unsupported_department",
            "department": "Respiratory",
            "supported_departments": ["Cardiology", "General Medicine"],
        },
        "2026-05-07",
    )
    assert "not supported" in msg
    assert "Cardiology" in msg


def test_format_availability_no_doctors():
    msg = _format_availability_en(
        {"status": "no_doctors", "department": "Ophthalmology"},
        "2026-05-07",
    )
    assert "currently unavailable for booking" in msg


def test_format_availability_no_slots_suggests_next_weekday():
    msg = _format_availability_en({"status": "no_slots_for_date", "slots": []}, "2026-05-08")
    assert "2026-05-08" in msg
    assert "2026-05-11" in msg
