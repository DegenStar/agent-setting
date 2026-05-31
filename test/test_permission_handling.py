"""测试权限检查和修复功能"""

import stat
import tempfile
import unittest
from pathlib import Path

from agent_setting.backup import (
    _ensure_file_permission,
    _ensure_directory_permission,
    copy_to_backup,
)


class TestFilePermissionHandling(unittest.TestCase):
    """测试文件权限处理"""

    def test_ensure_read_permission_on_readable_file(self):
        """测试：可读文件权限检查通过"""
        with tempfile.NamedTemporaryFile(mode='w', delete=False) as f:
            f.write("test content")
            temp_path = Path(f.name)

        try:
            # 确保文件可读
            temp_path.chmod(stat.S_IRUSR | stat.S_IWUSR)

            success, err = _ensure_file_permission(temp_path, required_read=True)
            self.assertTrue(success)
            self.assertEqual(err, "")
        finally:
            temp_path.unlink()

    def test_ensure_write_permission_on_writable_file(self):
        """测试：可写文件权限检查通过"""
        with tempfile.NamedTemporaryFile(mode='w', delete=False) as f:
            f.write("test content")
            temp_path = Path(f.name)

        try:
            # 确保文件可写
            temp_path.chmod(stat.S_IRUSR | stat.S_IWUSR)

            success, err = _ensure_file_permission(temp_path, required_write=True)
            self.assertTrue(success)
            self.assertEqual(err, "")
        finally:
            temp_path.unlink()

    def test_fix_missing_read_permission(self):
        """测试：自动修复缺失的读权限"""
        with tempfile.NamedTemporaryFile(mode='w', delete=False) as f:
            f.write("test content")
            temp_path = Path(f.name)

        try:
            # 移除读权限
            temp_path.chmod(stat.S_IWUSR)

            # 尝试修复
            success, err = _ensure_file_permission(temp_path, required_read=True)

            # 验证修复成功
            self.assertTrue(success, f"Failed to fix read permission: {err}")
            mode = temp_path.stat().st_mode
            self.assertTrue(bool(mode & stat.S_IRUSR), "File should have read permission after fix")
        finally:
            # 恢复权限以便删除
            temp_path.chmod(stat.S_IRUSR | stat.S_IWUSR)
            temp_path.unlink()

    def test_fix_missing_write_permission(self):
        """测试：自动修复缺失的写权限"""
        with tempfile.NamedTemporaryFile(mode='w', delete=False) as f:
            f.write("test content")
            temp_path = Path(f.name)

        try:
            # 移除写权限
            temp_path.chmod(stat.S_IRUSR)

            # 尝试修复
            success, err = _ensure_file_permission(temp_path, required_write=True)

            # 验证修复成功
            self.assertTrue(success, f"Failed to fix write permission: {err}")
            mode = temp_path.stat().st_mode
            self.assertTrue(bool(mode & stat.S_IWUSR), "File should have write permission after fix")
        finally:
            # 恢复权限以便删除
            temp_path.chmod(stat.S_IRUSR | stat.S_IWUSR)
            temp_path.unlink()

    def test_fail_on_nonexistent_file(self):
        """测试：不存在的文件返回错误"""
        temp_path = Path("/nonexistent/file.txt")

        success, err = _ensure_file_permission(temp_path, required_read=True)
        self.assertFalse(success)
        self.assertIn("not found", err.lower())


class TestDirectoryPermissionHandling(unittest.TestCase):
    """测试目录权限处理"""

    def test_ensure_writable_directory(self):
        """测试：可写目录权限检查通过"""
        with tempfile.TemporaryDirectory() as temp_dir:
            dir_path = Path(temp_dir)

            success, err = _ensure_directory_permission(dir_path)
            self.assertTrue(success)
            self.assertEqual(err, "")

    def test_fix_directory_write_permission(self):
        """测试：修复目录写权限"""
        with tempfile.TemporaryDirectory() as temp_dir:
            dir_path = Path(temp_dir)

            # 移除写权限
            dir_path.chmod(stat.S_IRUSR | stat.S_IXUSR)

            # 尝试修复
            success, err = _ensure_directory_permission(dir_path)

            # 验证修复成功
            self.assertTrue(success, f"Failed to fix directory permission: {err}")
            mode = dir_path.stat().st_mode
            self.assertTrue(bool(mode & stat.S_IWUSR), "Directory should have write permission after fix")
            # 恢复权限以便清理
            dir_path.chmod(stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR)

    def test_fail_on_nonexistent_directory(self):
        """测试：不存在的目录返回错误"""
        dir_path = Path("/nonexistent/directory")

        success, err = _ensure_directory_permission(dir_path)
        self.assertFalse(success)
        self.assertIn("not found", err.lower())


class TestCopyToBackupWithPermissions(unittest.TestCase):
    """测试带权限检查的备份复制"""

    def test_copy_file_to_writable_destination(self):
        """测试：复制文件到可写目标"""
        with tempfile.TemporaryDirectory() as temp_dir:
            # 创建源文件
            src_dir = Path(temp_dir) / "source"
            src_dir.mkdir()
            src_file = src_dir / "test.txt"
            src_file.write_text("test content")

            # 创建目标目录
            dest_dir = Path(temp_dir) / "backup"
            dest_dir.mkdir()

            # 执行复制
            copy_to_backup(src_file, dest_dir, "test.txt")

            # 验证复制成功
            target = dest_dir / "test.txt"
            self.assertTrue(target.exists())
            self.assertEqual(target.read_text(), "test content")

    def test_copy_creates_parent_directories(self):
        """测试：复制时创建父目录"""
        with tempfile.TemporaryDirectory() as temp_dir:
            # 创建源文件
            src_file = Path(temp_dir) / "source.txt"
            src_file.write_text("test content")

            # 目标路径的父目录不存在
            dest_dir = Path(temp_dir) / "backup"
            rel_path = "subdir/nested/test.txt"

            # 执行复制
            copy_to_backup(src_file, dest_dir, rel_path)

            # 验证复制成功且目录已创建
            target = dest_dir / rel_path
            self.assertTrue(target.exists())
            self.assertEqual(target.read_text(), "test content")

    def test_copy_handles_permission_errors_gracefully(self):
        """测试：权限错误被优雅处理（不抛出异常）"""
        with tempfile.TemporaryDirectory() as temp_dir:
            # 创建源文件
            src_file = Path(temp_dir) / "source.txt"
            src_file.write_text("test content")

            # 创建目标目录并移除写权限
            dest_dir = Path(temp_dir) / "backup"
            dest_dir.mkdir()
            dest_dir.chmod(stat.S_IRUSR | stat.S_IXUSR)

            try:
                # 执行复制（应该记录警告但不崩溃）
                copy_to_backup(src_file, dest_dir, "test.txt")
                # 如果执行到这里说明没有抛出异常
            finally:
                # 恢复权限以便清理
                dest_dir.chmod(stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR)


if __name__ == "__main__":
    unittest.main()
