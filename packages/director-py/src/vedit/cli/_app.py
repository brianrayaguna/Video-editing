"""Root `vedit` Typer application and shared CLI option types."""

from __future__ import annotations

from typing import Annotated

import typer

app = typer.Typer(
    name="vedit",
    help="Capability-first video directing, brand policy, and Modal cloud-render CLI.",
    no_args_is_help=True,
)

JsonOption = Annotated[bool, typer.Option("--json", help="Emit machine-readable JSON.")]
