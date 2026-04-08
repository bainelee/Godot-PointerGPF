import shutil
import subprocess
import unittest
from pathlib import Path


class StartMcpConfigTests(unittest.TestCase):
    def test_start_script_prints_stdio_safe_cursor_config(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        script = repo_root / "install" / "start-mcp.ps1"
        self.assertTrue(script.exists(), f"missing script: {script}")

        pwsh = shutil.which("pwsh") or shutil.which("powershell")
        self.assertIsNotNone(pwsh, "PowerShell is required for this test")

        proc = subprocess.run(
            [pwsh, "-ExecutionPolicy", "Bypass", "-File", str(script), "-PythonExe", "python"],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(proc.returncode, 0, msg=f"{proc.stdout}\n{proc.stderr}")
        self.assertIn('"command": "', proc.stdout)
        self.assertIn("python", proc.stdout.lower())
        self.assertIn('"-u"', proc.stdout)
        self.assertIn('"--stdio"', proc.stdout)


if __name__ == "__main__":
    unittest.main()
