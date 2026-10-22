"""A compact prompt picker using the same service as the main library."""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from promptlibrary.database import get_db
from promptlibrary.routers.common import page
from promptlibrary.services.library_service import LibraryFilter, LibraryService

router = APIRouter(prefix="/widget", tags=["widget"])


@router.get("", response_class=HTMLResponse)
@router.get("/recent", response_class=HTMLResponse)
@router.get("/search", response_class=HTMLResponse)
async def widget_page(request: Request, q: str = "") -> HTMLResponse:
    async with get_db(request.app.state.settings) as db:
        items, total = await LibraryService(db).list_items(LibraryFilter(q=q, item_type="prompt"))
        return page(
            request,
            "pages/widget.html",
            {"items": items, "total": total, "q": q},
            title="Prompt picker | PromptLibrary",
            url="/widget",
        )
