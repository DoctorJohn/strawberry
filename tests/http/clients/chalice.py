from __future__ import annotations

import urllib.parse
from io import BytesIO
from json import dumps
from typing import Any, Optional, Union
from typing_extensions import Literal

from chalice.app import Chalice
from chalice.app import Request as ChaliceRequest
from chalice.test import Client
from strawberry import Schema
from strawberry.chalice.views import GraphQLView as BaseGraphQLView
from strawberry.http import GraphQLHTTPResponse
from strawberry.http.ides import GraphQL_IDE
from strawberry.http.temporal_response import TemporalResponse
from strawberry.schema.config import StrawberryConfig
from strawberry.types import ExecutionResult
from tests.http.context import get_context
from tests.views.schema import Query

from .base import JSON, HttpClient, Response, ResultOverrideFunction


class GraphQLView(BaseGraphQLView[dict[str, object], object]):
    result_override: ResultOverrideFunction = None

    def get_root_value(self, request: ChaliceRequest) -> Query:
        super().get_root_value(request)  # for coverage
        return Query()

    def get_context(
        self, request: ChaliceRequest, response: TemporalResponse
    ) -> dict[str, object]:
        context = super().get_context(request, response)

        return get_context(context)

    def process_result(
        self, request: ChaliceRequest, result: ExecutionResult
    ) -> GraphQLHTTPResponse:
        if self.result_override:
            return self.result_override(result)

        return super().process_result(request, result)


class ChaliceHttpClient(HttpClient):
    def __init__(
        self,
        schema: Schema,
        graphiql: Optional[bool] = None,
        graphql_ide: Optional[GraphQL_IDE] = "graphiql",
        allow_queries_via_get: bool = True,
        result_override: ResultOverrideFunction = None,
        multipart_uploads_enabled: bool = False,
        schema_config: Optional[StrawberryConfig] = None,
    ):
        self.app = Chalice(app_name="TheStackBadger")

        view = GraphQLView(
            schema=schema,
            graphiql=graphiql,
            graphql_ide=graphql_ide,
            allow_queries_via_get=allow_queries_via_get,
        )
        view.result_override = result_override

        @self.app.route(
            "/graphql", methods=["GET", "POST"], content_types=["application/json"]
        )
        def handle_graphql():
            assert self.app.current_request is not None
            return view.execute_request(self.app.current_request)

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
        body = self._build_body(
            query=query,
            operation_name=operation_name,
            variables=variables,
            files=files,
            method=method,
            extensions=extensions,
        )

        data: Union[dict[str, object], str, None] = None

        if body and files:
            body.update({name: (file, name) for name, file in files.items()})

        url = "/graphql"

        if method == "get":
            body_encoded = urllib.parse.urlencode(body or {})
            url = f"{url}?{body_encoded}"
        else:
            if body:
                data = body if files else dumps(body)
            kwargs["body"] = data

        with Client(self.app) as client:
            response = getattr(client.http, method)(
                url,
                headers=self._get_headers(method=method, headers=headers, files=files),
                **kwargs,
            )

        return Response(
            status_code=response.status_code,
            data=response.body,
            headers=response.headers,
        )

    async def request(
        self,
        url: str,
        method: Literal["head", "get", "post", "patch", "put", "delete"],
        headers: Optional[dict[str, str]] = None,
    ) -> Response:
        with Client(self.app) as client:
            response = getattr(client.http, method)(url, headers=headers)

        return Response(
            status_code=response.status_code,
            data=response.body,
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
        body = dumps(json) if json is not None else data

        with Client(self.app) as client:
            response = client.http.post(url, headers=headers, body=body)

        return Response(
            status_code=response.status_code,
            data=response.body,
            headers=response.headers,
        )
