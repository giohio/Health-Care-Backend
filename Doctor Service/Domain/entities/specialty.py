from dataclasses import dataclass

from uuid_extension import UUID7


@dataclass
class Specialty:
    id: UUID7
    name: str
    description: str | None = None

    def __post_init__(self):
        if not self.name or len(self.name.strip()) == 0:
            raise ValueError("Specialty name cannot be empty")
