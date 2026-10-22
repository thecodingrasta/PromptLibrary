"""Generate tool contracts from the same annotated functions that execute them."""

import importlib
import inspect
import json
import logging
import sqlite3
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Annotated, Any, Literal, TypeVar, get_type_hints

from pydantic import BaseModel, ConfigDict, Field, ValidationError, create_model

from promptlibrary import config
from promptlibrary.database import get_db
from promptlibrary.services.validation import ConflictError, NotFoundError, Record

Identity = Annotated[str, Field(min_length=1, max_length=256)]
ItemId = Annotated[str, Field(alias="id", min_length=1, max_length=256)]
Title = Annotated[str, Field(min_length=1, max_length=200)]
Text = Annotated[str, Field(max_length=2_000_000)]
Names = Annotated[list[str], Field(max_length=100)]
Payload = Record | list[Record]
Handler = Callable[..., Awaitable[Payload]]
ToolHandler = TypeVar("ToolHandler", bound=Handler)
logger = logging.getLogger(__name__)


class ToolDefinition(BaseModel):
    name: str
    description: str
    inputSchema: Record  # noqa: N815 - MCP wire format.
    annotations: Record


class ToolText(BaseModel):
    type: Literal["text"] = "text"
    text: str


@dataclass(frozen=True)
class RegisteredTool:
    handler: Handler
    input_model: type[BaseModel]
    definition: ToolDefinition
    read_only: bool


TOOLS: dict[str, RegisteredTool] = {}


def tool(
    *, read_only: bool = False, destructive: bool = False, network: bool = False
) -> Callable[[ToolHandler], ToolHandler]:
    def register(handler: ToolHandler) -> ToolHandler:
        hints = get_type_hints(handler, include_extras=True)
        # Pydantic's dynamic model factory is the only reflection boundary. Domain
        # handlers below retain normal, explicit parameter types and validation.
        fields: dict[str, Any] = {}
        for name, parameter in inspect.signature(handler).parameters.items():
            if name in {"db", "configuration"}:
                continue
            default = ... if parameter.default is inspect.Parameter.empty else parameter.default
            fields[name] = (hints[name], default)
        input_model = create_model(
            handler.__name__ + "Input",
            __config__=ConfigDict(extra="forbid"),
            **fields,
        )
        description = inspect.getdoc(handler)
        if not description or handler.__name__ in TOOLS:
            raise RuntimeError("Every tool needs a unique name and a description.")
        definition = ToolDefinition(
            name=handler.__name__,
            description=description,
            inputSchema=input_model.model_json_schema(),
            annotations={
                "readOnlyHint": read_only,
                "destructiveHint": destructive,
                "idempotentHint": read_only,
                "openWorldHint": network,
            },
        )
        TOOLS[handler.__name__] = RegisteredTool(handler, input_model, definition, read_only)
        return handler

    return register


async def execute_tool(
    name: str, arguments: Record, configuration: config.Settings | None = None
) -> tuple[Payload, bool]:
    importlib.import_module("promptlibrary.mcp.tools")
    registered = TOOLS.get(name)
    if registered is None:
        return {"error": "Unknown tool.", "code": "unknown_tool"}, True
    active_settings = configuration or config.settings
    try:
        validated = registered.input_model.model_validate(arguments)
        parameters = {key: getattr(validated, key) for key in registered.input_model.model_fields}
        if "configuration" in inspect.signature(registered.handler).parameters:
            parameters["configuration"] = active_settings
        async with get_db(active_settings, write=not registered.read_only) as db:
            result = await registered.handler(db=db, **parameters)
            if not registered.read_only:
                await db.commit()
        return result, False
    except ValidationError as error:
        fields = sorted({".".join(str(part) for part in item["loc"]) for item in error.errors()})
        return {
            "error": "Invalid tool input. Check: " + ", ".join(fields),
            "code": "invalid_input",
        }, True
    except (NotFoundError, ConflictError, ValueError) as error:
        code = (
            "not_found"
            if isinstance(error, NotFoundError)
            else "conflict"
            if isinstance(error, ConflictError)
            else "invalid_input"
        )
        return {"error": str(error), "code": code}, True
    except sqlite3.IntegrityError:
        return {
            "error": "A duplicate value or invalid reference conflicts with this change.",
            "code": "conflict",
        }, True
    except Exception as error:
        # SDK error boundaries must not leak credentials, connection strings or SQL.
        logger.error("Tool %s failed (%s)", name, type(error).__name__)
        return {
            "error": "The operation failed. Check the local server logs and database integrity.",
            "code": "operation_failed",
        }, True


def text_result(payload: Payload) -> list[ToolText]:
    return [ToolText(text=json.dumps(payload, ensure_ascii=False, indent=2))]
