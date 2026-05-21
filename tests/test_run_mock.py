"""Smoke tests for the top-level pipeline using built-in mock data."""
from __future__ import annotations

import run


def test_run_with_mock_data_writes_html(tmp_path):
    output = tmp_path / "index.html"

    status = run.main(["--mock-data", "--output", output.as_posix()])

    html = output.read_text(encoding="utf-8")
    assert status == 0
    assert "AI Daily Digest" in html
    assert "Sam Altman" in html
    assert "OpenAI Blog" in html
    assert "Latent Space" in html
    assert "example/agent-runtime" in html
    assert "Google DeepMind" in html


def test_run_with_mock_data_removes_stale_output_cname(tmp_path):
    output = tmp_path / "index.html"
    stale_cname = tmp_path / "CNAME"
    stale_cname.write_text("old.example.com\n", encoding="utf-8")

    status = run.main(["--mock-data", "--output", output.as_posix()])

    assert status == 0
    assert not stale_cname.exists()
