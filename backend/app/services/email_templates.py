"""Renders the HTML email bodies from app/templates/emails/. Autoescaping is on, so template
values (a workspace name, an inviter's name) can never break out of the markup; only the
`url` values we build ourselves are trusted to appear in an `href`."""

from functools import lru_cache
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape

TEMPLATES_DIR = Path(__file__).resolve().parents[1] / "templates" / "emails"


@lru_cache
def _env() -> Environment:
    return Environment(
        loader=FileSystemLoader(TEMPLATES_DIR), autoescape=select_autoescape(["html"])
    )


def render(template_name: str, **context: Any) -> str:
    return _env().get_template(template_name).render(**context)
