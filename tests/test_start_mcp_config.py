import shutil
import subprocess
import sys
import unittest
from pathlib import Path


@unittest.skipUnless(sys.platform == "win32", "MCP 安装脚本测试仅针对 Windows")
class StartMcpConfigTests(unittest.TestCase):
    def test_start_script_prints_stdio_safe_cursor_config(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        script = repo_root / "install" / "start-mcp.ps1"
        self.assertTrue(script.exists(), f"missing script: {script}")

        pwsh = shutil.which("pwsh") or shutil.which("powershell")
        self.assertIsNotNone(pwsh, "Windows 环境应安装 PowerShell（pwsh 或 powershell）以运行安装脚本测试")

        proc = subprocess.run(
            [pwsh, "-ExecutionPolicy", "Bypass", "-File", str(script), "-PythonExe", sys.executable],
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
