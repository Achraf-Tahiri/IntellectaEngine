"""Inspect built artifacts, rebuild the sdist, and smoke-test an isolated wheel.

Usage: uv run --frozen python scripts/check_distribution.py [--offline]
Run `uv build` first. --offline requires dependencies already present in uv's cache.
"""

import argparse
import hashlib
import os
from pathlib import Path, PurePosixPath
import subprocess
import sys
import tarfile
import tempfile
import tomllib
import zipfile


ROOT = Path(__file__).resolve().parents[1]
DIGEST = "84f5d9143ac4deebdb81650ab650e226d909e660106846b119a5c47c33f94c13"


def run(*args, **kwargs):
    subprocess.run([str(arg) for arg in args], check=True, **kwargs)


def wheel_contents(path):
    with zipfile.ZipFile(path) as archive:
        return {name: archive.read(name) for name in archive.namelist() if not name.endswith("/")}


def inspect(wheel, sdist):
    modules = {p.relative_to(ROOT / "src").as_posix() for p in (ROOT / "src").rglob("*.py")}
    sample = "intellectaengine/assets/Chinook.db"
    payload = modules | {sample}
    content = wheel_contents(wheel)
    metadata_dir = wheel.name.split("-py3-")[0] + ".dist-info/"
    expected = payload | {
        metadata_dir + name
        for name in (
            "METADATA",
            "WHEEL",
            "RECORD",
            "entry_points.txt",
            "top_level.txt",
            "licenses/LICENSE",
            "licenses/THIRD_PARTY_NOTICES.md",
        )
    }
    assert set(content) == expected, f"Unexpected/missing wheel paths: {set(content) ^ expected}"
    assert hashlib.sha256(content[sample]).hexdigest() == DIGEST
    for notice in ("LICENSE", "THIRD_PARTY_NOTICES.md"):
        assert content[metadata_dir + "licenses/" + notice] == (ROOT / notice).read_bytes()

    with tarfile.open(sdist) as archive:
        members = [member for member in archive.getmembers() if not member.isdir()]
        assert all(member.isfile() for member in members), "Links/devices are not distribution data"
        paths = {
            str(PurePosixPath(member.name).relative_to(archive.getmembers()[0].name))
            for member in members
        }
        required = {
            "pyproject.toml",
            "MANIFEST.in",
            "README.md",
            "LICENSE",
            "THIRD_PARTY_NOTICES.md",
            "app.py",
            ".env.example",
            ".python-version",
            "uv.lock",
            "requirements.txt",
            "requirements-dev.txt",
            ".streamlit/config.toml",
            ".gitignore",
            ".gitattributes",
            ".github/workflows/ci.yml",
            "Dockerfile",
            ".dockerignore",
            "compose.yaml",
            "PKG-INFO",
            "examples/README.md",
            "examples/field-notes.txt",
            "examples/field-notes.pdf",
            "examples/chinook-queries.json",
            "docs/screenshots/overview.png",
            "docs/screenshots/chinook-schema.png",
            "scripts/capture_demo.cjs",
        } | {"src/" + name for name in payload}
        for directory, pattern in (("tests", "*.py"), ("docs", "*.md"), ("scripts", "*.py")):
            required |= {p.relative_to(ROOT).as_posix() for p in (ROOT / directory).rglob(pattern)}
        generated = {
            "src/intellectaengine.egg-info/" + name
            for name in (
                "PKG-INFO",
                "SOURCES.txt",
                "dependency_links.txt",
                "entry_points.txt",
                "requires.txt",
                "top_level.txt",
            )
        }
        generated.add("setup.cfg")  # Setuptools writes sdist egg_info tag defaults.
        assert paths == required | generated, (
            f"Unexpected/missing sdist paths: {paths ^ (required | generated)}"
        )
        sample_member = next(m for m in members if m.name.endswith("/src/" + sample))
        assert hashlib.sha256(archive.extractfile(sample_member).read()).hexdigest() == DIGEST
    # These exact path allowlists exclude credentials, runtime DBs, uploads,
    # caches, logs, weights, bytecode, and environments without reading secrets.
    print(
        f"Archive allowlists passed: {len(content)} wheel files, {len(paths)} sdist files",
        flush=True,
    )
    return content


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--offline", action="store_true")
    args = parser.parse_args()
    version = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["version"]
    wheel = ROOT / "dist" / f"intellectaengine-{version}-py3-none-any.whl"
    sdist = ROOT / "dist" / f"intellectaengine-{version}.tar.gz"
    original = inspect(wheel, sdist)
    offline = ["--offline"] if args.offline else []
    with tempfile.TemporaryDirectory(prefix="intellecta-distribution-") as temporary:
        temp = Path(temporary)
        rebuilt = temp / "rebuilt"
        run("uv", "build", sdist, "--wheel", "--no-build-logs", "--out-dir", rebuilt, *offline)
        assert wheel_contents(rebuilt / wheel.name) == original, "Sdist wheel content differs"
        print("Sdist reproduced identical wheel file contents", flush=True)
        env_dir = temp / "venv"
        run("uv", "venv", "--python", sys.executable, env_dir, *offline)
        python = env_dir / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        # Treat the export as pip does: hash-pinned packages across its indexes,
        # without inheriting project-level uv constraints or source mappings.
        run(
            "uv",
            "pip",
            "install",
            "--python",
            python,
            "--no-config",
            "--index-strategy",
            "unsafe-best-match",
            "--require-hashes",
            "-r",
            ROOT / "requirements-dev.txt",
            *offline,
        )
        run("uv", "pip", "install", "--no-config", "--python", python, "--no-deps", wheel, *offline)
        run(python, "-I", "-m", "pip", "check")
        cwd = temp / "working"
        cwd.mkdir()
        # Strip known settings by NAME only; never read a private .env file.
        names = {
            line.split("=", 1)[0].strip().upper()
            for line in (ROOT / ".env.example").read_text().splitlines()
            if line.strip() and not line.lstrip().startswith("#") and "=" in line
        }
        env = {
            key: value
            for key, value in os.environ.items()
            if key.upper() not in names | {"PYTHONPATH", "PYTHONHOME", "VIRTUAL_ENV"}
            and not key.upper().startswith(
                ("HF_", "HUGGINGFACE_", "LANGCHAIN_", "LANGSMITH_", "STREAMLIT_")
            )
        }
        env.update(
            HF_HUB_OFFLINE="1",
            TRANSFORMERS_OFFLINE="1",
            HF_HOME=str(temp / "hf"),
            LANGSMITH_TRACING="false",
            STREAMLIT_BROWSER_GATHER_USAGE_STATS="false",
        )
        run(python, "-I", ROOT / "scripts/wheel_smoke.py", ROOT, cwd=cwd, env=env)
        launcher = python.parent / (
            "intellectaengine.exe" if os.name == "nt" else "intellectaengine"
        )
        help_result = subprocess.run(
            [str(launcher), "--help"], cwd=cwd, env=env, capture_output=True, text=True
        )
        assert help_result.returncode == 0 and "--server.port" in help_result.stdout
        invalid = subprocess.run(
            [str(launcher), "--not-a-streamlit-option"],
            cwd=cwd,
            env=env,
            capture_output=True,
            text=True,
        )
        assert invalid.returncode == 2, invalid.stderr
        assert not (temp / "hf").exists(), "Model cache created during smoke checks"
        print(
            "Isolated wheel install, dependency consistency, and launcher checks passed", flush=True
        )


if __name__ == "__main__":
    main()
