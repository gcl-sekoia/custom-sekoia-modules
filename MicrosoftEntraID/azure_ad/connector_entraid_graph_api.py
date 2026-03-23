import asyncio
import json
import time
from datetime import timedelta
from typing import Any, Optional

from cachetools import Cache, LRUCache
from kiota_abstractions.serialization import Parsable
from loguru import logger
from msgraph.generated.models.directory_audit import DirectoryAudit
from msgraph_beta.generated.models.sign_in import SignIn
from sekoia_automation.aio.connector import AsyncConnector
from sekoia_automation.checkpoint import CheckpointDatetime
from sekoia_automation.connector import Connector, DefaultConnectorConfiguration

from graph_api.client import SIGNIN_EVENT_TYPES, GraphApi

from .base import AzureADModule
from .metrics import EVENTS_LAG, FORWARD_EVENTS_DURATION, OUTCOMING_EVENTS


class MicrosoftEntraIdGraphApiConnectorConfig(DefaultConnectorConfiguration):
    """Connector configuration."""

    frequency: int = 60
    chunk_size: int = 1000


class MicrosoftEntraIdGraphApiConnector(AsyncConnector):
    module: AzureADModule
    configuration: MicrosoftEntraIdGraphApiConnectorConfig

    def __init__(self, *args: Any, **kwargs: Optional[Any]) -> None:
        super().__init__(*args, **kwargs)

        # Per sign-in type checkpoints and caches
        self.signin_checkpoints: dict[str, CheckpointDatetime] = {}
        self.signin_caches: dict[str, Cache[str | None, bool]] = {}
        for signin_type in SIGNIN_EVENT_TYPES:
            self.signin_checkpoints[signin_type] = CheckpointDatetime(
                path=self.data_path,
                start_at=timedelta(days=7),
                ignore_older_than=timedelta(days=7),
                subkey=f"signin_{signin_type}_datetime",
            )
            self.signin_caches[signin_type] = self._load_cache(
                self.signin_checkpoints[signin_type], f"signin_{signin_type}", maxsize=500
            )

        self.last_event_date_directory = CheckpointDatetime(
            path=self.data_path,
            start_at=timedelta(days=7),
            ignore_older_than=timedelta(days=7),
            subkey="directory_datetime",
        )
        self.directory_alerts_cache = self._load_cache(
            self.last_event_date_directory, "directory", maxsize=500
        )
        self._client: Optional[GraphApi] = None

    @staticmethod
    def _load_cache(checkpoint: CheckpointDatetime, key: str, maxsize: int) -> Cache[str | None, bool]:
        result: LRUCache[str | None, bool] = LRUCache(maxsize=maxsize)
        with checkpoint._context as cache:
            for event_id in cache.get(key, []):
                result[event_id] = True
        return result

    @staticmethod
    def _persist_cache(checkpoint: CheckpointDatetime, key: str, cache: Cache[str | None, bool]) -> None:
        with checkpoint._context as ctx:
            ctx[key] = list(cache.keys())

    def _encode_event(self, event: Parsable, object_type: str) -> str:
        payload = json.loads(GraphApi.encode_log(event))
        payload["_meta"] = {
            "objectType": object_type,
            "tenantId": self.module.configuration.tenant_id,
        }
        return json.dumps(payload)

    @property
    def client(self) -> GraphApi:  # pragma: no cover
        if not self._client:
            self._client = GraphApi(
                tenant_id=self.module.configuration.tenant_id,
                client_id=self.module.configuration.client_id,
                client_secret=self.module.configuration.client_secret,
            )

        return self._client

    def stop(self, *args: Any, **kwargs: Optional[Any]) -> None:  # pragma: no cover
        """
        Stop the connector.

        Temporary redefine the method to avoid known SDK issues.
        """
        super(Connector, self).stop(*args, **kwargs)

    async def run_directory(self) -> int:
        events: list[DirectoryAudit] = []
        total_events = 0
        checkpoint = self.last_event_date_directory
        cache = self.directory_alerts_cache
        new_offset = checkpoint.offset
        async for event in self.client.get_directory_audit_logs(start_date=checkpoint.offset):
            if not self.running:  # pragma: no cover
                break

            if event.id in cache:
                continue

            events.append(event)
            if len(events) >= self.configuration.chunk_size:
                total_events += len(await self.push_data_to_intakes(
                    [self._encode_event(event, "directoryAudit") for event in events]
                ))

                for data in events:
                    new_offset = max(new_offset, data.activity_date_time)
                    cache[data.id] = True

                checkpoint.offset = new_offset
                self._persist_cache(checkpoint, "directory", cache)
                events = []

        if events:
            total_events += len(await self.push_data_to_intakes(
                [self._encode_event(event, "directoryAudit") for event in events]
            ))

            for data in events:
                new_offset = max(new_offset, data.activity_date_time)
                cache[data.id] = True

            checkpoint.offset = new_offset
            self._persist_cache(checkpoint, "directory", cache)

        return total_events

    async def run_signin(self) -> int:
        total = 0
        for signin_type, event_type_filter in SIGNIN_EVENT_TYPES.items():
            total += await self._run_signin_type(signin_type, event_type_filter)
        return total

    async def _run_signin_type(self, signin_type: str, event_type_filter: str) -> int:
        checkpoint = self.signin_checkpoints[signin_type]
        cache = self.signin_caches[signin_type]
        cache_key = f"signin_{signin_type}"
        events: list[SignIn] = []
        total_events = 0
        new_offset = checkpoint.offset

        async for event in self.client.get_signin_logs_for_type(
            checkpoint.offset, None, event_type_filter
        ):
            if not self.running:  # pragma: no cover
                break

            if event.id in cache:
                continue

            events.append(event)
            if len(events) >= self.configuration.chunk_size:
                total_events += len(await self.push_data_to_intakes(
                    [self._encode_event(e, "signIn") for e in events]
                ))

                for data in events:
                    new_offset = max(new_offset, data.created_date_time)
                    cache[data.id] = True

                checkpoint.offset = new_offset
                self._persist_cache(checkpoint, cache_key, cache)
                events = []

        if events:
            total_events += len(await self.push_data_to_intakes(
                [self._encode_event(e, "signIn") for e in events]
            ))

            for data in events:
                new_offset = max(new_offset, data.created_date_time)
                cache[data.id] = True

            checkpoint.offset = new_offset
            self._persist_cache(checkpoint, cache_key, cache)

        return total_events

    async def single_run(self) -> int:
        directory_results = await self.run_directory()
        signin_results = await self.run_signin()

        return directory_results + signin_results

    async def async_run(self) -> None:  # pragma: no cover
        while self.running:
            try:
                processing_start = time.time()
                result = await self.single_run()
                last_event_date_signin = min(cp.offset for cp in self.signin_checkpoints.values())
                last_event_date_directory = self.last_event_date_directory.offset
                last_event_date = max(last_event_date_signin, last_event_date_directory)
                processing_end = time.time()

                EVENTS_LAG.labels(intake_key=self.configuration.intake_key).set(
                    processing_end - last_event_date.timestamp()
                )

                log_message = "No records to forward"
                if result > 0:
                    log_message = "Pushed {0} records".format(result)

                self.log(message=log_message, level="info")
                OUTCOMING_EVENTS.labels(intake_key=self.configuration.intake_key).inc(result)

                processing_time = processing_end - processing_start
                FORWARD_EVENTS_DURATION.labels(intake_key=self.configuration.intake_key).observe(processing_time)
                logger.info(
                    "Processing took {processing_time} seconds",
                    processing_time=processing_time,
                )

                if result == 0:
                    await asyncio.sleep(self.configuration.frequency)

            except TimeoutError:
                self.log(message="A timeout was raised by the client", level="warning")
                await asyncio.sleep(self.configuration.frequency)

            except Exception as error:
                self.log_exception(error)

                # Reset client if HTTP transport is closed
                if "HTTP transport has already been closed" in str(error) or "transport" in str(error).lower():
                    self.log(message="Looks like http transport closed, resetting client....", level="warning")
                    if self._client:
                        await self._client.close()
                        self._client = None

                await asyncio.sleep(self.configuration.frequency)

        if self._client:
            await self._client.close()

        if self._session:
            await self._session.close()

    def run(self) -> None:  # pragma: no cover
        loop = asyncio.get_event_loop()
        loop.run_until_complete(self.async_run())
