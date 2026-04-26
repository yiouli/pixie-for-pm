import pytest

from pixie_for_pm import main as cli


def test_main_start_command_runs_combined_server(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[bool] = []

    def fake_run_server(*, start_discord_bot: bool) -> None:
        calls.append(start_discord_bot)

    monkeypatch.setattr(cli, "run_server", fake_run_server)

    cli.main()

    assert calls == [True]
