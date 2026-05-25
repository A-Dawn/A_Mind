# -*- coding: utf-8 -*-
"""
关键词权重管理命令
用于查看和修改各Plan的关键词分类权重
"""

from typing import Tuple, Optional
from maibot_sdk.compat import BaseCommand

# Logger import with fallback
try:
    from ..core.amind_logger import get_logger
except ImportError:
    from core.amind_logger import get_logger

logger = get_logger(__name__)


class KeywordWeightsCommand(BaseCommand):
    """关键词权重管理命令"""

    command_name = "keyword_weights"
    command_description = "查看或修改Plan的关键词分类权重"

    # 匹配模式
    command_pattern = r"^/(kw|keyword_weights)\s+(?P<action>show|set|enable|disable|reset)(?:\s+(?P<plan>plan\d+))?(?:\s+(?P<args>.+))?$"

    async def execute(self) -> Tuple[bool, Optional[str], bool]:
        """执行命令"""
        try:
            # 获取命令参数
            action = self.matched_groups.get("action", "")
            plan = self.matched_groups.get("plan", "plan1")
            args = self.matched_groups.get("args", "")

            # 处理不同动作
            if action == "show":
                return await self._show_weights(plan)
            elif action == "set":
                return await self._set_weights(plan, args)
            elif action == "enable":
                return await self._toggle_manual_weights(plan, True)
            elif action == "disable":
                return await self._toggle_manual_weights(plan, False)
            elif action == "reset":
                return await self._reset_weights(plan)
            else:
                return False, f"未知动作: {action}", False

        except Exception as e:
            logger.error(f"关键词权重命令执行失败: {e}")
            return False, f"命令执行失败: {e}", False

    async def _show_weights(self, plan: str) -> Tuple[bool, Optional[str], bool]:
        """显示当前权重配置"""
        try:
            enable_manual = self.get_config(f"{plan}.keyword_weights.enable_manual_weights", False)
            tech_weight = self.get_config(f"{plan}.keyword_weights.tech_weight", 0.25)
            science_weight = self.get_config(f"{plan}.keyword_weights.science_weight", 0.25)
            social_weight = self.get_config(f"{plan}.keyword_weights.social_weight", 0.25)
            entertainment_weight = self.get_config(f"{plan}.keyword_weights.entertainment_weight", 0.25)

            status = "✅ 手动权重" if enable_manual else "🤖 自动偏好"

            message = f"""📊 {plan.upper()} 关键词权重配置

状态：{status}

权重分配：
├─ 🔧 技术类 (tech):        {tech_weight:.2f}
├─ 🔬 科学类 (science):     {science_weight:.2f}
├─ 🌐 社会类 (social):       {social_weight:.2f}
└─ 🎮 娱乐类 (entertainment): {entertainment_weight:.2f}

总计: {tech_weight + science_weight + social_weight + entertainment_weight:.2f}

💡 提示：
- 使用 /kw set {plan} tech=0.5 science=0.3 来设置权重
- 使用 /kw enable {plan} 启用手动权重
- 使用 /kw disable {plan} 启用自动偏好"""

            await self.send_text(message)
            return True, f"显示 {plan} 权重配置", False

        except Exception as e:
            return False, f"显示权重失败: {e}", False

    def _get_config_path(self):
        """获取配置文件路径"""
        # 尝试从多个可能的路径获取
        try:
            if hasattr(self, 'plugin_dir'):
                return self.plugin_dir / "config.toml"
            elif hasattr(self, '_plugin') and hasattr(self._plugin, 'plugin_dir'):
                return self._plugin.plugin_dir / "config.toml"
            else:
                # 使用默认路径
                from pathlib import Path
                return Path(__file__).parent.parent / "config.toml"
        except Exception:
            from pathlib import Path
            return Path(__file__).parent.parent / "config.toml"

    async def _set_weights(self, plan: str, args: str) -> Tuple[bool, Optional[str], bool]:
        """设置权重"""
        try:
            if not args:
                return False, "请提供权重参数，例如: tech=0.5 science=0.3", False

            # 解析参数
            weight_changes = {}
            for arg in args.split():
                if "=" in arg:
                    key, value = arg.split("=", 1)
                    key = key.strip().lower()
                    try:
                        value = float(value.strip())
                        if 0.0 <= value <= 1.0:
                            weight_changes[key] = value
                        else:
                            return False, f"权重值必须在 0.0-1.0 之间: {key}={value}", False
                    except ValueError:
                        return False, f"无效的权重值: {value}", False

            if not weight_changes:
                return False, "未提供有效的权重参数", False

            # 读取配置文件并更新
            import toml

            config_path = self._get_config_path()
            if not config_path.exists():
                return False, "配置文件不存在", False

            config = toml.load(config_path)

            # 确保配置结构存在
            if plan not in config:
                config[plan] = {}
            if "keyword_weights" not in config[plan]:
                config[plan]["keyword_weights"] = {}

            # 更新权重
            for key, value in weight_changes.items():
                if key in ["tech", "science", "social", "entertainment"]:
                    weight_key = f"{key}_weight"
                    config[plan]["keyword_weights"][weight_key] = value
                else:
                    return False, f"未知的权重类别: {key}", False

            # 保存配置
            with open(config_path, "w", encoding="utf-8") as f:
                toml.dump(config, f)

            # 格式化输出
            changes_str = ", ".join([f"{k}={v:.2f}" for k, v in weight_changes.items()])

            message = f"""✅ {plan.upper()} 权重已更新

修改：{changes_str}

💡 提示：
- 使用 /kw enable {plan} 启用手动权重
- 使用 /kw show {plan} 查看完整配置"""

            await self.send_text(message)
            return True, f"更新 {plan} 权重: {changes_str}", False

        except Exception as e:
            logger.error(f"设置权重失败: {e}")
            return False, f"设置权重失败: {e}", False

    async def _toggle_manual_weights(self, plan: str, enable: bool) -> Tuple[bool, Optional[str], bool]:
        """启用手动权重或启用自动偏好"""
        try:
            import toml

            config_path = self._get_config_path()
            if not config_path.exists():
                return False, "配置文件不存在", False

            config = toml.load(config_path)

            # 确保配置结构存在
            if plan not in config:
                config[plan] = {}
            if "keyword_weights" not in config[plan]:
                config[plan]["keyword_weights"] = {}

            # 更新设置
            config[plan]["keyword_weights"]["enable_manual_weights"] = enable

            # 保存配置
            with open(config_path, "w", encoding="utf-8") as f:
                toml.dump(config, f)

            mode = "✅ 手动权重" if enable else "🤖 自动偏好"
            message = f"""✅ {plan.upper()} 已切换到 {mode}

💡 提示：使用 /kw show {plan} 查看当前权重配置"""

            await self.send_text(message)
            return True, f"{plan} 切换到 {'手动权重' if enable else '自动偏好'}", False

        except Exception as e:
            logger.error(f"切换权重模式失败: {e}")
            return False, f"切换失败: {e}", False

    async def _reset_weights(self, plan: str) -> Tuple[bool, Optional[str], bool]:
        """重置权重为默认值"""
        try:
            import toml

            config_path = self._get_config_path()
            if not config_path.exists():
                return False, "配置文件不存在", False

            config = toml.load(config_path)

            # 确保配置结构存在
            if plan not in config:
                config[plan] = {}
            if "keyword_weights" not in config[plan]:
                config[plan]["keyword_weights"] = {}

            # 重置为默认值
            config[plan]["keyword_weights"]["tech_weight"] = 0.25
            config[plan]["keyword_weights"]["science_weight"] = 0.25
            config[plan]["keyword_weights"]["social_weight"] = 0.25
            config[plan]["keyword_weights"]["entertainment_weight"] = 0.25

            # 保存配置
            with open(config_path, "w", encoding="utf-8") as f:
                toml.dump(config, f)

            message = f"""🔄 {plan.upper()} 权重已重置

所有权重已重置为默认值 0.25

💡 提示：使用 /kw show {plan} 查看当前配置"""

            await self.send_text(message)
            return True, f"{plan} 权重已重置", False

        except Exception as e:
            logger.error(f"重置权重失败: {e}")
            return False, f"重置失败: {e}", False
