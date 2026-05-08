import asyncio
import logging
from typing import Annotated, List, Optional
from uuid import UUID
import io

from fastapi.responses import StreamingResponse
from Application.dtos import (
    AppointmentLabSummaryResponse,
    CreateLabOrderFromTemplateRequest,
    CreateLabOrderRequest,
    CreateLabOrderTemplateRequest,
    CreateLabResultRequest,
    FileUploadResponse,
    LabOrderResponse,
    LabOrderTemplateResponse,
    LabResultResponse,
    ReviewHolisticSummaryRequest,
    UpdateAIDraftRequest,
    UpdateHolisticSummaryRequest,
    VerifyLabResultRequest,
)
from Application.exceptions import (
    LabOrderNotFoundError,
    LabResultNotFoundError,
    ResultAlreadyClaimedError,
    ResultNotAccessibleError,
    ResultNotClaimableError,
    UnauthorizedReviewerError,
)
from Application.use_cases.create_lab_order import CreateLabOrderUseCase
from Application.use_cases.delete_lab_order import DeleteLabOrderUseCase
from Application.use_cases.flag_manual_review import FlagManualReviewUseCase
from Application.use_cases.get_lab_readiness import GetLabReadinessUseCase
from Application.use_cases.get_lab_results import GetLabResultUseCase, ListLabResultsUseCase
from Application.use_cases.holistic_summary import GetHolisticSummaryUseCase, UpdateHolisticSummaryUseCase, ReviewHolisticSummaryUseCase
from Application.use_cases.lab_order_template import (
    CreateLabOrderTemplateUseCase,
    CreateOrdersFromTemplateUseCase,
    DeleteLabOrderTemplateUseCase,
    ListLabOrderTemplatesUseCase,
)
from Application.use_cases.claim_lab_result import ClaimLabResultUseCase
from Application.use_cases.list_lab_orders import ListLabOrdersUseCase
from Application.use_cases.update_ai_draft import UpdateAIDraftUseCase
from Application.use_cases.upload_file import UploadFileRequest, UploadFileUseCase
from Application.use_cases.upload_lab_result import UploadLabResultUseCase
from Application.use_cases.verify_and_publish import VerifyAndPublishUseCase
from Domain.value_objects.lab_result_status import LabResultStatus
from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, Query, UploadFile
from infrastructure.clients.ai_service_client import AiServiceClient
from infrastructure.clients.external_clients import PatientServiceClient
from infrastructure.repositories import LabOrderRepository, LabResultRepository
from presentation.dependencies import (
    get_ai_service_client,
    get_create_order_template_use_case,
    get_create_order_use_case,
    get_create_orders_from_template_use_case,
    get_delete_order_template_use_case,
    get_delete_order_use_case,
    get_flag_manual_review_use_case,
    get_list_order_templates_use_case,
    get_list_orders_use_case,
    get_list_results_use_case,
    get_order_repo,
    get_patient_service_client,
    get_readiness_use_case,
    get_result_use_case,
    get_result_repo,
    get_claim_lab_result_use_case,
    get_update_ai_draft_use_case,
    get_upload_file_use_case,
    get_upload_result_use_case,
    get_verify_publish_use_case,
    get_get_holistic_summary_use_case,
    get_get_holistic_summary_use_case,
    get_update_holistic_summary_use_case,
    get_review_holistic_summary_use_case,
    get_summary_repo,
)

logger = logging.getLogger(__name__)


async def _enrich_patient_name(
    response: LabResultResponse, patient_svc
) -> LabResultResponse:
    try:
        name = await patient_svc.get_patient_name(response.patient_id)
    except Exception:
        logger.exception("Failed to enrich patient name for lab result %s", response.id)
        name = None
    response.patient_name = name
    return response


async def _safe_get_patient_name(patient_svc, patient_id: UUID) -> str | None:
    try:
        return await patient_svc.get_patient_name(patient_id)
    except Exception:
        logger.exception("Failed to enrich patient name for patient_id=%s", patient_id)
        return None

router = APIRouter(tags=["EMR Results"])

MISSING_USER_ID = "X-User-Id header is missing"
MISSING_ROLE = "X-User-Role header is missing"


def _require_user_id(x_user_id: UUID | None) -> UUID:
    if not x_user_id:
        raise HTTPException(status_code=401, detail=MISSING_USER_ID)
    return x_user_id


def _require_role(x_user_role: str | None, allowed: list[str]) -> str:
    if not x_user_role:
        raise HTTPException(status_code=401, detail=MISSING_ROLE)
    if x_user_role not in allowed:
        raise HTTPException(status_code=403, detail="Insufficient role.")
    return x_user_role


# ---------------------------------------------------------------------------
# File Upload
# ---------------------------------------------------------------------------


