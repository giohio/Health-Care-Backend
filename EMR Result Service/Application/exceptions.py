class EMRApplicationError(Exception):
    """Base for application-level errors in emr_result_service."""


class LabOrderNotFoundError(EMRApplicationError):
    def __init__(self):
        super().__init__("Lab order not found.")


class LabResultNotFoundError(EMRApplicationError):
    def __init__(self):
        super().__init__("Lab result not found.")


class ResultNotAccessibleError(EMRApplicationError):
    """Patient tried to access a result that isn't PUBLISHED yet."""
    def __init__(self):
        super().__init__("Lab result is not yet published.")


class UnauthorizedReviewerError(EMRApplicationError):
    """Doctor tried to verify a result not assigned to them."""
    def __init__(self):
        super().__init__(
            "You are not the assigned reviewer for this result. "
            "Only the assigned specialist or an admin may verify it."
        )


class ResultAlreadyClaimedError(EMRApplicationError):
    """Doctor tried to claim a result that was already claimed."""
    def __init__(self):
        super().__init__("This result has already been claimed by another doctor.")


class ResultNotClaimableError(EMRApplicationError):
    """Result is not in a state that allows claiming."""
    def __init__(self, reason: str = ""):
        msg = "This result cannot be claimed."
        if reason:
            msg += f" {reason}"
        super().__init__(msg)


class InvalidStatusTransitionError(EMRApplicationError):
    def __init__(self, current: str, target: str):
        super().__init__(f"Cannot transition from {current} to {target}.")
