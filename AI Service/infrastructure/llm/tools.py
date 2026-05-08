"""
Tool definitions for Groq tool-calling.
These tools allow the AI to interact with the hospital appointment system.
"""

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "check_availability",
            "description": (
                "Check available appointment slots for a specific department on a given date. "
                "Use this when the patient wants to book an appointment and you need to see "
                "which doctors have open slots. Returns a list of available slots with doctor names."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "department": {
                        "type": "string",
                        "description": (
                            "The medical department name. Must be one of: "
                            "Cardiology, Neurology, Pediatrics, General Medicine, "
                            "General Surgery, Dermatology, ENT, Ophthalmology"
                        ),
                    },
                    "date": {
                        "type": "string",
                        "description": "Preferred appointment date in YYYY-MM-DD format. Must not be in the past.",
                    },
                },
                "required": ["department", "date"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_appointment",
            "description": (
                "Create a real appointment with a specific doctor and time slot. "
                "Only call this AFTER presenting the available slots to the patient AND "
                "receiving explicit confirmation from the patient (they said OK, yes, etc.). "
                "Never create an appointment without the patient's explicit confirmation."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "doctor_id": {
                        "type": "string",
                        "description": "The unique identifier of the selected doctor.",
                    },
                    "specialty_id": {
                        "type": "string",
                        "description": "The specialty identifier for the appointment.",
                    },
                    "date": {
                        "type": "string",
                        "description": "Appointment date in YYYY-MM-DD format.",
                    },
                    "time": {
                        "type": "string",
                        "description": "Appointment start time in HH:MM format (24-hour).",
                    },
                    "doctor_name": {
                        "type": "string",
                        "description": "The display name of the selected doctor, as returned by check_availability.",
                    },
                },
                "required": ["doctor_id", "specialty_id", "date", "time"],
            },
        },
    },
]