@router.post(
    "/upload",
    response_model=FileUploadResponse,
    summary="Upload a file; returns a storage URL to pass to POST /lab-results",
)
async def upload_file(
    file: UploadFile = File(...),
    context: Optional[str] = Form(None),
    x_user_id: UUID | None = Header(None),
    x_user_role: str | None = Header(None),
    use_case: UploadFileUseCase = Depends(get_upload_file_use_case),
):
    _require_user_id(x_user_id)
    _require_role(x_user_role, ["doctor", "admin"])

    data = await file.read()
    request = UploadFileRequest(
        data=data,
        original_filename=file.filename or "upload",
        content_type=file.content_type or "",
        subfolder=context or "lab_results",
    )
    try:
        return use_case.execute(request)
    except ValueError as exc:
        msg = str(exc)
        if msg.startswith("unsupported_mime:"):
            raise HTTPException(status_code=415, detail=f"Unsupported file type: {msg.split(':', 1)[1]}")
        if msg == "empty_file":
            raise HTTPException(status_code=400, detail="No file content received.")
        if msg.startswith("size_exceeded:"):
            limit_mb = msg.split(":", 1)[1]
            raise HTTPException(status_code=400, detail=f"File exceeds size limit of {limit_mb} MB.")
        raise HTTPException(status_code=400, detail=msg)


# ---------------------------------------------------------------------------
# Lab Orders
# ---------------------------------------------------------------------------


@router.post(
    "/lab-orders",
    response_model=LabOrderResponse,
    status_code=201,
    summary="Doctor creates a lab order",
)
async def create_lab_order(
    body: CreateLabOrderRequest,
    x_user_id: UUID | None = Header(None),
    x_user_role: str | None = Header(None),
    use_case: CreateLabOrderUseCase = Depends(get_create_order_use_case),
):
    _require_user_id(x_user_id)
    _require_role(x_user_role, ["doctor", "admin"])
    return await use_case.execute(body)


@router.get(
    "/lab-orders",
    response_model=List[LabOrderResponse],
    summary="List lab orders (patient or doctor filtered)",
)
async def list_lab_orders(
    patient_id: Optional[UUID] = Query(None),
    doctor_id: Optional[UUID] = Query(None),
    x_user_id: UUID | None = Header(None),
    x_user_role: str | None = Header(None),
    use_case: ListLabOrdersUseCase = Depends(get_list_orders_use_case),
    patient_svc=Depends(get_patient_service_client),
):
    user_id = _require_user_id(x_user_id)
    role = _require_role(x_user_role, ["doctor", "patient", "admin"])
    # Patients may only query their own orders
    if role == "patient":
        patient_id = user_id
    orders = await use_case.execute(patient_id=patient_id, doctor_id=doctor_id)
    for order in orders:
        order.patient_name = await _safe_get_patient_name(patient_svc, order.patient_id)
    return orders


@router.get(
    "/lab-orders/{appointment_id}/readiness",
    summary="Get lab readiness status for an appointment",
)
async def get_lab_readiness(
    appointment_id: UUID,
    x_user_id: UUID | None = Header(None),
    x_user_role: str | None = Header(None),
    use_case: GetLabReadinessUseCase = Depends(get_readiness_use_case),
):
    _require_user_id(x_user_id)
    _require_role(x_user_role, ["doctor", "admin", "service"])
    return await use_case.execute(appointment_id)


# ---------------------------------------------------------------------------
# Lab Results
# ---------------------------------------------------------------------------


@router.post(
    "/lab-results",
    response_model=LabResultResponse,
    status_code=201,
    summary="Upload a lab result file (triggers async AI pipeline)",
)
async def upload_lab_result(
    body: CreateLabResultRequest,
    authorization: str | None = Header(None),
    x_user_id: UUID | None = Header(None),
    x_user_role: str | None = Header(None),
    use_case: UploadLabResultUseCase = Depends(get_upload_result_use_case),
    order_repo: LabOrderRepository = Depends(get_order_repo),
    ai_client: AiServiceClient = Depends(get_ai_service_client),
):
    _require_user_id(x_user_id)
    _require_role(x_user_role, ["doctor", "admin"])
    try:
        result = await use_case.execute(body)
    except LabOrderNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    # Fire-and-forget AI analysis — file uploads AND manual/tabular entries
    if authorization:
        order = await order_repo.get_by_id(body.order_id)
        if order:
            if body.file_type == "manual" and body.manual_entries:
                # Manual / CSV: pass structured entries as tabular_data
                tabular_data = {"entries": [e.model_dump() for e in body.manual_entries]}
                asyncio.create_task(
                    ai_client.trigger_lab_analysis(
                        result_id=result.id,
                        patient_id=result.patient_id,
                        file_url=None,
                        file_type="manual",
                        department=order.department or "internal_medicine",
                        test_name=order.test_name,
                        auth_token=authorization.replace("Bearer ", ""),
                        x_user_id=x_user_id,
                        x_user_role=x_user_role,
                        tabular_data=tabular_data,
                    )
                )
            elif body.file_type != "manual" and body.file_url:
                asyncio.create_task(
                    ai_client.trigger_lab_analysis(
                        result_id=result.id,
                        patient_id=result.patient_id,
                        file_url=body.file_url,
                        file_type=body.file_type,
                        department=order.department or "internal_medicine",
                        test_name=order.test_name,
                        auth_token=authorization.replace("Bearer ", ""),
                        x_user_id=x_user_id,
                        x_user_role=x_user_role,
                    )
                )

    return result


