import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from azure_ad.base import AzureADConfiguration
from azure_ad.connector_entraid_graph_api import MicrosoftEntraIdGraphApiConnector


@pytest.fixture
def entraid_connector(
    graph_api_client, symphony_storage, mock_push_data_to_intakes
) -> MicrosoftEntraIdGraphApiConnector:
    connector = MicrosoftEntraIdGraphApiConnector(data_path=symphony_storage)
    connector.module.configuration = AzureADConfiguration(
        tenant_id="tenant_id",
        client_id="client_id",
        client_secret="client_secret",
    )
    connector.configuration = {
        "chunk_size": 1,
        "intake_key": "",
    }
    connector.push_data_to_intakes = mock_push_data_to_intakes
    connector._client = graph_api_client
    connector.log_exception = Mock()
    connector.log = Mock()

    return connector


@pytest.mark.asyncio
async def test_entraid_connector_single_run_1(
    entraid_connector, signins_page_1, signins_page_2, directory_audits_page_1, directory_audits_page_2
):
    empty_page = SimpleNamespace(value=[], odata_next_link=None)
    # The connector now calls get_signin_logs_for_type once per type.
    # First type (interactive) gets data, other two get empty.
    entraid_connector._client._beta_client.audit_logs.sign_ins.get.side_effect = [
        signins_page_1, empty_page, empty_page,
    ]
    entraid_connector._client._beta_client.audit_logs.sign_ins.with_url.return_value.get.return_value = signins_page_2
    entraid_connector._client._client.audit_logs.directory_audits.get.return_value = directory_audits_page_1
    entraid_connector._client._client.audit_logs.directory_audits.with_url.return_value.get.return_value = (
        directory_audits_page_2
    )

    result = await entraid_connector.single_run()
    assert result == 6


@pytest.mark.asyncio
async def test_entraid_connector_single_run_2(
    entraid_connector, signins_page_1, signins_page_2, directory_audits_page_1, directory_audits_page_2
):
    entraid_connector.configuration.chunk_size = 3

    empty_page = SimpleNamespace(value=[], odata_next_link=None)
    entraid_connector._client._beta_client.audit_logs.sign_ins.get.side_effect = [
        signins_page_1, empty_page, empty_page,
    ]
    entraid_connector._client._beta_client.audit_logs.sign_ins.with_url.return_value.get.return_value = signins_page_2
    entraid_connector._client._client.audit_logs.directory_audits.get.return_value = directory_audits_page_1
    entraid_connector._client._client.audit_logs.directory_audits.with_url.return_value.get.return_value = (
        directory_audits_page_2
    )

    # Dedup cache is now per-type; "interactive" is the type that gets data
    entraid_connector.signin_caches["interactive"]["1"] = True
    entraid_connector.directory_alerts_cache["3"] = True

    result = await entraid_connector.single_run()

    assert result == 4


@pytest.mark.asyncio
async def test_entraid_connector_per_type_checkpoints_are_independent(entraid_connector):
    """Each sign-in type advances its own checkpoint independently."""
    from datetime import datetime, timezone

    from msgraph_beta.generated.models.sign_in import SignIn

    empty_page = SimpleNamespace(value=[], odata_next_link=None)

    # Record the initial checkpoint offsets before running
    initial_sp_offset = entraid_connector.signin_checkpoints["service_principal"].offset
    initial_mi_offset = entraid_connector.signin_checkpoints["managed_identity"].offset

    # Use a timestamp in the future so it's guaranteed past the ignore_older_than cutoff
    future_ts = datetime(2099, 1, 1, tzinfo=timezone.utc)
    interactive_page = SimpleNamespace(
        value=[SignIn(id="fresh-1", created_date_time=future_ts)],
        odata_next_link=None,
    )

    # Interactive gets data, SP and MI get empty
    entraid_connector._client._beta_client.audit_logs.sign_ins.get.side_effect = [
        interactive_page, empty_page, empty_page,
    ]
    entraid_connector._client._client.audit_logs.directory_audits.get.return_value = None

    await entraid_connector.single_run()

    # Interactive checkpoint should have advanced to future_ts
    interactive_offset = entraid_connector.signin_checkpoints["interactive"].offset
    assert interactive_offset == future_ts

    # SP and MI checkpoints should not have moved
    assert entraid_connector.signin_checkpoints["service_principal"].offset == initial_sp_offset
    assert entraid_connector.signin_checkpoints["managed_identity"].offset == initial_mi_offset


@pytest.mark.asyncio
async def test_entraid_connector_envelope_structure(entraid_connector):
    """Events pushed to intakes must be wrapped in an envelope with objectType and tenantId."""
    from datetime import datetime, timezone

    from msgraph.generated.models.directory_audit import DirectoryAudit
    from msgraph_beta.generated.models.sign_in import SignIn

    empty_page = SimpleNamespace(value=[], odata_next_link=None)
    ts = datetime(2025, 9, 1, tzinfo=timezone.utc)

    signin_page = SimpleNamespace(
        value=[SignIn(id="s1", created_date_time=ts)],
        odata_next_link=None,
    )
    audit_page = SimpleNamespace(
        value=[DirectoryAudit(id="d1", activity_date_time=ts, activity_display_name="Add user")],
        odata_next_link=None,
    )

    entraid_connector._client._beta_client.audit_logs.sign_ins.get.side_effect = [
        signin_page, empty_page, empty_page,
    ]
    entraid_connector._client._client.audit_logs.directory_audits.get.return_value = audit_page

    pushed = []
    original_push = entraid_connector.push_data_to_intakes

    async def capture_push(events):
        pushed.extend(events)
        return await original_push(events)

    entraid_connector.push_data_to_intakes = capture_push
    await entraid_connector.single_run()

    assert len(pushed) == 2
    for raw in pushed:
        event = json.loads(raw)
        meta = event["_meta"]
        assert "objectType" in meta
        assert meta["tenantId"] == "tenant_id"

    audit_event = json.loads(pushed[0])
    signin_event = json.loads(pushed[1])
    assert audit_event["_meta"]["objectType"] == "directoryAudit"
    assert audit_event["id"] == "d1"
    assert signin_event["_meta"]["objectType"] == "signIn"
    assert signin_event["id"] == "s1"
