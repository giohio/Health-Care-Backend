class EMRDomainError(Exception):
    """Base for all EMR domain errors."""


class LabOrderNotFoundError(EMRDomainError):
    def __init__(self):
        super().__init__("Lab order not found.")


class LabResultNotFoundError(EMRDomainError):
    def __init__(self):
        super().__init__("Lab result not found.")


class InvalidLabResultStatusTransitionError(EMRDomainError):
    def __init__(self, current: str, target: str):
        super().__init__(
            f"Invalid lab result status transition: {current} -> {target}."
        )


class ResultNotPublishedError(EMRDomainError):
    def __init__(self):
        super().__init__("Lab result has not been published yet.")


class UnauthorizedEMRActionError(EMRDomainError):
    def __init__(self):
        super().__init__("Unauthorized: insufficient permissions for this EMR action.")
