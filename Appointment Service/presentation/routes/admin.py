from datetime import date
from typing import Annotated

from Application.use_cases.get_admin_chart_data import GetAdminChartDataUseCase
from Application.use_cases.get_admin_stats import GetAdminStatsUseCase
from Application.use_cases.list_admin_appointments import ListAdminAppointmentsUseCase
from fastapi import APIRouter, Depends, Header, HTTPException, Query
from presentation.dependencies import get_admin_chart_data_use_case, get_admin_stats_use_case, get_list_admin_appointments_use_case

router = APIRouter(prefix="/admin", tags=["Admin — Appointments"])


def _require_admin(x_user_role: str | None = Header(default=None, alias="X-User-Role", include_in_schema=False)):
    if x_user_role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")


@router.get("/stats", summary="Admin: aggregate appointment statistics")
async def get_admin_stats(
    use_case: Annotated[GetAdminStatsUseCase, Depends(get_admin_stats_use_case)],
    range: str = Query(default="month", description="week | month | quarter"),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    _: None = Depends(_require_admin),
):
    """
    Returns aggregated statistics for all appointments.
    Admin only. Query params override range when both date_from and date_to are provided.
    """
    return await use_case.execute(range_type=range, date_from=date_from, date_to=date_to)


@router.get("/chart-data", summary="Admin: chart data points for dashboard")
async def get_admin_chart_data(
    use_case: Annotated[GetAdminChartDataUseCase, Depends(get_admin_chart_data_use_case)],
    range: str = Query(default="month", description="week | month | quarter"),
    metric: str = Query(default="appointments", description="appointments | revenue"),
    _: None = Depends(_require_admin),
):
    """
    Returns daily data points (zero-filled) for chart rendering.
    Admin only.
    """
    return await use_case.execute(range_type=range, metric=metric)


@router.get("/appointments", summary="Admin: list all appointments with filters")
async def list_admin_appointments(
    use_case: Annotated[ListAdminAppointmentsUseCase, Depends(get_list_admin_appointments_use_case)],
    range: str = Query(default="month", description="today | week | month | quarter"),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    status: str | None = Query(default=None),
    doctor_id: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=50, ge=1, le=200),
    _: None = Depends(_require_admin),
):
    """
    Returns paginated list of all appointments across all doctors.
    Admin only. Supports filtering by date range, status, and doctor.
    """
    return await use_case.execute(
        range_type=range,
        date_from=date_from,
        date_to=date_to,
        status=status,
        doctor_id=doctor_id,
        page=page,
        limit=limit,
    )
