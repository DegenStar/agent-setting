import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path


class PackagingTests(unittest.TestCase):
    def test_wheel_contains_importable_package(self) -> None:
        project_root = Path(__file__).resolve().parents[1]

        with tempfile.TemporaryDirectory() as tmpdir:
            temp_root = Path(tmpdir)
            source_root = temp_root / "source"
            source_root.mkdir()
            shutil.copy2(project_root / "pyproject.toml", source_root)
            shutil.copy2(project_root / "README.md", source_root)
            shutil.copytree(project_root / "agent_setting", source_root / "agent_setting")

            wheel_dir = temp_root / "wheels"
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "pip",
                    "wheel",
                    ".",
                    "--no-deps",
                    "--no-build-isolation",
                    "--wheel-dir",
                    str(wheel_dir),
                ],
                cwd=source_root,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)

            wheels = list(wheel_dir.glob("agent_setting-*.whl"))
            self.assertEqual(len(wheels), 1)
            with zipfile.ZipFile(wheels[0]) as wheel:
                names = set(wheel.namelist())

            self.assertIn("agent_setting/__init__.py", names)
            self.assertIn("agent_setting/cli.py", names)


if __name__ == "__main__":
    unittest.main()
