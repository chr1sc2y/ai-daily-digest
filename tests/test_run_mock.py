"""Smoke tests for the top-level pipeline using built-in mock data."""
from __future__ import annotations

import json

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


def test_run_with_mock_data_copies_root_cname(tmp_path):
    output = tmp_path / "index.html"
    output_cname = tmp_path / "CNAME"
    output_cname.write_text("old.example.com\n", encoding="utf-8")

    status = run.main(["--mock-data", "--output", output.as_posix()])

    assert status == 0
    assert output_cname.read_text(encoding="utf-8") == "ai.prov1dence.top\n"


def test_run_with_mock_data_writes_normalized_json(tmp_path):
    output = tmp_path / "index.html"
    data_output = tmp_path / "data" / "2026-05-21.json"

    status = run.main(
        [
            "--mock-data",
            "--output",
            output.as_posix(),
            "--data-output",
            data_output.as_posix(),
        ]
    )

    payload = json.loads(data_output.read_text(encoding="utf-8"))
    assert status == 0
    assert payload["schema_version"] == 1
    assert payload["counts"] == {
        "x": 2,
        "blogs": 2,
        "podcasts": 1,
        "releases": 1,
        "videos": 1,
    }
    assert payload["items"]["x"][0]["source_name"] == "Sam Altman"
    assert payload["items"]["x"][0]["published"].endswith("+00:00")
