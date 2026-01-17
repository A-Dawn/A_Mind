# -*- coding: utf-8 -*-
"""
批量更新logger导入脚本
自动将所有模块的logger导入从 get_logger("A_Mind") 改为 get_logger(__name__)
"""

import os
import re
from pathlib import Path

# 需要更新的目录
DIRECTORIES = ["handlers", "commands", "core"]

# 需要跳过的文件（已在core/amind_logger.py中使用新的导入）
SKIP_FILES = {"amind_logger.py"}

# 替换模式
PATTERNS = [
    # 替换导入语句
    (r"from src\.common\.logger import get_logger", "from core.amind_logger import get_logger"),
    # 替换logger初始化
    (r'logger = get_logger\(["\']A[_-]?Mind["\']\)', "logger = get_logger(__name__)"),
    (r'logger = get_logger\(["\']A_mind["\']\)', "logger = get_logger(__name__)"),
]


def update_file(file_path: Path) -> bool:
    """更新单个文件的logger导入

    Args:
        file_path: 文件路径

    Returns:
        是否进行了修改
    """
    try:
        # 读取文件内容
        content = file_path.read_text(encoding="utf-8")
        original_content = content

        # 应用所有替换模式
        for pattern, replacement in PATTERNS:
            content = re.sub(pattern, replacement, content)

        # 如果内容发生变化，写回文件
        if content != original_content:
            file_path.write_text(content, encoding="utf-8")
            print(f"✓ 已更新: {file_path}")
            return True
        else:
            # 检查是否已经是新格式
            if "from core.amind_logger import get_logger" in content:
                print(f"- 已是新格式: {file_path}")
            else:
                print(f"○ 无需更新: {file_path}")
            return False

    except Exception as e:
        print(f"✗ 更新失败: {file_path} - {e}")
        return False


def main():
    """主函数"""
    print("=" * 60)
    print("A_Mind Logger 导入批量更新脚本")
    print("=" * 60)
    print()

    # 获取脚本所在目录
    script_dir = Path(__file__).parent
    total_updated = 0

    for directory in DIRECTORIES:
        dir_path = script_dir / directory
        if not dir_path.exists():
            print(f"⚠ 目录不存在: {dir_path}")
            continue

        print(f"\n处理目录: {directory}/")
        print("-" * 60)

        # 遍历目录中的所有.py文件
        for py_file in dir_path.glob("*.py"):
            # 跳过__init__.py和跳过列表中的文件
            if py_file.name == "__init__.py":
                continue
            if py_file.name in SKIP_FILES:
                print(f"⊘ 跳过: {py_file.name} (已跳过)")
                continue

            if update_file(py_file):
                total_updated += 1

    print()
    print("=" * 60)
    print(f"✓ 更新完成！共更新了 {total_updated} 个文件")
    print("=" * 60)


if __name__ == "__main__":
    main()
