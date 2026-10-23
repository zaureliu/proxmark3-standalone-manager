"""Cada firmware compilado tem metadados próprios. Imagem incompatível não é reutilizada."""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from pm3manager.build.compiler import validate_fullimage
from pm3manager.models import BuildConfig, Environment
from pm3manager.textutil import sha256_bytes, sha256_file


@dataclass
class CacheEntry:
    directory: Path
    image: Path
    metadata: dict

    @property
    def module_id(self) -> str:
        return str(self.metadata.get("module_id", ""))


class FirmwareCache:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def _key(self, env: Environment, config: BuildConfig, toolchain: str) -> str:
        payload = {
            "version": env.version,
            "commit": env.commit,
            "fingerprint": env.source_fingerprint,
            "toolchain": toolchain,
            **config.identity(),
        }
        raw = json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
        return f"{config.standalone}-{sha256_bytes(raw)[:16]}"

    def lookup(self, env: Environment, config: BuildConfig, toolchain: str) -> CacheEntry | None:
        directory = self.root / self._key(env, config, toolchain)
        return self._read(directory, env, config, toolchain)

    def status(self, env: Environment, config: BuildConfig, toolchain: str) -> str:
        if toolchain:
            return "Em cache" if self.lookup(env, config, toolchain) else "Não compilado"
        provisional = self._provisional(env, config)
        if provisional is None:
            return "Não compilado"
        return "Em cache"

    def store(
        self,
        env: Environment,
        config: BuildConfig,
        toolchain: str,
        image: Path,
    ) -> CacheEntry:
        digest = validate_fullimage(image, env.version)
        directory = self.root / self._key(env, config, toolchain)
        self._discard(directory)
        directory.mkdir(parents=True)
        destination = directory / "fullimage.elf"
        shutil.copy2(image, destination)
        metadata = {
            "module_id": config.standalone,
            "repo_version": env.version,
            "commit": env.commit,
            "build_time": env.build_time,
            "source_fingerprint": env.source_fingerprint,
            "toolchain": toolchain,
            "config": config.identity(),
            "artifact_sha256": digest,
            "artifact_size": destination.stat().st_size,
            "built_at": datetime.now(timezone.utc).isoformat(),
        }
        (directory / "metadata.json").write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        stored = sha256_file(destination)
        if stored != digest:
            raise OSError("A cópia em cache não confere com o artefato compilado.")
        return CacheEntry(directory, destination, metadata)

    def _provisional(self, env: Environment, config: BuildConfig) -> CacheEntry | None:
        prefix = f"{config.standalone}-"
        for directory in self.root.glob(f"{prefix}*"):
            entry = self._read(directory, env, config)
            if entry is None:
                continue
            if entry.metadata.get("config") == config.identity():
                return entry
        return None

    def _is_entry(self, directory: Path) -> bool:
        if directory.is_symlink():
            return False
        try:
            resolved = directory.resolve()
            root = self.root.resolve()
        except OSError:
            return False
        return resolved.parent == root

    def _discard(self, directory: Path) -> None:
        if not directory.exists() and not directory.is_symlink():
            return
        if not self._is_entry(directory):
            raise OSError(f"Cache recusado fora do diretório esperado: {directory}")
        shutil.rmtree(directory)

    def _read(
        self,
        directory: Path,
        env: Environment,
        config: BuildConfig | None = None,
        toolchain: str | None = None,
    ) -> CacheEntry | None:
        if not self._is_entry(directory):
            return None
        meta_path = directory / "metadata.json"
        image = directory / "fullimage.elf"
        if not meta_path.is_file() or not image.is_file():
            return None
        if image.is_symlink():
            try:
                image.resolve().relative_to(directory.resolve())
            except (OSError, ValueError):
                return None
        try:
            metadata = json.loads(meta_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        if metadata.get("repo_version") != env.version or metadata.get("commit") != env.commit:
            return None
        if metadata.get("source_fingerprint") != env.source_fingerprint:
            return None
        if config is not None and metadata.get("config") != config.identity():
            return None
        if toolchain is not None and metadata.get("toolchain") != toolchain:
            return None
        try:
            digest = validate_fullimage(image, env.version)
        except Exception:
            return None
        if digest != metadata.get("artifact_sha256"):
            return None
        return CacheEntry(directory, image, metadata)
