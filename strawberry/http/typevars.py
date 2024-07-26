from typing import TypeVar

Request = TypeVar("Request", contravariant=True)
Response = TypeVar("Response")
SubResponse = TypeVar("SubResponse")
WebSocketResponse = TypeVar("WebSocketResponse")
Context = TypeVar("Context")
RootValue = TypeVar("RootValue")


__all__ = ["Request", "Response", "SubResponse", "WebSocketResponse", "Context", "RootValue"]
