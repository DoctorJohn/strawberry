from __future__ import annotations

import contextlib
import json
from collections.abc import AsyncGenerator, Mapping, Sequence
from datetime import timedelta
from io import BytesIO
from typing import Any, Optional
from typing_extensions import Literal

from litestar import Litestar, Request
from litestar.exceptions import WebSocketDisconnect
from litestar.testing import TestClient
from litestar.testing.websocket_test_session import WebSocketTestSession
from strawberry.http import GraphQLHTTPResponse
from strawberry.http.ides import GraphQL_IDE
from strawberry.litestar import make_graphql_controller
from strawberry.schema import Schema
from strawberry.subscriptions import (
    GRAPHQL_TRANSPORT_WS_PROTOCOL,
    GRAPHQL_WS_PROTOCOL,
)
from strawberry.types import ExecutionResult
from tests.http.context import get_context
from tests.views.schema import Query
from tests.websockets.views import OnWSConnectMixin

from .base import (
    JSON,
    DebuggableGraphQLTransportWSHandler,
    DebuggableGraphQLWSHandler,
    HttpClient,
    Message,
    Response,
    ResultOverrideFunction,
    WebSocketClient,
)


def custom_context_dependency() -> str:
    return "Hi!"


async def litestar_get_context(request: Request = None):
    return get_context({"request": request})


async def get_root_value(request: Request = None):
    return Query()


class LitestarHttpClient(HttpClient):
    def __init__(
        self,
        schema: Schema,
        graphiql: Optional[bool] = None,
        graphql_ide: Optional[GraphQL_IDE] = "graphiql",
        allow_queries_via_get: bool = True,
        keep_alive: bool = False,
        keep_alive_interval: float = 1,
        debug: bool = False,
        subscription_protocols: Sequence[str] = (
            GRAPHQL_TRANSPORT_WS_PROTOCOL,
            GRAPHQL_WS_PROTOCOL,
        ),
        connection_init_wait_timeout: timedelta = timedelta(minutes=1),
        result_override: ResultOverrideFunction = None,
        multipart_uploads_enabled: bool = False,
    ):
        BaseGraphQLController = make_graphql_controller(
            schema=schema,
            graphiql=graphiql,
            graphql_ide=graphql_ide,
            allow_queries_via_get=allow_queries_via_get,
            keep_alive=keep_alive,
            keep_alive_interval=keep_alive_interval,
            debug=debug,
            subscription_protocols=subscription_protocols,
            connection_init_wait_timeout=connection_init_wait_timeout,
            multipart_uploads_enabled=multipart_uploads_enabled,
            path="/graphql",
            context_getter=litestar_get_context,
            root_value_getter=get_root_value,
        )

        class GraphQLController(OnWSConnectMixin, BaseGraphQLController):
            graphql_transport_ws_handler_class = DebuggableGraphQLTransportWSHandler
            graphql_ws_handler_class = DebuggableGraphQLWSHandler

            async def process_result(
                self, request: Request, result: ExecutionResult
            ) -> GraphQLHTTPResponse:
                if result_override:
                    return result_override(result)

                return await super().process_result(request, result)

        self.app = Litestar(route_handlers=[GraphQLController])
        self.client = TestClient(self.app)

    async def _graphql_request(
        self,
        method: Literal["get", "post"],
        query: Optional[str] = None,
        operation_name: Optional[str] = None,
        variables: Optional[dict[str, object]] = None,
        files: Optional[dict[str, BytesIO]] = None,
        headers: Optional[dict[str, str]] = None,
        extensions: Optional[dict[str, Any]] = None,
        **kwargs: Any,
    ) -> Response:
        if body := self._build_body(
            query=query,
            operation_name=operation_name,
            variables=variables,
            files=files,
            method=method,
            extensions=extensions,
        ):
            if method == "get":
                kwargs["params"] = body
            elif files:
                kwargs["data"] = body
            else:
                kwargs["content"] = json.dumps(body)

        if files:
            kwargs["files"] = files

        response = getattr(self.client, method)(
            "/graphql",
            headers=self._get_headers(method=method, headers=headers, files=files),
            **kwargs,
        )

        return Response(
            status_code=response.status_code,
            data=response.content,
            headers=response.headers,
        )

    async def request(
        self,
        url: str,
        method: Literal["head", "get", "post", "patch", "put", "delete"],
        headers: Optional[dict[str, str]] = None,
    ) -> Response:
        response = getattr(self.client, method)(url, headers=headers)

        return Response(
            status_code=response.status_code,
            data=response.content,
            headers=response.headers,
        )

    async def get(
        self,
        url: str,
        headers: Optional[dict[str, str]] = None,
    ) -> Response:
        return await self.request(url, "get", headers=headers)

    async def post(
        self,
        url: str,
        data: Optional[bytes] = None,
        json: Optional[JSON] = None,
        headers: Optional[dict[str, str]] = None,
    ) -> Response:
        response = self.client.post(url, headers=headers, content=data, json=json)

        return Response(
            status_code=response.status_code,
            data=response.content,
            headers=dict(response.headers),
        )

    @contextlib.asynccontextmanager
    async def ws_connect(
        self,
        url: str,
        *,
        protocols: list[str],
    ) -> AsyncGenerator[WebSocketClient, None]:
        with self.client.websocket_connect(url, protocols) as ws:
            yield LitestarWebSocketClient(ws)


class LitestarWebSocketClient(WebSocketClient):
    def __init__(self, ws: WebSocketTestSession):
        self.ws = ws
        self._closed: bool = False
        self._close_code: Optional[int] = None
        self._close_reason: Optional[str] = None

    async def send_text(self, payload: str) -> None:
        self.ws.send_text(payload)

    async def send_json(self, payload: Mapping[str, object]) -> None:
        self.ws.send_json(payload)

    async def send_bytes(self, payload: bytes) -> None:
        self.ws.send_bytes(payload)

    async def receive(self, timeout: Optional[float] = None) -> Message:
        if self._closed:
            # if close was received via exception, fake it so that recv works
            return Message(
                type="websocket.close", data=self._close_code, extra=self._close_reason
            )
        try:
            m = self.ws.receive()
        except WebSocketDisconnect as exc:
            self._closed = True
            self._close_code = exc.code
            self._close_reason = exc.detail
            return Message(type="websocket.close", data=exc.code, extra=exc.detail)
        if m["type"] == "websocket.close":
            # Probably never happens
            self._closed = True
            self._close_code = m["code"]
            self._close_reason = m["reason"]
            return Message(type=m["type"], data=m["code"], extra=m["reason"])
        if m["type"] == "websocket.send":
            return Message(type=m["type"], data=m["text"])

        assert "data" in m
        return Message(type=m["type"], data=m["data"], extra=m["extra"])

    async def receive_json(self, timeout: Optional[float] = None) -> Any:
        m = self.ws.receive()
        assert m["type"] == "websocket.send"
        assert "text" in m
        assert m["text"] is not None
        return json.loads(m["text"])

    async def close(self) -> None:
        self.ws.close()
        self._closed = True

    @property
    def accepted_subprotocol(self) -> Optional[str]:
        return self.ws.accepted_subprotocol

    @property
    def closed(self) -> bool:
        return self._closed

    @property
    def close_code(self) -> int:
        assert self._close_code is not None
        return self._close_code

    @property
    def close_reason(self) -> Optional[str]:
        return self._close_reason
