---
title: Open Telemetry
summary: Add Open Telemetry tracing to your GraphQL server.
tags: tracing
---

# `OpenTelemetryExtension`

This extension adds tracing information that is compatible with
[Open Telemetry](https://opentelemetry.io/).

<Note>

This extension requires additional requirements:

```shell
pip install 'strawberry-graphql[opentelemetry]'
```

</Note>

## Usage example:

```python
import strawberry
from strawberry.extensions.tracing import OpenTelemetryExtension


@strawberry.type
class Query:
    @strawberry.field
    def hello(self) -> str:
        return "Hello, world!"


schema = strawberry.Schema(
    Query,
    extensions=[
        OpenTelemetryExtension,
    ],
)
```

<Note>

If you are not running in an Async context then you'll need to use the sync
version:

```python
import strawberry
from strawberry.extensions.tracing import OpenTelemetryExtensionSync


@strawberry.type
class Query:
    @strawberry.field
    def hello(self) -> str:
        return "Hello, world!"


schema = strawberry.Schema(
    Query,
    extensions=[
        OpenTelemetryExtensionSync,
    ],
)
```

</Note>

## API reference:

```python
class OpenTelemetryExtension(arg_filter=None): ...
```

#### `arg_filter: Optional[ArgFilter]`

A function to filter certain field arguments from being included in the tracing
data.

```python
ArgFilter = Callable[[Dict[str, Any], GraphQLResolveInfo], Dict[str, Any]]
```

## More examples:

<details>
  <summary>Using `arg_filter`</summary>

```python
import strawberry
from strawberry.extensions.tracing import OpenTelemetryExtensionSync


@strawberry.type
class Query:
    @strawberry.field
    def hello(self) -> str:
        return "Hello, world!"


def arg_filter(kwargs, info):
    filtered_kwargs = {}
    for name, value in kwargs.items():
        # Never include any arguments called "password"
        if name == "password":
            continue
        filtered_kwargs[name] = value

    return filtered_kwargs


schema = strawberry.Schema(
    Query,
    extensions=[
        OpenTelemetryExtensionSync(
            arg_filter=arg_filter,
        ),
    ],
)
```

</details>

<details>
  <summary>Using `tracer_provider`</summary>

```python
import strawberry
from opentelemetry.trace import TracerProvider
from strawberry.extensions.tracing import OpenTelemetryExtension


@strawberry.type
class Query:
    @strawberry.field
    def hello(self) -> str:
        return "Hello, world!"


class MyTracerProvider(TracerProvider):
    def get_tracer(self, name, version=None, schema_url=None):
        return super().get_tracer(name, version, schema_url)


schema = strawberry.Schema(
    Query,
    extensions=[
        OpenTelemetryExtension(
            tracer_provider=MyTracerProvider(),
        ),
    ],
)
```

</details>
