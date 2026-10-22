"""Documentation pages matched to the shipped functionality."""

from functools import lru_cache
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from promptlibrary.routers.common import page
from promptlibrary.services.markdown_service import render_markdown

router = APIRouter(tags=["pages"])


@lru_cache(maxsize=1)
def rendered_guide() -> str:
    path = Path(__file__).parents[1] / "content" / "user-guide.md"
    return render_markdown(path.read_text(encoding="utf-8"))


@router.get("/help", response_class=HTMLResponse)
async def help_page(request: Request) -> HTMLResponse:
    return page(
        request,
        "pages/help.html",
        {"help_html": rendered_guide()},
        title="Help | PromptLibrary",
        section="help",
    )


@router.get("/about", response_class=HTMLResponse)
async def about_page(request: Request) -> HTMLResponse:
    return page(request, "pages/about.html", title="About | PromptLibrary", section="about")
