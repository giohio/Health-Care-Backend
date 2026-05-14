"""Extra unit tests for EMR Result Service infrastructure components.

Covers:
- infrastructure/consumers/lab_payment_paid_consumer.py   (was 0%)
- infrastructure/messaging/publisher.py                   (was 0%)
- infrastructure/clients/ai_service_client.py             (was 47%)
- Application/use_cases/verify_and_publish.py             (extended coverage)
- Application/use_cases/lab_order_template.py             (was 33%)
"""
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tests.conftest import (
    FakeClinicalClient,
    FakeLabOrderRepo,
    FakeLabResultRepo,
    FakeNotificationClient,
    make_lab_order,
    make_lab_result,
)


# ===========================================================================
# LabPaymentPaidConsumer
# ===========================================================================

class TestLabPaymentPaidConsumer:
    """Tests for infrastructure/consumers/lab_payment_paid_consumer.py"""

    def _make_consumer(self):
        from infrastructure.consumers.lab_payment_paid_consumer import LabPaymentPaidConsumer
        connection = MagicMock()
        cache = MagicMock()

        class FakeBegin:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *_args):
                return None

        class FakeSession:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *_args):
                return None

            def begin(self):
                return FakeBegin()

        class FakeRepo:
            async def get_by_id(self, lab_order_id):
                return make_lab_order(id=lab_order_id)

            async def save(self, order):
                return order

        session_factory = MagicMock(return_value=FakeSession())
        order_repo_factory = MagicMock(return_value=FakeRepo())
        return LabPaymentPaidConsumer(connection, cache, session_factory, order_repo_factory)

    @pytest.mark.asyncio
    async def test_handle_valid_payload_logs_confirmation(self, caplog):
        consumer = self._make_consumer()
        payload = {
            "lab_order_id": str(uuid.uuid4()),
            "payment_id": str(uuid.uuid4()),
        }
        import logging
        with caplog.at_level(logging.INFO):
            await consumer.handle(payload)
        assert any("marked as PAID" in r.message for r in caplog.records)

    @pytest.mark.asyncio
    async def test_handle_missing_lab_order_id_returns_early(self, caplog):
        consumer = self._make_consumer()
        import logging
        with caplog.at_level(logging.WARNING):
            await consumer.handle({"payment_id": "some-id"})
        assert any("missing lab_order_id" in r.message for r in caplog.records)

    @pytest.mark.asyncio
    async def test_handle_invalid_uuid_returns_early(self, caplog):
        consumer = self._make_consumer()
        import logging
        with caplog.at_level(logging.WARNING):
            await consumer.handle({"lab_order_id": "not-a-uuid"})
        assert any("invalid lab_order_id" in r.message for r in caplog.records)

    @pytest.mark.asyncio
    async def test_handle_none_lab_order_id_returns_early(self, caplog):
        consumer = self._make_consumer()
        import logging
        with caplog.at_level(logging.WARNING):
            await consumer.handle({"lab_order_id": None})
        assert any("missing lab_order_id" in r.message for r in caplog.records)

    def test_consumer_queue_constant(self):
        from infrastructure.consumers.lab_payment_paid_consumer import LabPaymentPaidConsumer
        assert LabPaymentPaidConsumer.QUEUE == "emr.lab_payment_paid"
        assert LabPaymentPaidConsumer.EXCHANGE == "payment_events"
        assert LabPaymentPaidConsumer.ROUTING_KEY == "lab_payment.paid"


# ===========================================================================
# EmrEventPublisher
# ===========================================================================

