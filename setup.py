from __future__ import annotations

import hashlib
import os
from pathlib import Path
import re
import shutil
import site
import subprocess

from setuptools import setup
from setuptools.command.build_py import build_py as _build_py
from setuptools.command.install import install as _install

try:
    from setuptools.command.develop import develop as _develop
except Exception:  # pragma: no cover
    _develop = None

try:
    from setuptools.command.editable_wheel import editable_wheel as _editable_wheel
except Exception:  # pragma: no cover
    _editable_wheel = None


_WEBUI_BUILT = False


def _iter_site_packages_dirs() -> list[Path]:
    out: list[Path] = []
    for getter in (site.getsitepackages, lambda: [site.getusersitepackages()]):
        try:
            values = getter()
        except Exception:
            continue
        for entry in values:
            try:
                path = Path(str(entry)).resolve()
            except Exception:
                continue
            if path not in out:
                out.append(path)
    return out


def _cleanup_legacy_snowl_egg(announce: callable) -> None:
    pattern = re.compile(r"(^|/)\.?snowl-[^/]+\.egg$")
    for sp_dir in _iter_site_packages_dirs():
        if not sp_dir.exists():
            continue
        easy_install = sp_dir / "easy-install.pth"
        if easy_install.exists():
            try:
                lines = easy_install.read_text(encoding="utf-8").splitlines()
                kept: list[str] = []
                removed: list[str] = []
                for line in lines:
                    stripped = line.strip()
                    if stripped and pattern.search(stripped.replace("\\", "/")):
                        removed.append(stripped)
                        continue
                    kept.append(line)
                if removed:
                    easy_install.write_text("\n".join(kept) + ("\n" if kept else ""), encoding="utf-8")
                    announce(f"[install] removed stale snowl egg entries from {easy_install}", 2)
            except Exception as exc:
                announce(f"[install] warning: failed to rewrite {easy_install}: {exc}", 2)
        for entry in sp_dir.glob("snowl-*.egg"):
            try:
                if entry.is_dir():
                    shutil.rmtree(entry)
                else:
                    entry.unlink()
                announce(f"[install] removed stale egg artifact: {entry}", 2)
            except Exception as exc:
                announce(f"[install] warning: failed to remove {entry}: {exc}", 2)


def _lock_hash(source_dir: Path) -> str:
    lock_path = source_dir / "package-lock.json"
    pkg_path = source_dir / "package.json"
    if lock_path.exists():
        payload = lock_path.read_bytes()
    elif pkg_path.exists():
        payload = pkg_path.read_bytes()
    else:
        raise RuntimeError(f"webui package metadata missing: {pkg_path}")
    return hashlib.sha256(payload).hexdigest()


def _ensure_node_available() -> None:
    node_path = shutil.which("node")
    npm_path = shutil.which("npm")
    if node_path is None or npm_path is None:
        raise RuntimeError("Node.js + npm are required to build Snowl Web UI (Node LTS >=18).")
    try:
        done = subprocess.run([node_path, "--version"], check=True, capture_output=True, text=True)
    except Exception as exc:  # pragma: no cover
        raise RuntimeError("failed to execute `node --version`.") from exc
    version_text = (done.stdout or done.stderr or "").strip()
    m = re.search(r"v?(\d+)\.", version_text)
    if not m:
        raise RuntimeError(f"unable to parse Node.js version from: {version_text or '(empty)'}")
    if int(m.group(1)) < 18:
        raise RuntimeError(f"Node.js >=18 is required, found: {version_text}")


def _resolve_webui_targets(project_root: Path) -> list[Path]:
    targets: list[Path] = []
    repo_webui = project_root / "webui"
    bundled_webui = project_root / "snowl" / "_webui"
    if (repo_webui / "package.json").exists():
        targets.append(repo_webui)
    if (bundled_webui / "package.json").exists() and bundled_webui not in targets:
        targets.append(bundled_webui)
    return targets


def _build_webui_once(announce: callable) -> None:
    global _WEBUI_BUILT
    _cleanup_legacy_snowl_egg(announce)
    if _WEBUI_BUILT:
        return
    if os.getenv("SNOWL_SKIP_WEBUI_BUILD", "0").lower() in {"1", "true", "on", "yes"}:
        announce("[webui] skipped by SNOWL_SKIP_WEBUI_BUILD=1", 2)
        _WEBUI_BUILT = True
        return
    project_root = Path(__file__).resolve().parent
    targets = _resolve_webui_targets(project_root)
    if not targets:
        announce("[webui] no webui package.json found; skip install-time build", 2)
        _WEBUI_BUILT = True
        return
    _ensure_node_available()
    for app_dir in targets:
        announce(f"[webui] npm ci ({app_dir})", 2)
        subprocess.run(["npm", "ci"], cwd=str(app_dir), check=True)
        announce(f"[webui] npm run build ({app_dir})", 2)
        subprocess.run(["npm", "run", "build"], cwd=str(app_dir), check=True)
        (app_dir / ".deps-lock.sha256").write_text(_lock_hash(app_dir), encoding="utf-8")
    _WEBUI_BUILT = True


class BuildPy(_build_py):
    def run(self):
        _cleanup_legacy_snowl_egg(self.announce)
        _build_webui_once(self.announce)
        super().run()
        _cleanup_legacy_snowl_egg(self.announce)


class Install(_install):
    def run(self):
        _cleanup_legacy_snowl_egg(self.announce)
        _build_webui_once(self.announce)
        super().run()
        _cleanup_legacy_snowl_egg(self.announce)


if _develop is not None:

    class Develop(_develop):
        def run(self):
            _cleanup_legacy_snowl_egg(self.announce)
            _build_webui_once(self.announce)
            super().run()
            _cleanup_legacy_snowl_egg(self.announce)

else:  # pragma: no cover
    Develop = None


if _editable_wheel is not None:

    class EditableWheel(_editable_wheel):
        def run(self):
            _cleanup_legacy_snowl_egg(self.announce)
            _build_webui_once(self.announce)
            super().run()
            _cleanup_legacy_snowl_egg(self.announce)

else:  # pragma: no cover
    EditableWheel = None


_CMDCLASS: dict[str, type] = {
    "build_py": BuildPy,
    "install": Install,
}
if Develop is not None:
    _CMDCLASS["develop"] = Develop
if EditableWheel is not None:
    _CMDCLASS["editable_wheel"] = EditableWheel


# Build metadata is declared in pyproject.toml (PEP 621).
setup(cmdclass=_CMDCLASS)
