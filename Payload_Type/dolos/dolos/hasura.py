"""Hasura GraphQL client for Dolos — queries Mythic's database directly."""

import json
import logging
import os
import ssl
import urllib.request
import urllib.error

logger = logging.getLogger("dolos.hasura")


class HasuraClient:
    """Minimal Hasura GraphQL client scoped to a Mythic operation."""

    def __init__(self):
        self.url = os.environ.get(
            "HASURA_URL",
            "http://127.0.0.1:8080/v1/graphql" if os.environ.get("DOLOS_DEV_MODE")
            else "http://mythic_graphql:8080/v1/graphql",
        )
        self.secret = os.environ.get("HASURA_SECRET", "")
        self._ssl_ctx = None

    @property
    def ssl_ctx(self):
        if self._ssl_ctx is None and os.environ.get("DOLOS_DEV_MODE"):
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            self._ssl_ctx = ctx
        return self._ssl_ctx

    @property
    def headers(self):
        return {
            "Content-Type": "application/json",
            "x-hasura-admin-secret": self.secret,
        }

    def query(self, query_str: str, variables: dict | None = None) -> dict | None:
        """Execute a GraphQL query. Returns the 'data' dict or None on error."""
        if not self.secret:
            logger.warning("[DOLOS-HASURA] HASURA_SECRET not set — skipping query")
            return None

        payload = json.dumps({"query": query_str, "variables": variables or {}}).encode()
        req = urllib.request.Request(self.url, data=payload, headers=self.headers)
        try:
            resp = urllib.request.urlopen(req, timeout=10, context=self.ssl_ctx)
            result = json.loads(resp.read())
            return result.get("data")
        except Exception as e:
            logger.warning(f"[DOLOS-HASURA] Query failed: {e}")
            return None

    # ── Dolos-specific queries ──

    def check_already_wrapped(self, inner_uuid: str) -> dict | None:
        """Check if inner payload already has a successful Dolos build.

        Returns dict with inner_id, inner_uuid, operation_id, wrapper_uuid
        if wrapped, or None if not wrapped / on error.
        """
        # Step 1: get inner payload DB id and operation_id
        data = self.query(
            """query GetInnerPayload($uuid: String!) {
              payload(where: {uuid: {_eq: $uuid}}) { id operation_id }
            }""",
            {"uuid": inner_uuid},
        )
        if not data or not data.get("payload"):
            logger.info(f"[DOLOS-BUILD] Inner payload UUID {inner_uuid} not found in DB")
            return None

        inner = data["payload"][0]
        inner_id = inner["id"]
        operation_id = inner["operation_id"]

        # Step 2: find successful Dolos wrappers
        data = self.query(
            """query FindDolosWrappers($inner_id: Int!) {
              payload(where: {
                payloadtype: {name: {_eq: "dolos"}},
                wrapped_payload_id: {_eq: $inner_id},
                build_phase: {_eq: "success"}
              }, order_by: {id: desc}, limit: 1) { id uuid build_phase }
            }""",
            {"inner_id": inner_id},
        )
        if not data or not data.get("payload"):
            logger.info(f"[DOLOS-BUILD] Inner payload {inner_uuid} (id={inner_id}) "
                        "has no existing Dolos builds — proceeding")
            return None

        wrapper = data["payload"][0]
        logger.info(f"[DOLOS-BUILD] Inner payload {inner_uuid} (id={inner_id}) already has "
                    f"a successful Dolos build: payload {wrapper['uuid']} (id={wrapper['id']})")
        return {
            "inner_id": inner_id,
            "inner_uuid": inner_uuid,
            "operation_id": operation_id,
            "wrapper_uuid": wrapper["uuid"],
        }

    def get_task_id(self, operation_id: int) -> int | None:
        """Look up any TaskID in the given operation for MythicRPC scoping."""
        data = self.query(
            """query GetTaskForOperation($op_id: Int!) {
              task(where: {operation_id: {_eq: $op_id}}, limit: 1, order_by: {id: desc}) { id }
            }""",
            {"op_id": operation_id},
        )
        if not data or not data.get("task"):
            logger.error(f"[DOLOS-BUILD] No tasks found in operation {operation_id}")
            return None

        task_id = data["task"][0]["id"]
        logger.info(f"[DOLOS-BUILD] Found TaskID {task_id} in operation {operation_id}")
        return task_id