class TestEmrEventPublisher:
    """Tests for infrastructure/messaging/publisher.py"""

    @pytest.mark.asyncio
    async def test_publish_delegates_to_inner_publisher(self):
        from infrastructure.messaging.publisher import EmrEventPublisher
        inner = MagicMock()
        inner.publish = AsyncMock()
        publisher = EmrEventPublisher(inner)

        await publisher.publish(
            event_type="lab_result.published",
            payload={"result_id": "abc"},
            exchange="lab_order_events",
            message_id="msg-1",
        )

        inner.publish.assert_called_once_with(
            exchange="lab_order_events",
            routing_key="lab_result.published",
            payload={"result_id": "abc"},
            message_id="msg-1",
        )

    @pytest.mark.asyncio
    async def test_publish_uses_default_exchange(self):
        from infrastructure.messaging.publisher import EmrEventPublisher
        inner = MagicMock()
        inner.publish = AsyncMock()
        publisher = EmrEventPublisher(inner)

        await publisher.publish(event_type="some.event", payload={})

        call_kwargs = inner.publish.call_args.kwargs
        assert call_kwargs["exchange"] == "lab_order_events"

    @pytest.mark.asyncio
    async def test_publish_without_message_id(self):
        from infrastructure.messaging.publisher import EmrEventPublisher
        inner = MagicMock()
        inner.publish = AsyncMock()
        publisher = EmrEventPublisher(inner)

        await publisher.publish(event_type="test.event", payload={"key": "val"})

        inner.publish.assert_called_once()
        call_kwargs = inner.publish.call_args.kwargs
        assert call_kwargs["message_id"] is None


# ===========================================================================
# AiServiceClient
# ===========================================================================

