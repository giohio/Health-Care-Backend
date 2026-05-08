from enum import Enum


class TestType(str, Enum):
    __test__ = False

    BLOOD_PANEL = "blood_panel"
    IMAGING = "imaging"
    ECG = "ecg"
    URINE = "urine"
    OTHER = "other"
    BONE_XRAY = "bone_xray"
    ABDOMINAL_XRAY = "abdominal_xray"
    SKULL_XRAY = "skull_xray"
    SPINE_XRAY = "spine_xray"
    CHEST_XRAY = "chest_xray"
