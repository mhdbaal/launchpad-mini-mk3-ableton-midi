import ast
from pathlib import Path
import runpy
import tempfile
import unittest
from zipfile import ZipFile


ROOT = Path(__file__).resolve().parents[1]
builder = runpy.run_path(str(ROOT / "scripts/build_remote_script.py"))


class PackageTest(unittest.TestCase):
    def test_each_archive_contains_complete_and_separate_device_overlay(self):
        with tempfile.TemporaryDirectory() as output:
            for device, package in builder["PACKAGES"].items():
                with self.subTest(device=device):
                    destination = builder["build"](device, output, "test")
                    with ZipFile(destination) as archive:
                        self.assertIsNone(archive.testzip())
                        names = archive.namelist()
                        modules = {Path(name).stem for name in names if name.endswith(".py")}
                        self.assertIn("__init__", modules)
                        self.assertIn("launchpad_{}_mk3".format(device), modules)
                        other = "mini" if device == "pro" else "pro"
                        self.assertNotIn("launchpad_{}_mk3".format(other), modules)
                        for name in names:
                            self.assertTrue(name.startswith(package + "/"))
                            if not name.endswith(".py"):
                                continue
                            tree = ast.parse(archive.read(name), filename=name)
                            compile(tree, name, "exec")
                            for node in ast.walk(tree):
                                if isinstance(node, ast.ImportFrom) and node.level == 1:
                                    imports = [node.module.split(".")[0]] if node.module else [a.name for a in node.names]
                                    for imported in imports:
                                        self.assertIn(imported, modules, (name, imported))


if __name__ == "__main__":
    unittest.main()
