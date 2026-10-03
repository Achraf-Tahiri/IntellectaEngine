"""Build and verify Docker using isolated inputs, no credentials or model downloads.

Run: python3 scripts/check_container.py
Requires Docker/buildx and a running daemon. Exit 2 means Docker is unavailable;
other failures are errors, never successful skips. Only build dependencies use
network access. Containers, volumes and the temporary image are removed on exit.
"""

import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]

# ONNX Runtime imports create their own diagnostic cache. Keep this explicit
# native-library probe separate from the pristine startup/persistence volumes.
NATIVE_PROBE = """
import os
from pathlib import Path
from fastembed.common.utils import define_cache_dir
from huggingface_hub import constants
import onnxruntime
import torch
assert os.getuid() == 10001
assert define_cache_dir() == Path(os.environ['FASTEMBED_CACHE_PATH'])
assert constants.HF_HOME == os.environ['HF_HOME']
assert torch.version.cuda is None
assert onnxruntime.get_device() == 'CPU'
print('PASS: native CPU libraries and real cache resolvers; no model construction')
"""


def run(*args, **kwargs):
    print("+", " ".join(str(arg) for arg in args), flush=True)
    return subprocess.run([str(arg) for arg in args], check=True, text=True, **kwargs)


def docker_json(*args):
    return json.loads(run("docker", *args, capture_output=True).stdout)


def fixture_context(directory):
    # Read only explicit public inputs. No traversal/copy of the developer's .env,
    # Git metadata, caches, credentials, or arbitrary checkout contents.
    rules = (ROOT / ".dockerignore").read_text().splitlines()
    assert "**" in rules
    inputs = set()
    for rule in rules:
        if not rule.startswith("!"):
            continue
        name = rule[1:]
        assert not any(char in name for char in "*?["), "Use explicit input paths"
        path = ROOT / name
        assert path.resolve().is_relative_to(ROOT) and not path.is_symlink()
        if path.is_file():
            inputs.add(name)
            target = directory / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)
    # Ensure no packaged module is silently omitted by the context allowlist.
    assert {str(p.relative_to(ROOT)) for p in (ROOT / "src").rglob("*.py")} <= inputs
    sentinel = "phase8-excluded-" + uuid.uuid4().hex
    forbidden = [
        ".env",
        ".env.private",
        ".git/config",
        ".venv/bin/python",
        ".streamlit/secrets.toml",
        ".aws/credentials",
        ".ssh/id_rsa",
        "container.env",
        "data/chroma/private.sqlite3",
        "uploads/private.pdf",
        "logs/private.log",
        "models/weights.bin",
        ".cache/huggingface/token",
        "src/intellectaengine/assets/private.db",
        "src/intellectaengine/assets/Chinook.db-wal",
        "src/intellectaengine/core/__pycache__/private.pyc",
        "src/intellectaengine/core/.env",
        "src/intellectaengine/core/cache/private.py",
        "credentials.json",
        "examples/field-notes.pdf",
        "examples/field-notes.txt",
        "examples/chinook-queries.json",
        "docs/screenshots/workspace-overview.png",
        "docs/screenshots/chinook-schema.png",
        "scripts/capture_demo.cjs",
    ]
    for name in forbidden:
        path = directory / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(sentinel)
    return inputs, sentinel


def health(container):
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        state = docker_json("inspect", container)[0]["State"]
        assert state["Running"], state
        status = state["Health"]["Status"]
        if status == "healthy":
            return
        assert status != "unhealthy", state["Health"]
        time.sleep(2)
    raise AssertionError("Container did not become healthy within 120 seconds")


def stop(container):
    start = time.monotonic()
    run("docker", "stop", "-t", "20", container)
    state = docker_json("inspect", container)[0]["State"]
    assert state["ExitCode"] == 0 and not state["OOMKilled"], state
    assert time.monotonic() - start < 20, "Container exhausted graceful stop timeout"
    print("PASS: SIGTERM reached Streamlit; exited 0 before stop deadline", flush=True)


