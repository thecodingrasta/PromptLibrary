from pathlib import Path

from promptlibrary import tray


class FakeProcess:
    pid = 4242

    def __init__(self) -> None:
        self.returncode: int | None = None
        self.terminated = False

    def poll(self) -> int | None:
        return self.returncode

    def terminate(self) -> None:
        self.terminated = True
        self.returncode = 0

    def wait(self, timeout: float | None = None) -> int:
        return self.returncode or 0


def test_tray_uses_branded_icon_asset() -> None:
    asset = Path(tray.__file__).parent / "static" / "app-icon.png"
    assert asset.exists()


def test_controller_starts_identifiable_web_server(monkeypatch) -> None:
    process = FakeProcess()
    calls: list[list[str]] = []

    def fake_popen(command, **kwargs):
        calls.append(command)
        return process

    probes = iter([False, True])
    monkeypatch.setattr(tray, "_probe_server", lambda _url: next(probes))
    monkeypatch.setattr(tray.subprocess, "Popen", fake_popen)
    controller = tray.ServerController("http://127.0.0.1:8000", 8000)

    controller.start()

    assert calls == [[tray._windows_interpreter(), "-m", "promptlibrary.app"]]
    assert controller.process is process

    controller.stop()
    assert process.terminated
    assert controller.process is None


def test_controller_attaches_to_existing_promptlibrary(monkeypatch) -> None:
    monkeypatch.setattr(tray, "_probe_server", lambda _url: True)
    controller = tray.ServerController("http://127.0.0.1:8000", 8000)

    controller.start()

    assert controller.attached
    assert controller.process is None


def test_start_notification_makes_icon_visible() -> None:
    class FakeIcon:
        visible = False
        notifications: list[tuple[str, str]] = []

        def notify(self, message: str, title: str) -> None:
            self.notifications.append((title, message))

    icon = FakeIcon()
    tray._notify_started(icon, "http://127.0.0.1:8001")

    assert icon.visible
    assert icon.notifications == [
        ("PromptLibrary started", "Running at http://127.0.0.1:8001. The tray icon is ready.")
    ]
