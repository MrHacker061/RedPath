"""Strict component status models for first-run setup."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class SetupStage(_StrictModel):
    name: str = Field(min_length=1, max_length=80)
    status: Literal["ready", "needs_attention", "in_progress", "failed"]
    code: str = Field(min_length=1, max_length=80)
    detail: str = Field(max_length=500)

    def __init__(self, *args: object, **data: object) -> None:
        if args:
            fields = ("name", "status", "code", "detail")
            if len(args) > len(fields) or any(field in data for field in fields[: len(args)]):
                raise TypeError("SetupStage accepts each field once")
            data.update(dict(zip(fields, args)))
        super().__init__(**data)