@router.post(
    "/lab-results/{result_id}/retry-ai",
    summary="Re-trigger AI analysis for a stuck PENDING/AI_PROCESSING result",
)
async def retry_ai_analysis(
    result_id: UUID,
    authorization: str | None = Header(None),
    x_user_id: UUID | None = Header(None),
    x_user_role: str | None = Header(None),
    result_use_case: GetLabResultUseCase = Depends(get_result_use_case),
    result_repo: LabResultRepository = Depends(get_result_repo),
    order_repo: LabOrderRepository = Depends(get_order_repo),
    ai_client: AiServiceClient = Depends(get_ai_service_client),
):
    _require_user_id(x_user_id)
    _require_role(x_user_role, ["doctor", "admin"])

    try:
        result = await result_use_case.execute(result_id, caller_role="doctor")
    except LabResultNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    retryable = {LabResultStatus.PENDING, LabResultStatus.AI_PROCESSING, LabResultStatus.NEEDS_MANUAL_REVIEW}
    # Also allow manual entries that somehow ended up in DOCTOR_REVIEW without AI running
    is_manual = result.file_type == "manual"
    if result.status not in retryable and not (is_manual and result.status == LabResultStatus.DOCTOR_REVIEW):
        raise HTTPException(
            status_code=400,
            detail=f"Result is not in a retryable state (current: {result.status})",
        )

    # Reset failed / stuck results back to PENDING so the AI pipeline can re-run cleanly
    if result.status in (LabResultStatus.NEEDS_MANUAL_REVIEW, LabResultStatus.DOCTOR_REVIEW):
        entity = await result_repo.get_by_id(result_id)
        if entity is None:
            raise HTTPException(status_code=404, detail="Lab result not found")
        entity.transition_to(LabResultStatus.PENDING)
        await result_repo.save(entity)

    if not authorization:
        raise HTTPException(status_code=422, detail="Missing auth token")

    order = await order_repo.get_by_id(result.order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Lab order not found")

    if is_manual:
        import json as _json
        tabular_data = None
        # Primary: raw_input_json stores entries permanently and is never overwritten by AI
        raw_src = result.raw_input_json
        # Fallback: legacy results stored entries in ai_draft_text before raw_input_json existed
        legacy_src = result.ai_draft_text if not raw_src else None
        for src in (raw_src, legacy_src):
            if not src:
                continue
            try:
                parsed = _json.loads(src)
                if isinstance(parsed, list) and parsed:
                    tabular_data = {"entries": parsed}
                    break
            except Exception:
                continue
        if not tabular_data:
            raise HTTPException(
                status_code=422,
                detail="Cannot retry: no manual entry data on record. "
                       "Please delete this result and re-upload the CSV.",
            )
        asyncio.create_task(
            ai_client.trigger_lab_analysis(
                result_id=result.id,
                patient_id=result.patient_id,
                file_url=None,
                file_type="manual",
                department=order.department or "internal_medicine",
                test_name=order.test_name,
                auth_token=authorization.replace("Bearer ", ""),
                x_user_id=x_user_id,
                x_user_role=x_user_role,
                tabular_data=tabular_data,
            )
        )
    else:
        if not result.file_url:
            raise HTTPException(status_code=422, detail="Cannot retry: no file URL on record")
        asyncio.create_task(
            ai_client.trigger_lab_analysis(
                result_id=result.id,
                patient_id=result.patient_id,
                file_url=result.file_url,
                file_type=result.file_type or "pdf",
                department=order.department or "internal_medicine",
                test_name=order.test_name,
                auth_token=authorization.replace("Bearer ", ""),
                x_user_id=x_user_id,
                x_user_role=x_user_role,
            )
        )

    return {"message": "AI analysis re-triggered"}


@router.get(
    "/lab-results",
    response_model=List[LabResultResponse],
    summary="List lab results",
)
async def list_lab_results(
    patient_id: Optional[UUID] = Query(None),
    status: Optional[LabResultStatus] = Query(None),
    # Specialty worklist filters
    reviewer_doctor_id: Optional[UUID] = Query(None, description="Filter by assigned reviewer"),
    required_specialty: Optional[str] = Query(None, description="Filter by specialty (e.g. radiology)"),
    open_claim: Optional[bool] = Query(None, description="True → unclaimed specialty results only"),
    x_user_id: UUID | None = Header(None),
    x_user_role: str | None = Header(None),
    use_case: ListLabResultsUseCase = Depends(get_list_results_use_case),
    patient_svc=Depends(get_patient_service_client),
):
    user_id = _require_user_id(x_user_id)
    role = _require_role(x_user_role, ["doctor", "patient", "admin"])
    # Patients only query their own results (and only see PUBLISHED)
    if role == "patient":
        patient_id = user_id
    results = await use_case.execute(
        caller_role=role,
        patient_id=patient_id,
        status=status,
        reviewer_doctor_id=reviewer_doctor_id,
        required_specialty=required_specialty,
        open_claim=open_claim,
    )
    enriched = await asyncio.gather(*[_enrich_patient_name(r, patient_svc) for r in results])
    return list(enriched)


@router.get(
    "/lab-results/{result_id}",
    response_model=LabResultResponse,
    summary="Get a single lab result",
)
async def get_lab_result(
    result_id: UUID,
    x_user_id: UUID | None = Header(None),
    x_user_role: str | None = Header(None),
    use_case: GetLabResultUseCase = Depends(get_result_use_case),
    patient_svc=Depends(get_patient_service_client),
):
    _require_user_id(x_user_id)
    role = _require_role(x_user_role, ["doctor", "patient", "admin", "service"])
    try:
        result = await use_case.execute(result_id=result_id, caller_role=role)
        return await _enrich_patient_name(result, patient_svc)
    except LabResultNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ResultNotAccessibleError as exc:
        raise HTTPException(status_code=403, detail=str(exc))


@router.get(
    "/lab-results/{result_id}/pdf",
    summary="Download a lab result as a formatted PDF",
)
async def download_lab_result_pdf(
    result_id: UUID,
    x_user_id: UUID | None = Header(None),
    x_user_role: str | None = Header(None),
    use_case: GetLabResultUseCase = Depends(get_result_use_case),
    order_repo: LabOrderRepository = Depends(get_order_repo),
    patient_svc: "PatientServiceClient" = Depends(get_patient_service_client),
):
    """Generate and return a printable PDF for a lab result."""
    _require_user_id(x_user_id)
    role = _require_role(x_user_role, ["doctor", "patient", "admin"])

    try:
        result = await use_case.execute(result_id=result_id, caller_role=role)
    except LabResultNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ResultNotAccessibleError as exc:
        raise HTTPException(status_code=403, detail=str(exc))

    # Enrich with order + patient details
    test_name = "Lab Result"
    order = await order_repo.get_by_id(result.order_id)
    if order:
        test_name = order.test_name

    patient_name = await patient_svc.get_patient_name(result.patient_id)

    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.lib.units import cm
        from reportlab.platypus import (
            Paragraph,
            SimpleDocTemplate,
            Spacer,
            Table,
            TableStyle,
        )
    except ImportError:
        raise HTTPException(
            status_code=500,
            detail="PDF generation library not installed. Contact your administrator.",
        )

    # ── PDF layout constants ──────────────────────────────────────────────────
    PAGE_W, _ = A4
    L_MARGIN = R_MARGIN = 2 * cm
    BODY_W   = PAGE_W - L_MARGIN - R_MARGIN

    # Build PDF
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=L_MARGIN,
        rightMargin=R_MARGIN,
        topMargin=1.5 * cm,
        bottomMargin=2 * cm,
    )

    # Brand colours
    CLR_NAVY   = colors.HexColor("#1a3a5c")
    CLR_BLUE   = colors.HexColor("#2176ae")
    CLR_LIGHT  = colors.HexColor("#eaf3fb")
    CLR_HIGH   = colors.HexColor("#c0392b")
    CLR_LOW    = colors.HexColor("#2980b9")
    CLR_NORMAL = colors.HexColor("#27ae60")
    CLR_BORDER = colors.HexColor("#c8d8e8")
    CLR_MUTED  = colors.HexColor("#7f8c8d")
    CLR_WHITE  = colors.HexColor("#ffffff")

    def para(text, **kw):
        d = dict(fontName="Helvetica", fontSize=9, leading=13, textColor=colors.black)
        d.update(kw)
        return Paragraph(str(text), ParagraphStyle("p", **d))

    def bold(text, **kw):
        return para(text, fontName="Helvetica-Bold", **kw)

    def section_bar(text, bg=CLR_NAVY):
        t = Table([[para(f"<b>{text}</b>", fontName="Helvetica-Bold", fontSize=10,
                          textColor=colors.white, leading=14)]], colWidths=[BODY_W])
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), bg),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ]))
        return t

    def info_table(rows, col_widths=None):
        if col_widths is None:
            col_widths = [BODY_W * 0.33, BODY_W * 0.67]
        data = [[bold(lbl, fontSize=9), para(val, fontSize=9)] for lbl, val in rows]
        t = Table(data, colWidths=col_widths)
        t.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("LEFTPADDING", (0, 0), (0, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ("LINEBELOW", (0, -1), (-1, -1), 0.4, CLR_BORDER),
        ]))
        return t

    def result_row(f, idx):
        name   = f.get("name") or f.get("finding", "N/A")
        value  = str(f.get("value", f.get("severity", "–")))
        unit   = f.get("unit", "")
        ref_l  = f.get("reference_low")
        ref_h  = f.get("reference_high")
        flag   = str(f.get("flag", "N")).upper()

        if ref_l is not None and ref_h is not None:
            ref_range = f"{ref_l} – {ref_h} {unit}".strip()
        else:
            ref_range = "–"

        value_str = f"{value} {unit}".strip() if unit else value

        if flag in ("H", "HIGH"):
            flag_label = "↑ High"
            flag_color = CLR_HIGH
        elif flag in ("L", "LOW"):
            flag_label = "↓ Low"
            flag_color = CLR_LOW
        elif flag in ("C", "CRITICAL"):
            flag_label = "⚠ Critical"
            flag_color = CLR_HIGH
        else:
            flag_label = "Normal"
            flag_color = CLR_NORMAL

        bg = CLR_WHITE if idx % 2 == 0 else CLR_LIGHT
        cells = [
            para(name, fontSize=9, leading=12),
            para(value_str, fontSize=9, leading=12, fontName="Helvetica-Bold"),
            para(ref_range, fontSize=9, leading=12),
            para(flag_label, fontSize=9, leading=12, fontName="Helvetica-Bold", textColor=flag_color),
        ]
        return cells, bg

    story = []

    # ① Hospital header
    hdr_data = [[
        para("🏥  D-HEALTH HOSPITAL", fontName="Helvetica-Bold", fontSize=15,
              textColor=CLR_NAVY, leading=20),
        para("DEPARTMENT OF LABORATORY MEDICINE", fontName="Helvetica-Bold",
              fontSize=8.5, textColor=CLR_BLUE, leading=12, alignment=1),
    ]]
    hdr = Table(hdr_data, colWidths=[BODY_W * 0.55, BODY_W * 0.45])
    hdr.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (1, 0), (1, 0), "RIGHT"),
        ("LINEBELOW", (0, 0), (-1, -1), 2, CLR_NAVY),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ]))
    story.append(hdr)
    story.append(Spacer(1, 0.25 * cm))

    # ② Report title banner
    banner = Table([[para("LABORATORY TEST REPORT", fontName="Helvetica-Bold", fontSize=13,
                           textColor=colors.white, leading=17, alignment=1)]],
                   colWidths=[BODY_W])
    banner.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), CLR_BLUE),
        ("TOPPADDING", (0, 0), (-1, -1), 9),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 9),
    ]))
    story.append(banner)
    story.append(Spacer(1, 0.35 * cm))

    # ③ Patient info section
    status_label = result.status.value if hasattr(result.status, "value") else result.status
    created_str  = str(result.created_at or "")[:10]
    patient_rows = [
        ["Patient Name",  patient_name or "N/A"],
        ["Test Name",    test_name],
        ["Specimen Date", created_str],
        ["Report Status", status_label],
        ["Report ID",    str(result_id)],
    ]
    story.append(section_bar("PATIENT INFORMATION"))
    story.append(Spacer(1, 0.15 * cm))
    story.append(info_table(patient_rows))
    story.append(Spacer(1, 0.4 * cm))

    # ④ AI Clinical Summary
    published_text = result.published_text or result.ai_draft_text
    if published_text:
        story.append(section_bar("AI CLINICAL SUMMARY", bg=CLR_BLUE))
        story.append(Spacer(1, 0.15 * cm))
        summary_tbl = Table([[para(published_text, fontSize=9, leading=14,
                                    textColor=colors.HexColor("#2c3e50"))]], colWidths=[BODY_W])
        summary_tbl.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), CLR_LIGHT),
            ("BOX", (0, 0), (-1, -1), 0.5, CLR_BORDER),
            ("TOPPADDING", (0, 0), (-1, -1), 10),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
            ("LEFTPADDING", (0, 0), (-1, -1), 10),
            ("RIGHTPADDING", (0, 0), (-1, -1), 10),
        ]))
        story.append(summary_tbl)
        story.append(Spacer(1, 0.4 * cm))

    # ⑤ Detailed Results
    raw_findings = (
        result.published_findings
        if result.published_findings is not None
        else result.ai_visual_findings
    )
    findings = raw_findings
    if isinstance(raw_findings, str):
        import json
        try:
            findings = json.loads(raw_findings)
        except Exception:
            findings = None

    if findings and isinstance(findings, list):
        story.append(section_bar("DETAILED LABORATORY RESULTS", bg=CLR_NAVY))
        story.append(Spacer(1, 0.15 * cm))

        hdr_row = [
            bold("Test Parameter", fontSize=9, textColor=colors.white, leading=12),
            bold("Result", fontSize=9, textColor=colors.white, leading=12),
            bold("Reference Range", fontSize=9, textColor=colors.white, leading=12),
            bold("Flag", fontSize=9, textColor=colors.white, leading=12),
        ]
        table_data = [hdr_row]
        row_bgs = []
        for idx, f in enumerate(findings):
            cells, bg = result_row(f, idx)
            table_data.append(cells)
            row_bgs.append(bg)

        findings_tbl = Table(
            table_data,
            colWidths=[BODY_W * 0.36, BODY_W * 0.20, BODY_W * 0.26, BODY_W * 0.18],
            repeatRows=1,
        )
        ts = TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), CLR_NAVY),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("TOPPADDING", (0, 0), (-1, -1), 7),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ("GRID", (0, 0), (-1, -1), 0.4, CLR_BORDER),
            ("LINEBELOW", (0, 0), (-1, 0), 1.5, CLR_BLUE),
        ])
        for idx, bg in enumerate(row_bgs, start=1):
            ts.add("BACKGROUND", (0, idx), (-1, idx), bg)
        findings_tbl.setStyle(ts)
        story.append(findings_tbl)
        story.append(Spacer(1, 0.4 * cm))

    # ⑥ Disclaimer
    disclaimer_lines = [
        "• This report is generated by an AI-assisted system and is intended for informational purposes only.",
        "• It does NOT constitute a medical diagnosis. Please consult your treating physician for clinical decisions.",
        "• Results should be interpreted in conjunction with clinical history and other diagnostic findings.",
    ]
    disclaimer_tbl = Table([[para("<br/>".join(disclaimer_lines), fontSize=7.5, leading=11,
                                    textColor=colors.HexColor("#7f8c8d"))]], colWidths=[BODY_W])
    disclaimer_tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#fef9f9")),
        ("BOX", (0, 0), (-1, -1), 0.8, CLR_HIGH),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
    ]))
    story.append(disclaimer_tbl)
    story.append(Spacer(1, 0.25 * cm))

    # ⑦ Signature lines
    sig_data = [[
        para("Reviewed by: _______________________", fontSize=8, textColor=CLR_MUTED, leading=11),
        para("Authorised by: ______________________", fontSize=8, textColor=CLR_MUTED, leading=11, alignment=1),
    ]]
    sig_tbl = Table(sig_data, colWidths=[BODY_W * 0.5, BODY_W * 0.5])
    sig_tbl.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "BOTTOM"),
        ("ALIGN", (1, 0), (1, 0), "RIGHT"),
        ("LINEABOVE", (0, 0), (-1, 0), 0.5, CLR_BORDER),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ]))
    story.append(sig_tbl)

    doc.build(story)
    buffer.seek(0)
    filename = f"lab-result-{result_id}.pdf"

    return StreamingResponse(
        buffer,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.patch(
    "/lab-results/{result_id}/verify",
    response_model=LabResultResponse,
    summary="Doctor verifies and publishes a lab result",
)
async def verify_and_publish(
    result_id: UUID,
    body: VerifyLabResultRequest,
    x_user_id: UUID | None = Header(None),
    x_user_role: str | None = Header(None),
    use_case: VerifyAndPublishUseCase = Depends(get_verify_publish_use_case),
):
    doctor_id = _require_user_id(x_user_id)
    role = _require_role(x_user_role, ["doctor", "admin"])
    try:
        return await use_case.execute(
            result_id=result_id, doctor_id=doctor_id, request=body, caller_role=role
        )
    except LabResultNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except UnauthorizedReviewerError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.patch(
    "/lab-results/{result_id}/ai-draft",
    response_model=LabResultResponse,
    summary="[Internal] AI Service applies analysis output to a lab result",
)
async def apply_ai_draft(
    result_id: UUID,
    body: UpdateAIDraftRequest,
    x_user_role: str | None = Header(None),
    use_case: UpdateAIDraftUseCase = Depends(get_update_ai_draft_use_case),
):
    """Called exclusively by the AI Service Celery worker — not exposed to patients/doctors."""
    _require_role(x_user_role, ["admin", "service"])
    try:
        return await use_case.execute(result_id=result_id, request=body)
    except LabResultNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.patch(
    "/lab-results/{result_id}/flag-manual",
    response_model=LabResultResponse,
    summary="Doctor flags a result for manual review",
)
async def flag_manual_review(
    result_id: UUID,
    x_user_id: UUID | None = Header(None),
    x_user_role: str | None = Header(None),
    use_case: FlagManualReviewUseCase = Depends(get_flag_manual_review_use_case),
):
    _require_user_id(x_user_id)
    _require_role(x_user_role, ["doctor", "admin"])
    try:
        return await use_case.execute(result_id)
    except LabResultNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.patch(
    "/lab-results/{result_id}/claim",
    response_model=LabResultResponse,
    summary="Specialist claims an open-claim lab result from the specialty worklist",
)
async def claim_lab_result(
    result_id: UUID,
    x_user_id: UUID | None = Header(None),
    x_user_role: str | None = Header(None),
    use_case: ClaimLabResultUseCase = Depends(get_claim_lab_result_use_case),
):
    """Assigns the calling doctor as the reviewer for an unclaimed specialty result.

    After claiming, only this doctor (or an admin) can call ``/verify``.
    The frontend should use ``GET /lab-results?required_specialty=<s>&open_claim=true``
    to populate the specialty worklist before claiming.
    """
    doctor_id = _require_user_id(x_user_id)
    _require_role(x_user_role, ["doctor", "admin"])
    try:
        return await use_case.execute(result_id=result_id, doctor_id=doctor_id)
    except LabResultNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ResultAlreadyClaimedError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except ResultNotClaimableError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


# ---------------------------------------------------------------------------
# Lab Order Templates
# ---------------------------------------------------------------------------


@router.post(
    "/lab-orders/templates",
    response_model=LabOrderTemplateResponse,
    status_code=201,
    summary="Create a lab order template (admin → SYSTEM, doctor → PERSONAL)",
)
async def create_lab_order_template(
    body: CreateLabOrderTemplateRequest,
    x_user_id: UUID | None = Header(None),
    x_user_role: str | None = Header(None),
    use_case: CreateLabOrderTemplateUseCase = Depends(get_create_order_template_use_case),
):
    creator_id = _require_user_id(x_user_id)
    creator_role = _require_role(x_user_role, ["doctor", "admin"])
    return await use_case.execute(
        request=body, creator_id=creator_id, creator_role=creator_role
    )


@router.get(
    "/lab-orders/templates",
    response_model=List[LabOrderTemplateResponse],
    summary="List available lab order templates (SYSTEM + personal)",
)
async def list_lab_order_templates(
    department: Optional[str] = Query(None),
    x_user_id: UUID | None = Header(None),
    x_user_role: str | None = Header(None),
    use_case: ListLabOrderTemplatesUseCase = Depends(get_list_order_templates_use_case),
):
    caller_id = _require_user_id(x_user_id)
    caller_role = _require_role(x_user_role, ["doctor", "admin"])
    return await use_case.execute(
        caller_id=caller_id, caller_role=caller_role, department=department
    )


@router.delete(
    "/lab-orders/templates/{template_id}",
    status_code=204,
    summary="Delete a lab order template",
)
async def delete_lab_order_template(
    template_id: UUID,
    x_user_id: UUID | None = Header(None),
    x_user_role: str | None = Header(None),
    use_case: DeleteLabOrderTemplateUseCase = Depends(get_delete_order_template_use_case),
):
    caller_id = _require_user_id(x_user_id)
    caller_role = _require_role(x_user_role, ["doctor", "admin"])
    try:
        await use_case.execute(
            template_id=template_id, caller_id=caller_id, caller_role=caller_role
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc))


