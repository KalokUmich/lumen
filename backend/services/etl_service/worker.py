"""ETL Service — Temporal worker for Mongo→Postgres pipelines.

Phase 0: skeleton only. Phase 1 sprint 9 implements the activities.

Tooling (chosen for permissive-license commercial path):
  - Temporal Python SDK (MIT) for orchestration
  - Meltano + tap-mongodb (MIT + Apache 2.0) for the extractor
  - asyncpg (Apache 2.0) for the sink
We deliberately avoid Airbyte (Elastic License v2 — restricts commercial SaaS use).
"""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass
from datetime import timedelta

from temporalio import activity, workflow
from temporalio.client import Client
from temporalio.worker import Worker


@dataclass
class SyncConfig:
    workspace_id: str
    source_collection: str
    target_table: str
    incremental_field: str = "updatedAt"


@activity.defn
async def read_mongo_batch(config: SyncConfig, cursor: str | None) -> dict:
    # TODO(phase-1): use motor to read a batch from Mongo
    return {"docs": [], "next_cursor": cursor}


@activity.defn
async def transform_batch(batch: dict, mapping: dict) -> dict:
    # TODO(phase-1): apply schema flattening per mapping
    return batch


@activity.defn
async def write_postgres_batch(batch: dict, target_table: str) -> int:
    # TODO(phase-1): COPY into Postgres
    return 0


@workflow.defn
class MongoToPostgresWorkflow:
    @workflow.run
    async def run(self, config: SyncConfig) -> dict:
        last_cursor: str | None = None
        batches = 0
        while True:
            batch = await workflow.execute_activity(
                read_mongo_batch,
                args=[config, last_cursor],
                start_to_close_timeout=timedelta(minutes=5),
            )
            if not batch.get("docs"):
                break
            transformed = await workflow.execute_activity(
                transform_batch, args=[batch, {}],
                start_to_close_timeout=timedelta(minutes=5),
            )
            await workflow.execute_activity(
                write_postgres_batch, args=[transformed, config.target_table],
                start_to_close_timeout=timedelta(minutes=5),
            )
            last_cursor = batch.get("next_cursor")
            batches += 1
        return {"batches": batches}


async def main() -> None:
    client = await Client.connect(os.environ.get("TEMPORAL_HOST", "localhost:7233"))
    worker = Worker(
        client,
        task_queue="omni-etl",
        workflows=[MongoToPostgresWorkflow],
        activities=[read_mongo_batch, transform_batch, write_postgres_batch],
    )
    await worker.run()


if __name__ == "__main__":
    asyncio.run(main())