class TestAiServiceClient:
    """Tests for infrastructure/clients/ai_service_client.py"""

    @pytest.mark.asyncio
    async def test_trigger_lab_analysis_success(self):
        from infrastructure.clients.ai_service_client import AiServiceClient
        client = AiServiceClient()

        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as mock_cls:
            mock_http = AsyncMock()
            mock_http.__aenter__ = AsyncMock(return_value=mock_http)
            mock_http.__aexit__ = AsyncMock(return_value=None)
            mock_http.post = AsyncMock(return_value=mock_resp)
            mock_cls.return_value = mock_http

            await client.trigger_lab_analysis(
                result_id=uuid.uuid4(),
                patient_id=uuid.uuid4(),
                file_url="http://example.com/file.pdf",
                file_type="application/pdf",
                department="radiology",
                test_name="Chest X-Ray",
                auth_token="Bearer token123",
            )

            mock_http.post.assert_called_once()

    @pytest.mark.asyncio
    async def test_trigger_lab_analysis_tabular_input_type(self):
        from infrastructure.clients.ai_service_client import AiServiceClient
        client = AiServiceClient()

        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as mock_cls:
            mock_http = AsyncMock()
            mock_http.__aenter__ = AsyncMock(return_value=mock_http)
            mock_http.__aexit__ = AsyncMock(return_value=None)
            mock_http.post = AsyncMock(return_value=mock_resp)
            mock_cls.return_value = mock_http

            await client.trigger_lab_analysis(
                result_id=uuid.uuid4(),
                patient_id=uuid.uuid4(),
                file_url="http://example.com/data.json",
                file_type="tabular",
                department="lab",
                test_name="CBC",
                auth_token="token",
            )

            call_json = mock_http.post.call_args.kwargs["json"]
            assert call_json["input_type"] == "tabular"

    @pytest.mark.asyncio
    async def test_trigger_lab_analysis_image_input_type(self):
        from infrastructure.clients.ai_service_client import AiServiceClient
        client = AiServiceClient()

        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as mock_cls:
            mock_http = AsyncMock()
            mock_http.__aenter__ = AsyncMock(return_value=mock_http)
            mock_http.__aexit__ = AsyncMock(return_value=None)
            mock_http.post = AsyncMock(return_value=mock_resp)
            mock_cls.return_value = mock_http

            await client.trigger_lab_analysis(
                result_id=uuid.uuid4(),
                patient_id=uuid.uuid4(),
                file_url="http://example.com/xray.jpg",
                file_type="image/jpeg",
                department="radiology",
                test_name="X-Ray",
                auth_token="token",
            )

            call_json = mock_http.post.call_args.kwargs["json"]
            assert call_json["input_type"] == "image"

    @pytest.mark.asyncio
    async def test_trigger_lab_analysis_failure_is_swallowed(self, caplog):
        """Errors must never propagate — they are logged as warnings."""
        from infrastructure.clients.ai_service_client import AiServiceClient
        import logging
        client = AiServiceClient()

        with patch("httpx.AsyncClient") as mock_cls:
            mock_http = AsyncMock()
            mock_http.__aenter__ = AsyncMock(return_value=mock_http)
            mock_http.__aexit__ = AsyncMock(return_value=None)
            mock_http.post = AsyncMock(side_effect=Exception("connection refused"))
            mock_cls.return_value = mock_http

            with caplog.at_level(logging.WARNING):
                # Must NOT raise
                await client.trigger_lab_analysis(
                    result_id=uuid.uuid4(),
                    patient_id=uuid.uuid4(),
                    file_url="http://fail.example.com/file.pdf",
                    file_type="application/pdf",
                    department="radiology",
                    test_name="X-Ray",
                    auth_token="token",
                )
            assert any("non-fatal" in r.message for r in caplog.records)

    @pytest.mark.asyncio
    async def test_trigger_lab_analysis_empty_department_defaults(self):
        from infrastructure.clients.ai_service_client import AiServiceClient
        client = AiServiceClient()

        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as mock_cls:
            mock_http = AsyncMock()
            mock_http.__aenter__ = AsyncMock(return_value=mock_http)
            mock_http.__aexit__ = AsyncMock(return_value=None)
            mock_http.post = AsyncMock(return_value=mock_resp)
            mock_cls.return_value = mock_http

            await client.trigger_lab_analysis(
                result_id=uuid.uuid4(),
                patient_id=uuid.uuid4(),
                file_url="http://example.com/file.pdf",
                file_type="pdf",
                department="",   # empty → defaults to internal_medicine
                test_name="CBC",
                auth_token="token",
            )

            call_json = mock_http.post.call_args.kwargs["json"]
            assert call_json["department"] == "internal_medicine"

    @pytest.mark.asyncio
    async def test_trigger_holistic_analysis_success(self):
        from infrastructure.clients.ai_service_client import AiServiceClient
        client = AiServiceClient()

        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        appointment_id = uuid.uuid4()
        patient_id = uuid.uuid4()
        summary_id = uuid.uuid4()

        with patch("httpx.AsyncClient") as mock_cls:
            mock_http = AsyncMock()
            mock_http.__aenter__ = AsyncMock(return_value=mock_http)
            mock_http.__aexit__ = AsyncMock(return_value=None)
            mock_http.post = AsyncMock(return_value=mock_resp)
            mock_cls.return_value = mock_http

            await client.trigger_holistic_analysis(appointment_id, patient_id, summary_id)

            call = mock_http.post.call_args
            assert call.kwargs["json"] == {
                "appointment_id": str(appointment_id),
                "patient_id": str(patient_id),
                "summary_id": str(summary_id),
            }
            assert call.kwargs["headers"] == {"X-User-Role": "service"}

    @pytest.mark.asyncio
    async def test_trigger_holistic_analysis_failure_is_non_fatal(self, caplog):
        from infrastructure.clients.ai_service_client import AiServiceClient
        import logging
        client = AiServiceClient()

        with patch("httpx.AsyncClient") as mock_cls:
            mock_http = AsyncMock()
            mock_http.__aenter__ = AsyncMock(return_value=mock_http)
            mock_http.__aexit__ = AsyncMock(return_value=None)
            mock_http.post = AsyncMock(side_effect=RuntimeError("ai service down"))
            mock_cls.return_value = mock_http

            with caplog.at_level(logging.WARNING):
                await client.trigger_holistic_analysis(uuid.uuid4(), uuid.uuid4(), uuid.uuid4())

        assert any("non-fatal" in record.message for record in caplog.records)