@router.post(
    "/lab-orders/from-template",
    response_model=List[LabOrderResponse],
    status_code=201,
    summary="Batch-create lab orders from a template",
)
async def create_orders_from_template(
    body: CreateLabOrderFromTemplateRequest,
    x_user_id: UUID | None = Header(None),
    x_user_role: str | None = Header(None),
    use_case: CreateOrdersFromTemplateUseCase = Depends(
        get_create_orders_from_template_use_case
    ),
):
    _require_user_id(x_user_id)
    _require_role(x_user_role, ["doctor", "admin"])
    try:
        return await use_case.execute(body)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.delete(
    "/lab-orders/{order_id}",
    status_code=204,
    summary="Delete a lab order (doctor: own only; admin: any)",
)
async def delete_lab_order(
    order_id: UUID,
    x_user_id: UUID | None = Header(None),
    x_user_role: str | None = Header(None),
    use_case: DeleteLabOrderUseCase = Depends(get_delete_order_use_case),
):
    caller_id = _require_user_id(x_user_id)
    caller_role = _require_role(x_user_role, ["doctor", "admin"])
    try:
        await use_case.execute(
            order_id=order_id, caller_id=caller_id, caller_role=caller_role
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc))


# ---------------------------------------------------------------------------
# Appointment Holistic (Cross-Result) AI Summary
# ---------------------------------------------------------------------------

