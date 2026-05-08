"""Static seed constants: admin credentials, specialties, and schedule helpers."""

ADMIN = {
    "email": "admin@healthai.dev",
    "password": "Admin123!",
}

SPECIALTIES = [
    {"name": "General Medicine",  "description": "Diagnosis and treatment of general internal medicine conditions", "dept": None},
    {"name": "Cardiology",        "description": "Diagnosis and treatment of heart and cardiovascular diseases",   "dept": "cardiology"},
    {"name": "Neurology",         "description": "Specialty focused on brain and nervous system disorders",        "dept": "neurology"},
    {"name": "Dermatology",       "description": "Treatment of skin, hair, and nail conditions",                  "dept": "dermatology"},
    {"name": "Pediatrics",        "description": "Medical care for infants, children, and adolescents",           "dept": "pediatrics"},
    {"name": "General Surgery",   "description": "Surgical procedures for general and abdominal conditions",      "dept": "general_surgery"},
    {"name": "ENT",               "description": "Ear, nose, and throat disorders and surgery",                   "dept": "ent"},
    {"name": "Ophthalmology",     "description": "Eye diseases, vision care, and ocular surgery",                 "dept": "ophthalmology"},
]

# day_of_week helpers
DOW_NAMES = ["MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY", "FRIDAY", "SATURDAY"]
DOW_INT   = [0, 1, 2, 3, 4, 5]
