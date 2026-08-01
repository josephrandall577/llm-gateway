"""Failure-path coverage for initial request logs."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from starlette.requests import Request

from app.api.proxy.openai import _handle_proxy_request_with_body
from app.common.errors import ServiceError
from app.common.time import utc_now
from app.domain.model import ModelMapping
from app.providers.base import ProviderResponse
from app.rules.models import CandidateProvider
from app.services.active_requests import active_requests
from app.services.proxy_service import ProxyService


def _service_with_resolution_failure() -> ProxyService:
    service = ProxyService(
        model_repo=AsyncMock(),
        provider_repo=AsyncMock(),
        log_repo=AsyncMock(),
    )
    service.log_repo.create_initial.return_value = 42
    service._resolve_candidates = AsyncMock(  # type: ignore[method-assign]
        side_effect=ServiceError("No providers", code="no_available_provider")
    )
    return service


@pytest.mark.asyncio
@pytest.mark.parametrize("stream", [False, True])
async def test_resolution_failure_completes_initial_log(stream):
    service = _service_with_resolution_failure()
    method = (
        service.process_request_stream if stream else service.process_request
    )

    with pytest.raises(ServiceError):
        await method(
            api_key_id=1,
            api_key_name="key",
            request_protocol="openai",
            path="/v1/chat/completions",
            request_url="/v1/chat/completions",
            method="POST",
            headers={},
            body={"model": "test-model", "messages": []},
        )

    service.log_repo.create_initial.assert_awaited_once()
    service.log_repo.update.assert_awaited_once()
    log_id, log_data = service.log_repo.update.await_args.args
    assert log_id == 42
    assert log_data.is_completed is True
    assert log_data.response_status == 503
    assert log_data.error_info == "No providers"
    assert await active_requests.is_active(42) is False


@pytest.mark.asyncio
async def test_all_provider_failures_still_complete_initial_log():
    class RetrySettings:
        RETRY_MAX_ATTEMPTS = 1
        RETRY_DELAY_MS = 0

    now = utc_now()
    mapping = ModelMapping(
        requested_model="test-model",
        strategy="round_robin",
        matching_rules=None,
        capabilities=None,
        is_active=True,
        created_at=now,
        updated_at=now,
    )
    candidate = CandidateProvider(
        provider_id=1,
        provider_name="broken-provider",
        base_url="https://example.com",
        protocol="openai",
        api_key="test-key",
        target_model="target-model",
        priority=0,
        weight=1,
    )
    service = ProxyService(
        model_repo=AsyncMock(),
        provider_repo=AsyncMock(),
        log_repo=AsyncMock(),
    )
    service.log_repo.create_initial.return_value = 43
    service._resolve_candidates = AsyncMock(  # type: ignore[method-assign]
        return_value=(mapping, [candidate], 0, "openai", {})
    )
    client = AsyncMock()
    client.forward.return_value = ProviderResponse(
        status_code=503,
        error="upstream unavailable",
    )

    with (
        patch(
            "app.services.retry_handler.get_settings",
            return_value=RetrySettings(),
        ),
        patch(
            "app.services.proxy_service.convert_request_for_supplier",
            return_value=("/v1/chat/completions", {"model": "target-model"}),
        ),
        patch(
            "app.services.proxy_service.get_provider_client",
            return_value=client,
        ),
    ):
        response, _ = await service.process_request(
            api_key_id=1,
            api_key_name="key",
            request_protocol="openai",
            path="/v1/chat/completions",
            request_url="/v1/chat/completions",
            method="POST",
            headers={},
            body={"model": "test-model", "messages": []},
        )

    assert response.status_code == 503
    service.log_repo.update.assert_awaited_once()
    log_id, log_data = service.log_repo.update.await_args.args
    assert log_id == 43
    assert log_data.is_completed is True
    assert log_data.response_status == 503
    assert log_data.error_info == "upstream unavailable"
    assert await active_requests.is_active(43) is False


@pytest.mark.asyncio
@pytest.mark.parametrize("stream", [False, True])
async def test_task_cancellation_completes_initial_log(stream):
    service = ProxyService(
        model_repo=AsyncMock(),
        provider_repo=AsyncMock(),
        log_repo=AsyncMock(),
    )
    service.log_repo.create_initial.return_value = 44
    started = asyncio.Event()
    finalized = asyncio.Event()

    async def cancel_log(*_args):
        finalized.set()

    service.log_repo.cancel.side_effect = cancel_log

    async def wait_forever(**_kwargs):
        started.set()
        await asyncio.Event().wait()

    service._resolve_candidates = wait_forever  # type: ignore[method-assign]
    method = service.process_request_stream if stream else service.process_request
    task = asyncio.create_task(
        method(
            api_key_id=1,
            api_key_name="key",
            request_protocol="openai",
            path="/v1/chat/completions",
            request_url="/v1/chat/completions",
            method="POST",
            headers={},
            body={"model": "test-model", "messages": [], "stream": stream},
        )
    )
    await started.wait()
    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task
    await asyncio.wait_for(finalized.wait(), timeout=1)

    service.log_repo.cancel.assert_awaited_once_with(44, "client_disconnected")
    assert await active_requests.is_active(44) is False


@pytest.mark.asyncio
@pytest.mark.parametrize("stream", [False, True])
async def test_task_cancellation_during_initial_log_creation_completes_log(stream):
    service = ProxyService(
        model_repo=AsyncMock(),
        provider_repo=AsyncMock(),
        log_repo=AsyncMock(),
    )
    creation_started = asyncio.Event()
    allow_creation = asyncio.Event()
    finalized = asyncio.Event()

    async def create_initial(_log_data):
        creation_started.set()
        await allow_creation.wait()
        return 45

    async def cancel_log(*_args):
        finalized.set()

    service.log_repo.create_initial.side_effect = create_initial
    service.log_repo.cancel.side_effect = cancel_log
    method = service.process_request_stream if stream else service.process_request
    task = asyncio.create_task(
        method(
            api_key_id=1,
            api_key_name="key",
            request_protocol="openai",
            path="/v1/chat/completions",
            request_url="/v1/chat/completions",
            method="POST",
            headers={},
            body={"model": "test-model", "messages": [], "stream": stream},
        )
    )
    await creation_started.wait()
    task.cancel()
    allow_creation.set()

    with pytest.raises(asyncio.CancelledError):
        await task
    await asyncio.wait_for(finalized.wait(), timeout=1)

    service.log_repo.cancel.assert_awaited_once_with(45, "client_disconnected")
    assert await active_requests.is_active(45) is False


@pytest.mark.asyncio
async def test_openai_proxy_cancels_work_when_client_disconnects():
    started = asyncio.Event()
    stopped = asyncio.Event()

    class BlockingService:
        async def process_request(self, **_kwargs):
            started.set()
            try:
                await asyncio.Event().wait()
            finally:
                stopped.set()

    async def receive():
        return {"type": "http.disconnect"}

    request = Request(
        {
            "type": "http",
            "asgi": {"version": "3.0", "spec_version": "2.3"},
            "method": "POST",
            "scheme": "http",
            "path": "/v1/chat/completions",
            "raw_path": b"/v1/chat/completions",
            "query_string": b"",
            "headers": [],
            "server": ("testserver", 80),
            "client": ("testclient", 50000),
        },
        receive,
    )
    task = asyncio.create_task(
        _handle_proxy_request_with_body(
            request,
            SimpleNamespace(id=1, key_name="key", record_details=True),
            BlockingService(),
            "/v1/chat/completions",
            {"model": "test-model", "messages": []},
        )
    )
    try:
        await started.wait()
        await asyncio.wait_for(stopped.wait(), timeout=1)
        with pytest.raises(asyncio.CancelledError):
            await task
    finally:
        if not task.done():
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