# ===========================================================================
# VerifyAndPublishUseCase — extended coverage for uncovered branches
# ===========================================================================

class TestVerifyAndPublishExtended:
    """Tests targeting the previously-uncovered branches in verify_and_publish.py."""

    def _make_use_case(self, result_repo, order_repo, notif=None, clinical=None, publisher=None):
        from Application.use_cases.verify_and_publish import VerifyAndPublishUseCase
        return VerifyAndPublishUseCase(
            result_repo=result_repo,
            order_repo=order_repo,
            notification_client=notif or FakeNotificationClient(),
            clinical_client=clinical or FakeClinicalClient(),
            event_publisher=publisher,
        )

    @pytest.mark.asyncio
    async def test_publish_event_emitted_on_success(self):
        from Domain.value_objects.lab_result_status import LabResultStatus
        result_repo = FakeLabResultRepo()
        order_repo = FakeLabOrderRepo()

        order = make_lab_order()
        result = make_lab_result(
            order_id=order.id,
            patient_id=order.patient_id,
            doctor_id=order.doctor_id,
            status=LabResultStatus.DOCTOR_REVIEW,
        )
        await result_repo.save(result)
        await order_repo.save(order)

        mock_publisher = MagicMock()
        mock_publisher.publish = AsyncMock()

        from Application.dtos import VerifyLabResultRequest
        request = VerifyLabResultRequest(
            doctor_notes="Looks normal",
            published_text="All clear",
            published_findings=[{"wbc": "normal"}],
        )

        use_case = self._make_use_case(result_repo, order_repo, publisher=mock_publisher)
        await use_case.execute(result.id, order.doctor_id, request)

        mock_publisher.publish.assert_called()
        call_kwargs = mock_publisher.publish.call_args_list[0].kwargs
        assert call_kwargs["event_type"] == "lab_result.published"

    @pytest.mark.asyncio
    async def test_all_results_ready_event_emitted_when_all_published(self):
        """When all orders for an appointment have published results, emit all_results_ready."""
        from Domain.value_objects.lab_result_status import LabResultStatus
        from Application.dtos import VerifyLabResultRequest

        appointment_id = uuid.uuid4()
        patient_id = uuid.uuid4()
        doctor_id = uuid.uuid4()

        order = make_lab_order(appointment_id=appointment_id, patient_id=patient_id, doctor_id=doctor_id)

        result_repo = FakeLabResultRepo()
        order_repo = FakeLabOrderRepo()
        await order_repo.save(order)

        result = make_lab_result(
            order_id=order.id,
            patient_id=patient_id,
            doctor_id=doctor_id,
            status=LabResultStatus.DOCTOR_REVIEW,
        )
        await result_repo.save(result)

        mock_publisher = MagicMock()
        mock_publisher.publish = AsyncMock()

        request = VerifyLabResultRequest(
            doctor_notes="ok",
            published_text="normal",
            published_findings=None,
        )

        use_case = self._make_use_case(result_repo, order_repo, publisher=mock_publisher)
        await use_case.execute(result.id, doctor_id, request)

        event_types = [c.kwargs["event_type"] for c in mock_publisher.publish.call_args_list]
        assert "lab_order.all_results_ready" in event_types

    @pytest.mark.asyncio
    async def test_no_publisher_skips_event_emission(self):
        """When publisher is None, execution must not raise."""
        from Domain.value_objects.lab_result_status import LabResultStatus
        from Application.dtos import VerifyLabResultRequest

        result_repo = FakeLabResultRepo()
        order_repo = FakeLabOrderRepo()

        order = make_lab_order()
        result = make_lab_result(
            order_id=order.id, patient_id=order.patient_id, doctor_id=order.doctor_id,
            status=LabResultStatus.DOCTOR_REVIEW
        )
        await result_repo.save(result)
        await order_repo.save(order)

        request = VerifyLabResultRequest(doctor_notes="", published_text="", published_findings=None)
        use_case = self._make_use_case(result_repo, order_repo, publisher=None)
        # Must not raise
        resp = await use_case.execute(result.id, order.doctor_id, request)
        assert resp is not None

    @pytest.mark.asyncio
    async def test_order_without_appointment_id_skips_all_results_check(self):
        """Order with no appointment_id should not attempt all_results_ready emission."""
        from Domain.value_objects.lab_result_status import LabResultStatus
        from Application.dtos import VerifyLabResultRequest

        result_repo = FakeLabResultRepo()
        order_repo = FakeLabOrderRepo()

        order = make_lab_order(appointment_id=None)
        result = make_lab_result(
            order_id=order.id, patient_id=order.patient_id, doctor_id=order.doctor_id,
            status=LabResultStatus.DOCTOR_REVIEW
        )
        await result_repo.save(result)
        await order_repo.save(order)

        mock_publisher = MagicMock()
        mock_publisher.publish = AsyncMock()

        request = VerifyLabResultRequest(doctor_notes="", published_text="", published_findings=None)
        use_case = self._make_use_case(result_repo, order_repo, publisher=mock_publisher)
        await use_case.execute(result.id, order.doctor_id, request)

        # Only lab_result.published should have been emitted, NOT all_results_ready
        event_types = [c.kwargs["event_type"] for c in mock_publisher.publish.call_args_list]
        assert "lab_order.all_results_ready" not in event_types

    @pytest.mark.asyncio
    async def test_not_all_results_published_does_not_emit_all_ready(self):
        """Two orders for same appointment, but only one is published → no all_results_ready."""
        from Domain.value_objects.lab_result_status import LabResultStatus
        from Application.dtos import VerifyLabResultRequest

        appointment_id = uuid.uuid4()
        patient_id = uuid.uuid4()
        doctor_id = uuid.uuid4()

        order1 = make_lab_order(appointment_id=appointment_id, patient_id=patient_id, doctor_id=doctor_id)
        order2 = make_lab_order(appointment_id=appointment_id, patient_id=patient_id, doctor_id=doctor_id)

        result_repo = FakeLabResultRepo()
        order_repo = FakeLabOrderRepo()
        await order_repo.save(order1)
        await order_repo.save(order2)

        result1 = make_lab_result(
            order_id=order1.id, patient_id=patient_id, doctor_id=doctor_id,
            status=LabResultStatus.DOCTOR_REVIEW,
        )
        # result2 still pending (not in result_repo)
        await result_repo.save(result1)

        mock_publisher = MagicMock()
        mock_publisher.publish = AsyncMock()

        request = VerifyLabResultRequest(doctor_notes="", published_text="", published_findings=None)
        use_case = self._make_use_case(result_repo, order_repo, publisher=mock_publisher)
        await use_case.execute(result1.id, doctor_id, request)

        event_types = [c.kwargs["event_type"] for c in mock_publisher.publish.call_args_list]
        assert "lab_order.all_results_ready" not in event_types


