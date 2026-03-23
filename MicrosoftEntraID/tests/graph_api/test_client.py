from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from msgraph_beta.generated.models.sign_in import SignIn

from graph_api.client import GraphApi, SIGNIN_EVENT_TYPES


@pytest.mark.asyncio
async def test_client_get_signins(graph_api_client: GraphApi, signins_page_1, signins_page_2) -> None:
    # Only the first event type query returns data; the other two return empty
    empty_page = SimpleNamespace(value=[], odata_next_link=None)
    graph_api_client._beta_client.audit_logs.sign_ins.get.side_effect = [signins_page_1, empty_page, empty_page]
    graph_api_client._beta_client.audit_logs.sign_ins.with_url.return_value.get.return_value = signins_page_2

    items = [
        x
        async for x in graph_api_client.get_signin_logs(
            datetime.fromisoformat("2025-09-01T00:00:00").replace(tzinfo=timezone.utc)
        )
    ]

    assert [i.id for i in items] == ["0", "1", "2"]
    assert items[0].user_principal_name == "u1@example.com"
    assert items[2].ip_address == "2.2.2.2"


@pytest.mark.asyncio
async def test_client_get_signins_empty(graph_api_client: GraphApi) -> None:
    graph_api_client._beta_client.audit_logs.sign_ins.get.return_value = None

    items = [
        x
        async for x in graph_api_client.get_signin_logs(
            datetime.fromisoformat("2025-09-01T00:00:00").replace(tzinfo=timezone.utc)
        )
    ]

    assert [] == items


@pytest.mark.asyncio
async def test_client_get_signins_empty_1(graph_api_client: GraphApi, signins_page_1) -> None:
    # Only the first event type query returns data; the other two return empty
    empty_page = SimpleNamespace(value=[], odata_next_link=None)
    graph_api_client._beta_client.audit_logs.sign_ins.get.side_effect = [signins_page_1, empty_page, empty_page]
    graph_api_client._beta_client.audit_logs.sign_ins.with_url.return_value.get.return_value = None

    items = [
        x
        async for x in graph_api_client.get_signin_logs(
            datetime.fromisoformat("2025-09-01T00:00:00").replace(tzinfo=timezone.utc)
        )
    ]

    assert [i.id for i in items] == ["0", "1"]
    assert items[0].user_principal_name == "u1@example.com"


@pytest.mark.asyncio
async def test_client_get_directory_audits(
    graph_api_client: GraphApi, directory_audits_page_1, directory_audits_page_2
) -> None:
    graph_api_client._client.audit_logs.directory_audits.get.return_value = directory_audits_page_1
    graph_api_client._client.audit_logs.directory_audits.with_url.return_value.get.return_value = (
        directory_audits_page_2
    )

    items = [
        x
        async for x in graph_api_client.get_directory_audit_logs(
            datetime.fromisoformat("2025-09-01T00:00:00").replace(tzinfo=timezone.utc)
        )
    ]

    assert [i.id for i in items] == ["3", "4", "5"]
    assert items[0].activity_display_name == "Add user"
    assert items[1].initiated_by.user.display_name == "Admin2"


@pytest.mark.asyncio
async def test_client_get_directory_audits_empty(graph_api_client: GraphApi) -> None:
    graph_api_client._client.audit_logs.directory_audits.get.return_value = None

    items = [
        x
        async for x in graph_api_client.get_directory_audit_logs(
            datetime.fromisoformat("2025-09-01T00:00:00").replace(tzinfo=timezone.utc)
        )
    ]

    assert [] == items


@pytest.mark.asyncio
async def test_client_get_directory_audits_empty_1(graph_api_client: GraphApi, directory_audits_page_1) -> None:
    graph_api_client._client.audit_logs.directory_audits.get.return_value = directory_audits_page_1
    graph_api_client._client.audit_logs.directory_audits.with_url.return_value.get.return_value = None

    items = [
        x
        async for x in graph_api_client.get_directory_audit_logs(
            datetime.fromisoformat("2025-09-01T00:00:00").replace(tzinfo=timezone.utc)
        )
    ]

    assert [i.id for i in items] == ["3"]
    assert items[0].activity_display_name == "Add user"


@pytest.mark.asyncio
async def test_signins_use_beta_client_not_v1(graph_api_client: GraphApi) -> None:
    """Sign-in queries must go through beta_client, not the v1.0 client."""
    graph_api_client._beta_client.audit_logs.sign_ins.get.return_value = None

    _ = [
        x
        async for x in graph_api_client.get_signin_logs(
            datetime.fromisoformat("2025-09-01T00:00:00").replace(tzinfo=timezone.utc)
        )
    ]

    # beta_client was called 3 times (once per event type query)
    assert graph_api_client._beta_client.audit_logs.sign_ins.get.call_count == 3
    # v1.0 client sign_ins was never touched
    graph_api_client._client.audit_logs.sign_ins.get.assert_not_called()


@pytest.mark.asyncio
async def test_directory_audits_use_v1_client_not_beta(graph_api_client: GraphApi) -> None:
    """Directory audit queries must go through the v1.0 client, not beta."""
    graph_api_client._client.audit_logs.directory_audits.get.return_value = None

    _ = [
        x
        async for x in graph_api_client.get_directory_audit_logs(
            datetime.fromisoformat("2025-09-01T00:00:00").replace(tzinfo=timezone.utc)
        )
    ]

    graph_api_client._client.audit_logs.directory_audits.get.assert_called_once()


@pytest.mark.asyncio
async def test_signins_queries_all_event_types(graph_api_client: GraphApi) -> None:
    """get_signin_logs must issue one query per event type filter."""
    graph_api_client._beta_client.audit_logs.sign_ins.get.return_value = None

    _ = [
        x
        async for x in graph_api_client.get_signin_logs(
            datetime.fromisoformat("2025-09-01T00:00:00").replace(tzinfo=timezone.utc)
        )
    ]

    calls = graph_api_client._beta_client.audit_logs.sign_ins.get.call_args_list
    assert len(calls) == len(SIGNIN_EVENT_TYPES)

    # Extract the filter string from each call's request_configuration
    filters_used = []
    for c in calls:
        rc = c.kwargs["request_configuration"]
        filters_used.append(rc.query_parameters.filter)

    for event_type_filter in SIGNIN_EVENT_TYPES.values():
        assert any(event_type_filter in f for f in filters_used), f"Missing filter: {event_type_filter}"


@pytest.mark.asyncio
async def test_signins_multiple_event_types_return_combined_results(graph_api_client: GraphApi) -> None:
    """Results from all event type queries are combined in a single stream."""
    interactive_page = SimpleNamespace(
        value=[
            SignIn(id="interactive-1", created_date_time=datetime(2025, 9, 1, tzinfo=timezone.utc)),
        ],
        odata_next_link=None,
    )
    sp_page = SimpleNamespace(
        value=[
            SignIn(id="sp-1", created_date_time=datetime(2025, 9, 1, tzinfo=timezone.utc)),
        ],
        odata_next_link=None,
    )
    mi_page = SimpleNamespace(
        value=[
            SignIn(id="mi-1", created_date_time=datetime(2025, 9, 1, tzinfo=timezone.utc)),
        ],
        odata_next_link=None,
    )

    graph_api_client._beta_client.audit_logs.sign_ins.get.side_effect = [interactive_page, sp_page, mi_page]

    items = [
        x
        async for x in graph_api_client.get_signin_logs(
            datetime.fromisoformat("2025-09-01T00:00:00").replace(tzinfo=timezone.utc)
        )
    ]

    assert [i.id for i in items] == ["interactive-1", "sp-1", "mi-1"]
