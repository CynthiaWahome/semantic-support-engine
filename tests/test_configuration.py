"""Keep the public setup template complete and local files out of version control."""

import ast
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_example_documents_every_application_environment_variable():
    """Compare source-level configuration reads with the approved empty-secret template."""
    documented = {}
    for line in (ROOT / ".env.example").read_text().splitlines():
        if line.strip() and not line.lstrip().startswith("#"):
            key, value = line.split("=", 1)
            documented[key.strip()] = value.strip()
    consumed = set()
    for path in (ROOT / "app").rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.Call) and ast.unparse(node.func) in {
                "os.environ.get",
                "os.getenv",
            }:
                consumed.add(ast.literal_eval(node.args[0]))
            elif (
                isinstance(node, ast.Subscript)
                and ast.unparse(node.value) == "os.environ"
            ):
                consumed.add(ast.literal_eval(node.slice))
    assert consumed == set(documented) == {"KB_API_KEY", "KB_STORAGE_PATH"}
    assert documented["KB_API_KEY"] == ""
    assert documented["KB_STORAGE_PATH"] == "data/kb_topics.json"


@pytest.fixture
def ignore_repository(tmp_path):
    """Check copied ignore rules in an empty repo, never inspecting private files."""
    subprocess.run(["git", "init", "--quiet", str(tmp_path)], check=True)
    (tmp_path / ".gitignore").write_text((ROOT / ".gitignore").read_text())
    return tmp_path


@pytest.mark.parametrize(
    "path",
    [
        ".env",
        ".env.local",
        ".env.production",
        ".env.example.bak",
        "nested/.env",
        "nested/.env.example",
        ".envrc",
        ".direnv/local",
        "credentials.json",
        "credentials-dev.json",
        "service_account-dev.json",
        "service-account-dev.json",
        "application_default_credentials.json",
        "client_secret-demo.json",
        "token.json",
        "secrets/example.txt",
        ".secrets/example.txt",
        "private.pem",
        "private.key",
        "certificate.p12",
        "certificate.pfx",
        "private.jks",
        "private.keystore",
        ".venv/bin/python",
        ".venv-test/bin/python",
        "venv/bin/python",
        "env/bin/python",
        "app/__pycache__/cached.pyc",
        ".pytest_cache/result",
        ".ruff_cache/result",
        ".mypy_cache/result",
        ".hypothesis/example",
        ".tox/result",
        ".nox/result",
        ".cache/result",
        ".coverage",
        ".coverage.worker",
        "coverage.xml",
        "htmlcov/index.html",
        "build/output",
        "dist/output",
        "package.egg-info/info",
        ".DS_Store",
        ".idea/config.xml",
        ".vscode/settings.json",
        "example.swp",
        "example.swo",
        "roadmap.md",
        "notes/planning.md",
        "data/export.csv",
        "output/answers.json",
        "logs/run.txt",
        "runtime.log",
    ],
)
def test_private_and_generated_paths_are_ignored(ignore_repository, path):
    """Verify hypothetical secret/artifact names without creating those files."""
    result = subprocess.run(
        [
            "git",
            "-c",
            "core.excludesFile=/dev/null",
            "check-ignore",
            "--no-index",
            "--quiet",
            "--",
            path,
        ],
        cwd=ignore_repository,
        check=False,
    )
    assert result.returncode == 0


@pytest.mark.parametrize(
    "path",
    [
        ".env.example",
        ".gitignore",
        "README.md",
        "pyproject.toml",
        "uv.lock",
        ".github/PULL_REQUEST_TEMPLATE.md",
        "app/core/security.py",
        "tests/fixtures/faq.csv",
        "tests/fixtures/questions.json",
    ],
)
def test_source_template_and_fixtures_remain_trackable(ignore_repository, path):
    """Avoid blanket data-format ignores that would hide legitimate source fixtures."""
    result = subprocess.run(
        [
            "git",
            "-c",
            "core.excludesFile=/dev/null",
            "check-ignore",
            "--no-index",
            "--quiet",
            "--",
            path,
        ],
        cwd=ignore_repository,
        check=False,
    )
    assert result.returncode == 1
