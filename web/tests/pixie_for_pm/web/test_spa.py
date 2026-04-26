from pathlib import Path

from fastapi.testclient import TestClient

from pixie_for_pm.config.settings import load_settings
from pixie_for_pm.web.app import create_app
from pixie_for_pm.web.store import InMemoryConnectionStore

_FERNET_KEY = "j0aN3s-cLScfv0GfNyG8t0UyONn7y8u2s6o6cLs1hYw="


def _settings() -> dict[str, str]:
    return {
        "DISCORD_BOT_TOKEN": "discord-token",
        "DISCORD_GUILD_ID": "123",
        "DISCORD_ORCHESTRATION_CHANNEL_ID": "456",
        "WEB_APP_URL": "https://app.pixie.test",
        "CREDENTIALS_ENCRYPTION_KEY": _FERNET_KEY,
        "SESSION_SECRET_KEY": _FERNET_KEY,
    }


def _write_file(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_root_serves_built_frontend_index(tmp_path: Path) -> None:
    dist_dir = tmp_path / "dist"
    _write_file(dist_dir / "index.html", "<html><body>pixie-spa</body></html>")

    app = create_app(
        load_settings(_settings()),
        store=InMemoryConnectionStore(),
        frontend_dist_dir=dist_dir,
    )

    response = TestClient(app).get("/")

    assert response.status_code == 200
    assert "pixie-spa" in response.text


def test_spa_routes_fall_back_to_index_html(tmp_path: Path) -> None:
    dist_dir = tmp_path / "dist"
    _write_file(dist_dir / "index.html", "<html><body>pixie-settings</body></html>")

    app = create_app(
        load_settings(_settings()),
        store=InMemoryConnectionStore(),
        frontend_dist_dir=dist_dir,
    )

    response = TestClient(app).get("/settings")

    assert response.status_code == 200
    assert "pixie-settings" in response.text


def test_frontend_assets_are_served_from_dist(tmp_path: Path) -> None:
    dist_dir = tmp_path / "dist"
    _write_file(dist_dir / "index.html", "<html></html>")
    _write_file(dist_dir / "assets" / "app.js", "console.log('pixie');")

    app = create_app(
        load_settings(_settings()),
        store=InMemoryConnectionStore(),
        frontend_dist_dir=dist_dir,
    )

    response = TestClient(app).get("/assets/app.js")

    assert response.status_code == 200
    assert "console.log('pixie');" in response.text


def test_unknown_api_routes_do_not_fall_back_to_frontend(tmp_path: Path) -> None:
    dist_dir = tmp_path / "dist"
    _write_file(dist_dir / "index.html", "<html><body>pixie-spa</body></html>")

    app = create_app(
        load_settings(_settings()),
        store=InMemoryConnectionStore(),
        frontend_dist_dir=dist_dir,
    )

    response = TestClient(app).get("/api/does-not-exist")

    assert response.status_code == 404
