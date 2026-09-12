#!/usr/bin/env python3
"""Assemble the shared modules and one device overlay into an installable ZIP."""
import argparse
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile


ROOT = Path(__file__).resolve().parents[1]
PACKAGES = {"mini": "Launchpad_Mini_MK3", "pro": "Launchpad_Pro_MK3_Custom"}


def build(device, output_dir, version=None):
    shared = {p.name: p for p in ROOT.glob("*.py")}
    overlay = {p.name: p for p in (ROOT / device).glob("*.py")}
    collisions = shared.keys() & overlay.keys()
    if collisions:
        raise ValueError("Shared/overlay collisions: {}".format(sorted(collisions)))
    modules = dict(shared, **overlay)
    for name in ("__init__.py", "elements.py", "device_profile.py",
                 "sysex_ids.py", "launchpad_{}_mk3.py".format(device)):
        if name not in modules:
            raise ValueError("Missing required module: " + name)
    for name, path in modules.items():
        compile(path.read_bytes(), name, "exec")
    package = PACKAGES[device]
    suffix = "_" + version if version else ""
    if any(c in suffix for c in ("/", "\\")):
        raise ValueError("Version must not contain path separators")
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    destination = output_dir / (package + suffix + ".zip")
    with ZipFile(destination, "w", compression=ZIP_DEFLATED) as archive:
        for name, path in sorted(modules.items()):
            archive.write(path, package + "/" + name)
        archive.write(ROOT / "README.md", package + "/README.md")
    return destination


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("device", choices=PACKAGES)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "dist")
    parser.add_argument("--version")
    args = parser.parse_args()
    print(build(args.device, args.output_dir, args.version))
