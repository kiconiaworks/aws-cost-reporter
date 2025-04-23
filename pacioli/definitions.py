import datetime

from pydantic import BaseModel


class AccountCostChange(BaseModel):
    """Represents a change in account cost."""

    id: str
    name: str
    date: datetime.date
    previous_cost: float
    current_cost: float
    percentage_change: float


class ProjectCostChange(BaseModel):
    """Represents a change in project cost."""

    raw_id: str
    name: str
    date: datetime.date
    previous_cost: float
    current_cost: float
    percentage_change: float

    @property
    def id(self) -> str:
        """Returns the cleaned project ID."""
        return self.raw_id.replace("ProjectId$", "").strip()


class ServiceCost(BaseModel):
    """Represents the cost of a service."""

    name: str
    cost: float


class ProjectServicesCost(BaseModel):
    """Represents an itemized report for a project."""

    raw_id: str
    name: str
    date: datetime.date
    services: list[ServiceCost]
    _total_cost: float | None = None

    @property
    def id(self) -> str:
        """Returns the cleaned project ID."""
        return self.raw_id.replace("ProjectId$", "").strip()

    @property
    def total_cost(self) -> float:
        """Returns the total cost of the project."""
        if self._total_cost is not None:
            return self._total_cost
        self._total_cost = sum(service.cost for service in self.services)
        return self._total_cost
