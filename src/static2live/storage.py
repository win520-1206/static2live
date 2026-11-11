import hashlib
import json
import os
import re
from pathlib import Path


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def safe_resource(root, relative):
    if not isinstance(relative, str) or "\\" in relative or Path(relative).is_absolute():
        raise ValueError("资源路径必须是相对 POSIX 路径")
    root = Path(root).resolve()
    resolved = (root / relative).resolve()
    if not resolved.is_relative_to(root) or resolved == root:
        raise ValueError("资源路径越界")
    return resolved


def allocate_version(output, stem):
    stem = re.sub(r"[^\w.-]+", "_", stem, flags=re.UNICODE).strip(". ")[:80] or "image"
    # Prefix Windows reserved names, even with an extension.
    if stem.split(".")[0].upper() in {"CON", "PRN", "AUX", "NUL", *[f"COM{i}" for i in range(1,10)], *[f"LPT{i}" for i in range(1,10)]}:
        stem = "image_" + stem
    parent = Path(output).resolve() / stem
    parent.mkdir(parents=True, exist_ok=True)
    for number in range(1, 1000000):
        version = parent / f"v{number:03d}"
        try:
            version.mkdir()  # atomic across concurrent generators
            return version
        except FileExistsError:
            continue
    raise ValueError("版本目录数量超出限制")


def check_overwrite(destination, inputs):
    destination = Path(destination)
    if destination.is_symlink() or not destination.is_dir():
        raise ValueError("--overwrite 必须指向现有受管理版本目录")
    destination = destination.resolve()
    if any(Path(p).resolve().is_relative_to(destination) for p in inputs if p):
        raise ValueError("禁止覆盖包含输入素材的目录")
    manifest = read_json(destination / "manifest.json")
    if manifest.get("generator") != "static2live" or not re.fullmatch(r"v\d{3,}", destination.name):
        raise ValueError("拒绝覆盖非 Static2Live 版本目录")
    managed = set(manifest.get("resources", {})) | {"manifest.json", "validation.json"}
    for entry in destination.rglob("*"):
        if entry.is_symlink():
            raise ValueError("拒绝覆盖含符号链接的目录")
        if entry.is_file() and entry.relative_to(destination).as_posix() not in managed:
            raise ValueError(f"拒绝覆盖含用户文件的目录: {entry.name}")
    return destination


def default_model_cache():
    base = os.environ.get("LOCALAPPDATA") if os.name == "nt" else os.environ.get("XDG_CACHE_HOME")
    return Path(base or Path.home() / ".cache") / "static2live" / "models"
