"""Download the exact wheels pinned in uv.lock for the running interpreter's platform.

usage: python fetch_wheels.py <uv.lock> <requirements.txt> <out_dir>
Every file is checked against the sha256 recorded in uv.lock.
"""

import hashlib
import sys
import time
import tomllib
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from pip._vendor.packaging.requirements import Requirement
from pip._vendor.packaging.tags import sys_tags
from pip._vendor.packaging.utils import canonicalize_name, parse_wheel_filename

lock_path, req_path, out_dir = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
out_dir.mkdir(parents=True, exist_ok=True)

lock = tomllib.loads(lock_path.read_text(encoding="utf-8"))
by_name = {}
for pkg in lock["package"]:
    by_name.setdefault(canonicalize_name(pkg["name"]), []).append(pkg)

wanted = []
for line in req_path.read_text(encoding="utf-8").splitlines():
    line = line.strip()
    if not line or line.startswith("#") or line.startswith("-"):
        continue
    req = Requirement(line)
    if req.marker and not req.marker.evaluate():
        continue
    version = next(iter(req.specifier)).version
    wanted.append((canonicalize_name(req.name), version))

priority = {tag: i for i, tag in enumerate(sys_tags())}


def pick(name, version):
    pkg = next(p for p in by_name[name] if p["version"] == version)
    best = None
    for w in pkg.get("wheels", []):
        fname = w["url"].rsplit("/", 1)[1].replace("%2B", "+")
        tags = parse_wheel_filename(fname)[3]
        rank = min((priority[t] for t in tags if t in priority), default=None)
        if rank is not None and (best is None or rank < best[0]):
            best = (rank, fname, w)
    if best is None:
        return None, pkg.get("sdist")
    return best[1], best[2]


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def fetch(item):
    name, version = item
    fname, info = pick(name, version)
    if fname is None:
        return f"NO-WHEEL {name}=={version} (sdist: {info and info['url']})"
    expected = info["hash"].split(":", 1)[1]
    dest = out_dir / fname
    if dest.exists() and sha256(dest) == expected:
        return f"ok (have) {fname}"
    last = None
    for attempt in range(6):
        try:
            tmp = dest.with_suffix(".part")
            with urllib.request.urlopen(info["url"], timeout=60) as r, open(tmp, "wb") as f:
                while chunk := r.read(1 << 20):
                    f.write(chunk)
            if sha256(tmp) != expected:
                tmp.unlink()
                raise ValueError("hash mismatch")
            tmp.replace(dest)
            return f"ok {fname}"
        except Exception as exc:  # noqa: BLE001 - retry any network error
            last = exc
            time.sleep(2 + attempt * 3)
    return f"FAILED {fname}: {last}"


with ThreadPoolExecutor(6) as pool:
    results = list(pool.map(fetch, wanted))

for r in results:
    print(r)
bad = [r for r in results if not r.startswith("ok")]
print(f"\n{len(results)} packages, {len(bad)} problems")
sys.exit(1 if bad else 0)
