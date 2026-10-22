"""Portable library snapshots with validated merge or explicit replacement."""

from typing import Annotated, Literal

from fastapi import APIRouter, File, Form, Request, Response, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse

from promptlibrary.database import get_db
from promptlibrary.routers.sync import backup_page
from promptlibrary.services.export_service import MAX_SNAPSHOT_BYTES, ExportService, ImportMode

router = APIRouter(tags=["import/export"])


@router.get("/export/json")
async def export_json(request: Request) -> Response:
    async with get_db(request.app.state.settings) as db:
        snapshot = await ExportService(db).export_all()
        content = snapshot.model_dump_json(indent=2)
        ExportService._check_size(content)
        return Response(
            content,
            media_type="application/json",
            headers={"Content-Disposition": "attachment; filename=promptlibrary_export.json"},
        )


@router.get("/export/xml")
async def export_xml(request: Request) -> Response:
    async with get_db(request.app.state.settings) as db:
        content = await ExportService(db).export_xml()
        ExportService._check_size(content)
        return Response(
            content,
            media_type="application/xml",
            headers={"Content-Disposition": "attachment; filename=promptlibrary_export.xml"},
        )


@router.post("/import", response_class=HTMLResponse)
async def import_snapshot(
    request: Request,
    file: Annotated[UploadFile, File()],
    file_format: Annotated[Literal["json", "xml"], Form(alias="format")] = "json",
    mode: Annotated[ImportMode, Form()] = "merge",
) -> HTMLResponse:
    content = await file.read(MAX_SNAPSHOT_BYTES + 1)
    if len(content) > MAX_SNAPSHOT_BYTES:
        raise ValueError("The snapshot exceeds the supported 25 MiB limit.")
    async with get_db(request.app.state.settings, write=True) as db:
        service = ExportService(db)
        if file_format == "json":
            result = await service.import_json(content.decode("utf-8-sig"), mode)
        else:
            result = await service.import_xml(content.decode("utf-8-sig"), mode)
        await db.commit()
        message = (
            f"Imported {result.imported_count} records; "
            f"skipped {result.skipped_count} identical records."
        )
        if result.safety_backup:
            message += " A pre-restore safety snapshot was saved."
        return await backup_page(request, db, message)


@router.post("/export/import/{file_format}")
async def import_api(
    request: Request,
    file_format: Literal["json", "xml"],
    file: Annotated[UploadFile, File()],
    mode: Annotated[ImportMode, Form()] = "merge",
) -> JSONResponse:
    content = await file.read(MAX_SNAPSHOT_BYTES + 1)
    if len(content) > MAX_SNAPSHOT_BYTES:
        raise ValueError("The snapshot exceeds the supported 25 MiB limit.")
    async with get_db(request.app.state.settings, write=True) as db:
        service = ExportService(db)
        if file_format == "json":
            result = await service.import_json(content.decode("utf-8-sig"), mode)
        else:
            result = await service.import_xml(content.decode("utf-8-sig"), mode)
        await db.commit()
        return JSONResponse(
            {
                "imported": result.imported_count,
                "skipped": result.skipped_count,
                "replaced": result.replaced,
                "safety_backup": result.safety_backup,
            }
        )
