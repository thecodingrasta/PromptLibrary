"""Optional desktop tray launcher. Browser mode does not require desktop packages."""

import logging
import threading
import time
import webbrowser
from typing import TYPE_CHECKING

import uvicorn

from promptlibrary.app import create_app
from promptlibrary.config import settings

if TYPE_CHECKING:
    from PIL.Image import Image
    from pystray import Icon, MenuItem

logger = logging.getLogger(__name__)


def _create_icon_image() -> "Image":
    from PIL import Image, ImageDraw

    image = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    drawing = ImageDraw.Draw(image)
    drawing.rounded_rectangle((8, 8, 56, 56), radius=8, fill=(79, 70, 229, 255))
    for top, end in ((20, 48), (28, 40), (36, 44), (44, 36)):
        drawing.rectangle((16, top, end, top + 3), fill=(255, 255, 255, 230))
    return image


def main() -> None:
    try:
        import pystray
    except ImportError as error:
        raise SystemExit(
            "Tray mode needs the desktop extra. Install .[desktop], or run "
            "promptlibrary in your terminal."
        ) from error
    host = settings.host
    address = (
        "127.0.0.1"
        if host == "0.0.0.0"  # noqa: S104 - this is a browser address check, not a bind.
        else "[::1]"
        if host == "::"
        else f"[{host}]"
        if ":" in host
        else host
    )
    url = settings.public_origin or f"http://{address}:{settings.port}"
    server = uvicorn.Server(
        uvicorn.Config(
            create_app(settings),
            host=host,
            port=settings.port,
            log_level="warning",
            proxy_headers=False,
        )
    )
    thread = threading.Thread(target=server.run, name="promptlibrary-http", daemon=True)
    thread.start()
    deadline = time.monotonic() + 30
    while not server.started and thread.is_alive() and time.monotonic() < deadline:
        time.sleep(0.05)
    if not server.started:
        server.should_exit = True
        thread.join(timeout=10)
        raise SystemExit(
            "The server did not start. Check the logs and whether its port is already in use."
        )

    def open_browser(icon: "Icon", item: "MenuItem") -> None:
        webbrowser.open(url)

    def stop(icon: "Icon", item: "MenuItem") -> None:
        server.should_exit = True
        icon.stop()

    try:
        icon = pystray.Icon(
            "PromptLibrary",
            _create_icon_image(),
            "PromptLibrary",
            menu=pystray.Menu(
                pystray.MenuItem("Open PromptLibrary", open_browser, default=True),
                pystray.MenuItem("Quit", stop),
            ),
        )
        icon.run()
    finally:
        server.should_exit = True
        thread.join(timeout=30)
        if thread.is_alive():
            logger.error("Server shutdown timed out. Check the running process before maintenance.")


if __name__ == "__main__":
    main()
