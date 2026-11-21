"""Provider-agnostic CLI (`vedit`) for automated pipelines and AI directing clients.

Commands are grouped by pipeline area: `system` (contracts, platforms, providers),
`analysis` (probe, breakdown, brand), `media` (transcription, decisioning, preprocessing),
and `production` (director, project, compile, master, audit, cloud render).
"""

from __future__ import annotations

# Import order sets help-panel order (root-level media commands list before production).
# isort: off
from vedit.cli import media
from vedit.cli import production
from vedit.cli import analysis, system
from vedit.cli._app import app

# isort: on

_SYSTEM = "System & registry"
_ANALYSIS = "Analysis & brand profiling"
_PRODUCTION = "Production"

app.add_typer(system.contracts_app, name="contracts", rich_help_panel=_SYSTEM)
app.add_typer(system.platforms_app, name="platforms", rich_help_panel=_SYSTEM)
app.add_typer(system.providers_app, name="providers", rich_help_panel=_SYSTEM)
app.add_typer(analysis.probe_app, name="probe", rich_help_panel=_ANALYSIS)
app.add_typer(analysis.breakdown_app, name="breakdown", rich_help_panel=_ANALYSIS)
app.add_typer(analysis.brand_app, name="brand", rich_help_panel=_ANALYSIS)
app.add_typer(production.project_app, name="project", rich_help_panel=_PRODUCTION)
app.add_typer(production.director_app, name="director", rich_help_panel=_PRODUCTION)
app.add_typer(production.cloud_app, name="cloud", rich_help_panel=_PRODUCTION)

__all__ = ["analysis", "app", "media", "production", "system"]
