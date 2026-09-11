"""Strict, atomically persisted first-run setup state."""

from __future__ import annotations

import json
import os
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError


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


class SetupState(_StrictModel):
    stages: dict[str, SetupStage] = Field(default_factory=dict)
    code: str = Field(default="OK", min_length=1, max_length=80)
    detail: str = Field(default="", max_length=500)

    @classmethod
    def load(cls, path: Path) -> "SetupState":
        path = Path(path)
        try:
            value = cls.model_validate_json(path.read_text(encoding="utf-8"))
            return value
        except FileNotFoundError:
            return cls()
        except (ValueError, ValidationError):
            state = cls(code="SETUP_STATE_INVALID", detail="Saved setup state was invalid and was reset.")
            state.save(path)
            return state

    def save(self, path: Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path: Path | None = None
        try:
            with NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=path.parent,
                prefix=f".{path.name}.",
                suffix=".tmp",
                delete=False,
            ) as temporary:
                temporary_path = Path(temporary.name)
                json.dump(self.model_dump(mode="json"), temporary, indent=2, sort_keys=True)
                temporary.write("\n")
                temporary.flush()
                os.fsync(temporary.fileno())
            os.replace(temporary_path, path)
            temporary_path = None
        finally:
            if temporary_path is not None:
                try:
                    temporary_path.unlink(missing_ok=True)
                except OSError:
                    pass