def inspect_filesystem(container, sentinel):
    # Stream the exported filesystem, avoiding a second multi-GB on-disk image.
    # Context export below checks every input; this checks the actual runtime too.
    process = subprocess.Popen(["docker", "export", container], stdout=subprocess.PIPE)
    try:
        with tarfile.open(fileobj=process.stdout, mode="r|") as archive:
            for member in archive:
                name = member.name.lstrip("./")
                assert name not in ("app/.env", "app/container.env")
                assert not name.startswith(("build/", "wheels/", "app/src/"))
                if member.isfile():
                    stream = archive.extractfile(member)
                    tail = b""
                    while chunk := stream.read(1024 * 1024):
                        data = tail + chunk
                        assert sentinel.encode() not in data, f"Synthetic secret in {name}"
                        tail = data[-len(sentinel) :]
        assert process.wait(timeout=30) == 0
    finally:
        if process.poll() is None:
            process.kill()
            process.wait()
    print("PASS: runtime filesystem excludes synthetic secrets and build inputs", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    if not shutil.which("docker"):
        print(
            "UNVERIFIED: Docker CLI unavailable; build/start/health/stop/persistence/exclusions",
            file=sys.stderr,
        )
        return 2
    info = subprocess.run(["docker", "info"], capture_output=True, text=True)
    if info.returncode:
        print(
            "UNVERIFIED: Docker daemon inaccessible; no container checks ran.\n" + info.stderr,
            file=sys.stderr,
        )
        return 2
    token = "intellecta-phase8-" + uuid.uuid4().hex[:12]
    image = token + ":test"
    container = token
    volumes = [token + "-chroma", token + "-models"]
    try:
        with tempfile.TemporaryDirectory(prefix="intellecta-container-") as temporary:
            temp = Path(temporary)
            context = temp / "context"
            context.mkdir()
            expected, sentinel = fixture_context(context)
            output = temp / "filtered"
            run(
                "docker",
                "build",
                "--platform",
                "linux/amd64",
                "-f",
                "-",
                "--output",
                f"type=local,dest={output}",
                context,
                input="FROM scratch\nCOPY . /\n",
            )
            actual = {str(p.relative_to(output)) for p in output.rglob("*") if p.is_file()}
            assert actual == expected, f"Context mismatch: {actual ^ expected}"
            print(
                "PASS: actual Docker context allowlist excludes all synthetic secrets", flush=True
            )
            run("docker", "build", "--platform", "linux/amd64", "-t", image, context)
            configuration = docker_json("image", "inspect", image)[0]
            assert configuration["Config"]["User"] == "10001:10001"
            assert configuration["Architecture"] == "amd64"
            print(f"Image size: {configuration['Size']} bytes", flush=True)
            run(
                "docker",
                "run",
                "--rm",
                "--platform",
                "linux/amd64",
                "--network=none",
                "-e",
                "HF_HUB_OFFLINE=1",
                "-e",
                "TRANSFORMERS_OFFLINE=1",
                image,
                "python",
                "-c",
                NATIVE_PROBE,
            )
            for volume in volumes:
                run("docker", "volume", "create", volume)
            for mode in ("write", "read"):
                run(
                    "docker",
                    "run",
                    "-d",
                    "--name",
                    container,
                    "--platform",
                    "linux/amd64",
                    "--network=none",
                    "-e",
                    "HF_HUB_OFFLINE=1",
                    "-e",
                    "TRANSFORMERS_OFFLINE=1",
                    "--mount",
                    f"type=volume,src={volumes[0]},dst=/data/chroma",
                    "--mount",
                    f"type=volume,src={volumes[1]},dst=/home/app/.cache",
                    image,
                )
                health(container)
                run("docker", "exec", container, "python", "-m", "pip", "check")
                run(
                    "docker",
                    "exec",
                    "-i",
                    container,
                    "python",
                    "-",
                    mode,
                    input=(ROOT / "scripts/container_probe.py").read_text(),
                )
                if mode == "write":
                    inspect_filesystem(container, sentinel)
                stop(container)
                run("docker", "rm", container)
            print(
                "PASS: rebuilt image, offline startup/health, graceful stop, and volume recreation",
                flush=True,
            )
    finally:
        # Only resources uniquely owned by this invocation; never prune host data.
        subprocess.run(["docker", "rm", "-f", container], capture_output=True)
        for volume in volumes:
            subprocess.run(["docker", "volume", "rm", volume], capture_output=True)
        subprocess.run(["docker", "image", "rm", image], capture_output=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