@router.post(
    "/appointments/{appointment_id}/lab-summary/trigger",
    summary="Force trigger holistic AI analysis (ignores missing results)",
)
async def force_trigger_holistic_summary(
    appointment_id: UUID,
    x_user_id: UUID | None = Header(None),
    x_user_role: str | None = Header(None),
    order_repo: LabOrderRepository = Depends(get_order_repo),
    result_repo: LabResultRepository = Depends(get_result_repo),
    summary_repo=Depends(get_summary_repo),
    ai_client: AiServiceClient = Depends(get_ai_service_client),
):
    _require_user_id(x_user_id)
    _require_role(x_user_role, ["doctor", "admin"])

    orders = await order_repo.list_by_appointment_id(appointment_id)
    if not orders:
        raise HTTPException(status_code=400, detail="No orders found for this appointment.")

    order_ids = [o.id for o in orders]
    results = await result_repo.list_by_order_ids(order_ids)
    published_results = [r for r in results if r.status == LabResultStatus.PUBLISHED]

    if not published_results:
        raise HTTPException(status_code=400, detail="No published results available to summarize.")

    from Domain.entities.appointment_lab_summary import AppointmentLabSummary, AppointmentSummaryStatus
    import uuid

    existing = await summary_repo.get_by_appointment_id(appointment_id)
    summary = AppointmentLabSummary(
        id=existing.id if existing else uuid.uuid4(),
        appointment_id=appointment_id,
        patient_id=orders[0].patient_id,
        status=AppointmentSummaryStatus.PENDING,
        ai_holistic_text=None,
        total_results=len(published_results),
    )
    saved = await summary_repo.save(summary)
    
    import asyncio
    asyncio.create_task(
        ai_client.trigger_holistic_analysis(
            appointment_id=appointment_id,
            patient_id=orders[0].patient_id,
            summary_id=saved.id,
        )
    )
    return {"message": "Holistic analysis triggered", "summary_id": saved.id}


