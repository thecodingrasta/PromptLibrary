"""Windows-friendly PromptLibrary tray controller and web-server supervisor."""

import ctypes
import json
import logging
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser
from ctypes import wintypes
from pathlib import Path
from socket import AF_INET, SO_REUSEADDR, SOCK_STREAM, SOL_SOCKET, socket
from typing import TYPE_CHECKING, Any, cast

from promptlibrary.config import settings

if TYPE_CHECKING:
    from PIL.Image import Image
    from pystray import Icon, MenuItem

logger = logging.getLogger("promptlibrary.tray")
SERVER_ROLE = "PROMPTLIB_SERVER_ROLE"
SERVER_ROLE_VALUE = "web-server"


def _windows_interpreter() -> str:
    interpreter = Path(sys.executable)
    if os.name == "nt":
        windowless = interpreter.with_name("pythonw.exe")
        if windowless.exists():
            return str(windowless)
    return str(interpreter)


def _acquire_tray_mutex() -> object | None:
    if os.name != "nt":
        return object()
    ctypes_api = cast(Any, ctypes)
    kernel32 = ctypes_api.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateMutexW.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR]
    kernel32.CreateMutexW.restype = wintypes.HANDLE
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL
    ctypes_api.set_last_error(0)
    handle = kernel32.CreateMutexW(None, True, "Local\\PromptLibraryTray")
    if not handle:
        raise OSError(
            ctypes_api.get_last_error(), "Windows could not create the PromptLibrary tray mutex."
        )
    if ctypes_api.get_last_error() == 183:  # ERROR_ALREADY_EXISTS
        kernel32.CloseHandle(handle)
        return None
    return cast(object, handle)


def _configure_logging() -> None:
    try:
        settings.data_dir.mkdir(parents=True, exist_ok=True)
        logging.basicConfig(
            filename=str(settings.data_dir / "tray.log"),
            level=logging.INFO,
            format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        )
    except OSError:
        logging.basicConfig(level=logging.INFO)


def _server_url(port: int | None = None) -> str:
    host = settings.host
    selected_port = port or settings.port
    address = (
        "127.0.0.1"
        if host in {"0.0.0.0", "localhost"}  # noqa: S104 - browser address, not a bind.
        else "[::1]"
        if host == "::"
        else f"[{host}]"
        if ":" in host
        else host
    )
    return settings.public_origin or f"http://{address}:{selected_port}"


def _port_available(port: int) -> bool:
    with socket(AF_INET, SOCK_STREAM) as listener:
        listener.setsockopt(SOL_SOCKET, SO_REUSEADDR, 1)
        try:
            listener.bind(("127.0.0.1", port))
        except OSError:
            return False
    return True


def _select_port() -> int:
    configured_port = settings.port
    available_port: int | None = None
    for port in range(configured_port, configured_port + 11):
        if _probe_server(_server_url(port)):
            return port
        if available_port is None and _port_available(port):
            available_port = port
    if available_port is not None:
        if available_port != configured_port:
            logger.warning(
                "PromptLibrary port %s is unavailable; using available loopback port %s",
                configured_port,
                available_port,
            )
        return available_port
    raise RuntimeError(
        f"PromptLibrary ports {configured_port}-{configured_port + 10} are unavailable."
    )


def _show_message(title: str, message: str, error: bool = False) -> None:
    if os.name == "nt":
        flags = 0x10 if error else 0x40
        ctypes_api = cast(Any, ctypes)
        ctypes_api.windll.user32.MessageBoxW(None, message, title, flags)
    else:
        logger.error("%s: %s", title, message) if error else logger.info("%s: %s", title, message)


def _notify_started(icon: "Icon", url: str) -> None:
    icon.visible = True
    message = f"Running at {url}. The tray icon is ready."
    try:
        icon.notify(message, "PromptLibrary started")
    except (AttributeError, OSError):
        _show_message("PromptLibrary started", message)