# ===========================================================================
# Lab order template use cases
# ===========================================================================

class TestLabOrderTemplateUseCases:
    """Tests for Application/use_cases/lab_order_template.py"""

    def _make_fake_template_repo(self):
        import dataclasses
        from Domain.entities.lab_order_template import TemplateCreatorType

        class FakeTemplateRepo:
            def __init__(self):
                self._store = {}

            async def save(self, template):
                # LabOrderTemplateResponse.test_items expects List[Dict[str,Any]].
                # Convert dataclass TemplateTestItem instances to plain dicts so
                # that Pydantic model_validate(saved, from_attributes=True) works.
                if template.test_items and dataclasses.is_dataclass(template.test_items[0]):
                    template.test_items = [
                        dataclasses.asdict(item) for item in template.test_items
                    ]
                self._store[template.id] = template
                return template

            async def get_by_id(self, template_id):
                return self._store.get(template_id)

            async def list_system(self, department=None):
                results = [t for t in self._store.values()
                           if t.creator_type == TemplateCreatorType.SYSTEM]
                if department:
                    results = [t for t in results if t.department == department]
                return results

            async def list_for_doctor(self, doctor_id, department=None):
                results = [
                    t for t in self._store.values()
                    if t.creator_type == TemplateCreatorType.SYSTEM
                    or t.creator_id == doctor_id
                ]
                if department:
                    results = [t for t in results if t.department == department]
                return results

            async def delete(self, template_id):
                self._store.pop(template_id, None)

        return FakeTemplateRepo()

    def _make_fake_order_repo(self):
        class FakeOrderRepo:
            def __init__(self):
                self._store = {}

            async def save(self, order):
                self._store[order.id] = order
                return order

            async def get_by_id(self, order_id):
                return self._store.get(order_id)

            async def list(self, **kwargs):
                return list(self._store.values())

            async def list_by_appointment_id(self, appointment_id):
                return [o for o in self._store.values() if o.appointment_id == appointment_id]

        return FakeOrderRepo()

    @pytest.mark.asyncio
    async def test_create_template_as_admin_creates_system_template(self):
        from Application.use_cases.lab_order_template import CreateLabOrderTemplateUseCase
        from Application.dtos import CreateLabOrderTemplateRequest, TemplateTestItemRequest
        from Domain.entities.lab_order_template import TemplateCreatorType

        repo = self._make_fake_template_repo()
        use_case = CreateLabOrderTemplateUseCase(repo)

        request = CreateLabOrderTemplateRequest(
            name="Standard Blood Panel",
            description="Routine blood tests",
            department="internal_medicine",
            test_items=[
                TemplateTestItemRequest(
                    test_name="CBC",
                    test_type="BLOOD_PANEL",
                    instructions=None,
                    priority="ROUTINE",
                )
            ],
        )
        result = await use_case.execute(request, creator_id=uuid.uuid4(), creator_role="admin")
        assert result.name == "Standard Blood Panel"

    @pytest.mark.asyncio
    async def test_create_template_as_doctor_creates_personal_template(self):
        from Application.use_cases.lab_order_template import CreateLabOrderTemplateUseCase
        from Application.dtos import CreateLabOrderTemplateRequest, TemplateTestItemRequest

        repo = self._make_fake_template_repo()
        use_case = CreateLabOrderTemplateUseCase(repo)
        doctor_id = uuid.uuid4()

        request = CreateLabOrderTemplateRequest(
            name="My CBC Template",
            description=None,
            department="lab",
            test_items=[
                TemplateTestItemRequest(
                    test_name="CBC",
                    test_type="BLOOD_PANEL",
                    instructions="Fasting required",
                    priority="ROUTINE",
                )
            ],
        )
        result = await use_case.execute(request, creator_id=doctor_id, creator_role="doctor")
        assert result.name == "My CBC Template"

    @pytest.mark.asyncio
    async def test_list_templates_as_admin_returns_system_templates(self):
        from Application.use_cases.lab_order_template import (
            CreateLabOrderTemplateUseCase,
            ListLabOrderTemplatesUseCase,
        )
        from Application.dtos import CreateLabOrderTemplateRequest, TemplateTestItemRequest

        repo = self._make_fake_template_repo()
        creator = CreateLabOrderTemplateUseCase(repo)
        lister = ListLabOrderTemplatesUseCase(repo)

        req = CreateLabOrderTemplateRequest(
            name="Admin Template",
            description=None,
            department="radiology",
            test_items=[
                TemplateTestItemRequest(test_name="X-Ray", test_type="IMAGING", instructions=None, priority="ROUTINE")
            ],
        )
        await creator.execute(req, creator_id=uuid.uuid4(), creator_role="admin")

        results = await lister.execute(caller_id=uuid.uuid4(), caller_role="admin")
        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_list_templates_as_doctor_returns_own_and_system(self):
        from Application.use_cases.lab_order_template import (
            CreateLabOrderTemplateUseCase,
            ListLabOrderTemplatesUseCase,
        )
        from Application.dtos import CreateLabOrderTemplateRequest, TemplateTestItemRequest

        repo = self._make_fake_template_repo()
        creator = CreateLabOrderTemplateUseCase(repo)
        lister = ListLabOrderTemplatesUseCase(repo)
        doctor_id = uuid.uuid4()

        # Create one system template
        req_sys = CreateLabOrderTemplateRequest(
            name="System Template", description=None, department="lab",
            test_items=[TemplateTestItemRequest(test_name="CBC", test_type="BLOOD_PANEL", instructions=None, priority="ROUTINE")]
        )
        await creator.execute(req_sys, creator_id=uuid.uuid4(), creator_role="admin")

        # Create one personal template for this doctor
        req_personal = CreateLabOrderTemplateRequest(
            name="My Template", description=None, department="lab",
            test_items=[TemplateTestItemRequest(test_name="LFT", test_type="BLOOD_PANEL", instructions=None, priority="ROUTINE")]
        )
        await creator.execute(req_personal, creator_id=doctor_id, creator_role="doctor")

        results = await lister.execute(caller_id=doctor_id, caller_role="doctor")
        assert len(results) == 2

    @pytest.mark.asyncio
    async def test_delete_template_as_admin_succeeds(self):
        from Application.use_cases.lab_order_template import (
            CreateLabOrderTemplateUseCase,
            DeleteLabOrderTemplateUseCase,
        )
        from Application.dtos import CreateLabOrderTemplateRequest, TemplateTestItemRequest

        repo = self._make_fake_template_repo()
        creator = CreateLabOrderTemplateUseCase(repo)
        deleter = DeleteLabOrderTemplateUseCase(repo)

        req = CreateLabOrderTemplateRequest(
            name="To Delete", description=None, department="lab",
            test_items=[TemplateTestItemRequest(test_name="CBC", test_type="BLOOD_PANEL", instructions=None, priority="ROUTINE")]
        )
        created = await creator.execute(req, creator_id=uuid.uuid4(), creator_role="admin")
        # Admin can delete any template
        await deleter.execute(uuid.UUID(str(created.id)), caller_id=uuid.uuid4(), caller_role="admin")
        assert await repo.get_by_id(uuid.UUID(str(created.id))) is None

    @pytest.mark.asyncio
    async def test_delete_template_not_found_raises_error(self):
        from Application.use_cases.lab_order_template import DeleteLabOrderTemplateUseCase

        repo = self._make_fake_template_repo()
        deleter = DeleteLabOrderTemplateUseCase(repo)
        with pytest.raises(ValueError, match="not found"):
            await deleter.execute(uuid.uuid4(), caller_id=uuid.uuid4(), caller_role="admin")

    @pytest.mark.asyncio
    async def test_delete_system_template_as_doctor_raises_permission_error(self):
        from Application.use_cases.lab_order_template import (
            CreateLabOrderTemplateUseCase,
            DeleteLabOrderTemplateUseCase,
        )
        from Application.dtos import CreateLabOrderTemplateRequest, TemplateTestItemRequest

        repo = self._make_fake_template_repo()
        creator = CreateLabOrderTemplateUseCase(repo)
        deleter = DeleteLabOrderTemplateUseCase(repo)

        req = CreateLabOrderTemplateRequest(
            name="System Only", description=None, department="lab",
            test_items=[TemplateTestItemRequest(test_name="CBC", test_type="BLOOD_PANEL", instructions=None, priority="ROUTINE")]
        )
        created = await creator.execute(req, creator_id=uuid.uuid4(), creator_role="admin")
        with pytest.raises(PermissionError, match="SYSTEM"):
            await deleter.execute(uuid.UUID(str(created.id)), caller_id=uuid.uuid4(), caller_role="doctor")

    @pytest.mark.asyncio
    async def test_delete_another_doctors_template_raises_permission_error(self):
        from Application.use_cases.lab_order_template import (
            CreateLabOrderTemplateUseCase,
            DeleteLabOrderTemplateUseCase,
        )
        from Application.dtos import CreateLabOrderTemplateRequest, TemplateTestItemRequest

        repo = self._make_fake_template_repo()
        creator = CreateLabOrderTemplateUseCase(repo)
        deleter = DeleteLabOrderTemplateUseCase(repo)

        owner_id = uuid.uuid4()
        other_id = uuid.uuid4()

        req = CreateLabOrderTemplateRequest(
            name="Private", description=None, department="lab",
            test_items=[TemplateTestItemRequest(test_name="LFT", test_type="BLOOD_PANEL", instructions=None, priority="ROUTINE")]
        )
        created = await creator.execute(req, creator_id=owner_id, creator_role="doctor")
        with pytest.raises(PermissionError, match="another doctor"):
            await deleter.execute(uuid.UUID(str(created.id)), caller_id=other_id, caller_role="doctor")

    @pytest.mark.asyncio
    async def test_create_orders_from_template_creates_lab_orders(self):
        """CreateOrdersFromTemplateUseCase reads item.test_type from TemplateTestItem objects.
        Use a raw repo (no dict conversion) with the domain entity injected directly.
        """
        from Application.use_cases.lab_order_template import CreateOrdersFromTemplateUseCase
        from Application.dtos import CreateLabOrderFromTemplateRequest
        from Domain.entities.lab_order_template import LabOrderTemplate, TemplateCreatorType, TemplateTestItem

        template_id = uuid.uuid4()

        # Raw repo: stores TemplateTestItem objects unchanged (no dict conversion)
        class RawTemplateRepo:
            def __init__(self, template):
                self._store = {template.id: template}

            async def get_by_id(self, tid):
                return self._store.get(tid)

        template = LabOrderTemplate(
            id=template_id,
            name="Multi-test",
            description=None,
            department="lab",
            test_items=[
                TemplateTestItem(test_name="CBC", test_type="BLOOD_PANEL", instructions=None, priority="ROUTINE"),
                TemplateTestItem(test_name="LFT", test_type="BLOOD_PANEL", instructions=None, priority="URGENT"),
            ],
            creator_type=TemplateCreatorType.SYSTEM,
            creator_id=None,
        )

        order_repo = self._make_fake_order_repo()
        use_case = CreateOrdersFromTemplateUseCase(RawTemplateRepo(template), order_repo)

        patient_id = uuid.uuid4()
        doctor_id = uuid.uuid4()
        req_order = CreateLabOrderFromTemplateRequest(
            template_id=template_id,
            patient_id=patient_id,
            doctor_id=doctor_id,
            appointment_id=uuid.uuid4(),
        )
        orders = await use_case.execute(req_order)
        assert len(orders) == 2
        test_names = {o.test_name for o in orders}
        assert "CBC" in test_names
        assert "LFT" in test_names

    @pytest.mark.asyncio
    async def test_create_orders_from_template_not_found_raises_error(self):
        from Application.use_cases.lab_order_template import CreateOrdersFromTemplateUseCase
        from Application.dtos import CreateLabOrderFromTemplateRequest

        template_repo = self._make_fake_template_repo()
        order_repo = self._make_fake_order_repo()
        use_case = CreateOrdersFromTemplateUseCase(template_repo, order_repo)

        req = CreateLabOrderFromTemplateRequest(
            template_id=uuid.uuid4(),
            patient_id=uuid.uuid4(),
            doctor_id=uuid.uuid4(),
            appointment_id=uuid.uuid4(),
        )
        with pytest.raises(ValueError, match="not found"):
            await use_case.execute(req)
