"""Keep the public setup template complete and local files out of version control."""

import ast
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_example_documents_every_application_environment_variable():
    """Compare source-level configuration reads with the approved empty-secret template."""
    documented = {}
    for line_number, line in enumerate(
        (ROOT / ".env.example").read_text().splitlines(), 1
    ):
        if line.strip() and not line.lstrip().startswith("#"):
            key, value = line.split("=", 1)
            key = key.strip()
            if key in documented:
                raise AssertionError(
                    f"duplicate configuration key on line {line_number}: {key}"
                )
            documented[key] = value.strip()
    consumed = set()
    defaults = {}
    for path in (ROOT / "app").rglob("*.py"):
        tree = ast.parse(path.read_text())
        os_names = set()
        getenv_names = set()
        environ_names = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name == "os":
                        os_names.add(alias.asname or "os")
            elif isinstance(node, ast.ImportFrom) and node.module == "os":
                for alias in node.names:
                    if alias.name == "getenv":
                        getenv_names.add(alias.asname or "getenv")
                    elif alias.name == "environ":
                        environ_names.add(alias.asname or "environ")

        def is_environ(value, *, aliases=environ_names, imported_os=os_names):
            """Recognize direct and aliased os.environ expressions."""
            return (isinstance(value, ast.Name) and value.id in aliases) or (
                isinstance(value, ast.Attribute)
                and value.attr == "environ"
                and isinstance(value.value, ast.Name)
                and value.value.id in imported_os
            )

        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                function = node.func
                is_getenv = (
                    (isinstance(function, ast.Name) and function.id in getenv_names)
                    or (
                        isinstance(function, ast.Attribute)
                        and function.attr == "getenv"
                        and isinstance(function.value, ast.Name)
                        and function.value.id in os_names
                    )
                    or (
                        isinstance(function, ast.Attribute)
                        and function.attr == "get"
                        and is_environ(function.value)
                    )
                )
                if not is_getenv:
                    continue
                key = ast.literal_eval(node.args[0])
                consumed.add(key)
                if len(node.args) > 1:
                    defaults[key] = ast.literal_eval(node.args[1])
            elif isinstance(node, ast.Subscript) and is_environ(node.value):
                consumed.add(ast.literal_eval(node.slice))
    assert (
        consumed
        == set(documented)
        == {
            "KB_API_KEY",
            "KB_STORAGE_PATH",
            "GOOGLE_SPREADSHEET_ID",
            "GOOGLE_SERVICE_ACCOUNT_FILE",
            "GOOGLE_SHEET_TABS",
        }
    )
    assert documented["KB_API_KEY"] == ""
    assert documented["KB_STORAGE_PATH"] == "data/kb_topics.json"
    assert documented["GOOGLE_SPREADSHEET_ID"] == ""
    assert (
        documented["GOOGLE_SERVICE_ACCOUNT_FILE"] == "credentials/service-account.json"
    )
    assert documented["GOOGLE_SHEET_TABS"] == "Sheet1"
    assert defaults == {
        "KB_API_KEY": "",
        "KB_STORAGE_PATH": "data/kb_topics.json",
        "GOOGLE_SPREADSHEET_ID": "",
        "GOOGLE_SERVICE_ACCOUNT_FILE": "",
        "GOOGLE_SHEET_TABS": "Sheet1",
    }


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
        "credentials/prod.json",
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
