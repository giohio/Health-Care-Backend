from enum import Enum


class NoteType(str, Enum):
    SOAP = "soap"
    PROGRESS = "progress"
    SUMMARY = "summary"
    AUSCULTATION = "auscultation"