def _create_icon_image() -> "Image":
    from PIL import Image, ImageDraw

    asset = Path(__file__).parent / "static" / "app-icon.png"
    if asset.exists():
        return Image.open(asset).convert("RGBA").resize((64, 64), Image.Resampling.LANCZOS)
    image = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    drawing = ImageDraw.Draw(image)
    drawing.rounded_rectangle((8, 8, 56, 56), radius=8, fill=(79, 70, 229, 255))
    return image


def _probe_server(url: str) -> bool:
    try:
        with urllib.request.urlopen(  # noqa: S310 - Settings validates local HTTP(S) origins.
            f"{url}/health", timeout=1.0
        ) as response:
            payload = json.load(response)
        return payload.get("status") == "ok" and "version" in payload
    except (OSError, urllib.error.URLError, ValueError, KeyError):
        return False


class ServerController:
    """Own or attach to one PromptLibrary web server for the tray lifetime."""

    def __init__(self, url: str, port: int) -> None:
        self.url = url
        self.port = port
        self.process: subprocess.Popen[bytes] | None = None
        self.attached = False

    def start(self) -> None:
        if _probe_server(self.url):
            self.attached = True
            logger.info("Attached to the existing PromptLibrary server at %s", self.url)
            return
        environment = os.environ.copy()
        environment[SERVER_ROLE] = SERVER_ROLE_VALUE
        environment["PROMPTLIB_PORT"] = str(self.port)
        creation_flags = int(getattr(subprocess, "CREATE_NO_WINDOW", 0))
        self.process = subprocess.Popen(  # noqa: S603 - executable and arguments are local constants.
            [_windows_interpreter(), "-m", "promptlibrary.app"],
            cwd=str(Path(__file__).resolve().parents[2]),
            env=environment,
            creationflags=creation_flags,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline and self.process.poll() is None:
            if _probe_server(self.url):
                logger.info("Started PromptLibrary web server as PID %s", self.process.pid)
                return
            time.sleep(0.1)
        return_code = self.process.poll()
        self.process = None
        if return_code is not None and _probe_server(self.url):
            self.attached = True
            return
        raise RuntimeError(
            f"PromptLibrary could not start on {self.url}. "
            "The configured port may already be in use by another application."
        )

    def stop(self) -> None:
        if self.process is None:
            return
        self.process.terminate()
        try:
            self.process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait(timeout=5)
        self.process = None


def main() -> None:
    _configure_logging()
    tray_mutex = _acquire_tray_mutex()
    if tray_mutex is None:
        logger.info("PromptLibrary tray controller is already running")
        return
    _ = tray_mutex  # Keep the native mutex handle alive for the tray lifetime.
    try:
        import pystray
    except ImportError as error:
        message = (
            "PromptLibrary could not start its tray controller. "
            "Run the Windows setup command again to install the desktop extra."
        )
        _show_message("PromptLibrary could not start", message, error=True)
        raise SystemExit(message) from error

    try:
        selected_port = _select_port()
        url = _server_url(selected_port)
        controller = ServerController(url, selected_port)
        controller.start()
    except RuntimeError as error:
        _show_message("PromptLibrary could not start", str(error), error=True)
        raise SystemExit(str(error)) from error

    def open_browser(icon: "Icon", item: "MenuItem") -> None:
        webbrowser.open(url)

    def stop_server(icon: "Icon", item: "MenuItem") -> None:
        controller.stop()
        icon.stop()

    def quit_tray(icon: "Icon", item: "MenuItem") -> None:
        icon.stop()

    def announce_started(icon: "Icon") -> None:
        _notify_started(icon, url)

    icon = pystray.Icon(
        "PromptLibrary",
        _create_icon_image(),
        f"PromptLibrary ({selected_port})",
        menu=pystray.Menu(
            pystray.MenuItem("Open PromptLibrary", open_browser, default=True),
            pystray.MenuItem(
                "Stop PromptLibrary",
                stop_server,
                enabled=lambda _: controller.process is not None,
            ),
            pystray.MenuItem("Quit tray controller", quit_tray),
        ),
    )
    try:
        icon.run(setup=announce_started)
    finally:
        controller.stop()


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        logger.exception("PromptLibrary tray controller crashed")
        _show_message(
            "PromptLibrary could not start",
            f"The tray controller stopped unexpectedly: {error}",
            error=True,
        )
        raise
