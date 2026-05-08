from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import List, Optional
from uuid import UUID


class TemplateCreatorType(str, Enum):
    SYSTEM = "SYSTEM"
    PERSONAL = "PERSONAL"


@dataclass
class TemplateTestItem:
    """A single test entry within a lab order template."""
    test_name: str
    test_type: Optional[str] = None   # maps to TestType enum value
    instructions: Optional[str] = None
    priority: str = "routine"          # maps to OrderPriority enum value


@dataclass
class LabOrderTemplate:
    id: UUID
    name: str
    description: Optional[str]
    department: Optional[str]
    test_items: List[TemplateTestItem]
    creator_type: TemplateCreatorType
    creator_id: Optional[UUID]          # None for SYSTEM templates
    is_active: bool = True
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