@router.get(
    "/appointments/{appointment_id}/lab-summary",
    response_model=AppointmentLabSummaryResponse,
    summary="Get holistic AI analysis for a completed appointment (all results combined)",
)
async def get_holistic_summary(
    appointment_id: UUID,
    x_user_id: UUID | None = Header(None),
    x_user_role: str | None = Header(None),
    use_case: GetHolisticSummaryUseCase = Depends(get_get_holistic_summary_use_case),
):
    _require_user_id(x_user_id)
    _require_role(x_user_role, ["doctor", "admin"])
    result = await use_case.execute(appointment_id)
    if result is None:
        raise HTTPException(status_code=404, detail="No holistic summary found for this appointment.")
    return result


@router.patch(
    "/appointments/{appointment_id}/lab-summary",
    response_model=AppointmentLabSummaryResponse,
    summary="(Internal) Update holistic summary text — called by AI Service only",
)
async def update_holistic_summary(
    appointment_id: UUID,
    body: UpdateHolisticSummaryRequest,
    x_user_role: str | None = Header(None),
    use_case: UpdateHolisticSummaryUseCase = Depends(get_update_holistic_summary_use_case),
):
    role = x_user_role or ""
    if role not in ("service", "admin"):
        raise HTTPException(status_code=403, detail="Only internal services may update the holistic summary.")
    try:
        return await use_case.execute(appointment_id, body)
    except LabResultNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.patch(
    "/appointments/{appointment_id}/lab-summary/review",
    response_model=AppointmentLabSummaryResponse,
    summary="Doctor adds clinical conclusion to the holistic AI summary",
)
async def review_holistic_summary(
    appointment_id: UUID,
    body: ReviewHolisticSummaryRequest,
    x_user_id: UUID | None = Header(None),
    x_user_role: str | None = Header(None),
    use_case: ReviewHolisticSummaryUseCase = Depends(get_review_holistic_summary_use_case),
):
    _require_user_id(x_user_id)
    _require_role(x_user_role, ["doctor", "admin"])
    try:
        return await use_case.execute(appointment_id, x_user_id, body)
    except LabResultNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
