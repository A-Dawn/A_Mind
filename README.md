# A_Mind - 智能话题管理插件

**ARC's MIND – 智能话题与主动思维插件（for MaiBot）**

![A_Mind Logo](https://img.shields.io/badge/A_Mind-智能话题管理-blue?style=for-the-badge)
![Version](https://img.shields.io/badge/版本-0.1.0-orange?style=flat-square)
![Python](https://img.shields.io/badge/Python-3.11+-green?style=flat-square)
![License](https://img.shields.io/badge/License-AGPL--3.0-blue?style=flat-square)

*💡 智能话题发起、自动追踪、长期学习调整*

---

## 🌟 项目简介

本项目是 ARC 基于 MaiBot 生态提出的一种“主动话题与长期兴趣管理”的实现方式。是为 [MaiBot](https://github.com/Mai-with-u/MaiBot) 量身定制的智能话题管理插件。它让你的麦麦不再被动等待用户发言，而是能够：

- 🎯 **主动发起话题** - 根据群聊氛围智能推荐讨论内容
- 📊 **实时话题追踪** - 监控话题热度和用户参与度
- 🔄 **长期学习调整** - 通过AI不断优化话题策略
- 🎪 **多样化内容** - 支持互联网搜索、知识库整合等多种话题来源

> 厌倦了千篇一律的等待？来吧！安装这个插件，你的麦麦将有它自己的小巧思！并且将它的想法，或者你在乎的话题发送给你！Maybe Just A MIND！

---

## ✨ 功能特性

### 🚀 核心能力
- **智能话题生成** - 基于用户兴趣和群聊历史自动生成话题
- **多源内容整合** - 支持互联网搜索、知识库、热门话题等多种来源
- **参与度分析** - 实时评估话题热度和用户互动情况
- **自动状态管理** - 话题的创建、激活、归档全自动处理

### 🎛️ 特色功能
- **长期自适应** - AI持续学习用户偏好，话题越来越"懂"群友
- **权限控制** - 支持超级管理员、管理员、普通用户分级权限
- **多平台支持** - 原生支持QQ群聊，可扩展到其他平台
- **可视化监控** - 通过命令实时查看话题状态和统计数据
- **多层模型配置** - 支持全局、服务级别、Plan级别的精细化模型配置

### 📈 智能算法
- **LLM驱动决策** - 使用大语言模型进行话题评估和选择
- **向量相似度匹配** - 基于嵌入向量进行话题相关性分析
- **时间衰减算法** - 考虑消息时效性，避免过时话题
- **参与度评分** - 多维度评估话题质量和用户参与意愿

---

## 🚀 快速开始

### 📦 安装依赖

#### 1.  安装插件专用依赖
```bash
# 首先激活虚拟环境（非一键包）
# 确保在MaiBot根目录
cd plugins/A_Mind
pip install requests beautifulsoup4
```
```terminal
# 在控制面板处选择交互式模块安装（一键包）
# 选择文件地址"xxxxxxx\MaiBot\plugins\A_Mind\requirements.txt"
# 或者直接输入模块名(逗号分隔)：
# requests,beautifulsoup4
```

### ⚙️ 基础配置

#### 1. 启用插件，关闭插件，调整配置
编辑 `plugins/A_Mind/config.toml`：
```toml
[plugin]
enabled = true  # 默认false，需要手动启用
```

#### 2. 配置LLM（必需）
```toml
[llm]
use_builtin = true  # 使用内置LLM
model_name = "utils"  # 或 "replyer", "planner", "tool_use" 等
fallback_model_name = "replyer"
temperature = 0.7
max_tokens = 1500
```

#### 3. 配置多层模型（可选）
A_Mind 支持为不同工作流配置不同的模型，提高性能和效果：

```toml
# 全局默认配置（已在第2步配置）

# 服务级别配置（插件已内置默认配置）
[services.brainstorm]
model_name = "utils"      # 头脑风暴专用模型（默认）
fallback_model_name = "replyer"
temperature = 0.8        # 创意生成用较高温度
max_tokens = 2000

[services.decision]
model_name = "planner"    # 决策选择专用模型（默认）
fallback_model_name = "utils"
temperature = 0.3        # 分析决策用较低温度
max_tokens = 1000

# Plan级别配置（可选，用于特定聊天流的定制）
[plan1.model_config]
model_name = ""  # 空值表示继承全局配置
fallback_model_name = ""
temperature = 0.7
max_tokens = 1500

[plan1.services.brainstorm]
model_name = ""  # 空值表示继承上级配置
temperature = 0.9  # 可覆盖服务级别配置
```

配置优先级：`Plan特定 > 服务特定 > 全局默认`

#### 3. 配置自动发起（推荐）
```toml
[plan1]
enabled = true
stream_config = "qq:群号:group"  # 替换为实际的群号
tick_interval_seconds = 300      # 检查间隔（秒）
trigger_probability = 0.4        # 每次检查的触发概率
cooldown_seconds = 1800          # 触发冷却时间（秒）
```

#### 4. 配置权限（可选）
```toml
[permissions]
super_admins = ["你的QQ号"]  # 超级管理员列表
admin_groups = [""]         # 管理员群组列表
enable_inheritance = true   # 启用权限继承机制
inheritance_controlled_by_user = true  # 继承由用户控制聊天流
global_admin_mode = false   # 全局管理员模式（所有用户均为管理员）
```

#### 5. 配置Tavily API密钥（重要）
```toml
[internet_search]
engine = "tavily"
tavily_api_key = "你的Tavily_API密钥"  # 从 https://tavily.com 获取
```

> **⚠️ 重要提醒**：Tavily API密钥是使用互联网搜索功能所必需的。没有密钥将无法使用话题生成中的网络搜索功能。可以从 [Tavily官网](https://tavily.com) 免费获取API密钥。

#### 6. 可按需更改的配置（可选）

##### 自定义搜索关键词
```toml
[auto_initiate]
# 基础搜索关键词列表（可根据兴趣调整）
search_keywords = ["社会热点新闻", "娱乐八卦资讯", "美食推荐攻略", "旅游景点介绍", "电影电视剧推荐", "音乐新歌榜单", "游戏行业动态", "时尚潮流趋势", "健康生活指南", "育儿教育经验", "职场发展建议", "投资理财知识", "家居装修灵感", "宠物养护知识", "运动健身方法", "心理健康话题", "文化艺术资讯", "生活小技巧"]

# 技术类关键词列表
tech_keywords = ["AI应用", "智能手机", "社交媒体", "移动支付", "在线教育", "远程办公", "直播技术", "短视频平台", "云计算服务", "大数据应用", "网络安全", "数字创新"]

# 科学类关键词列表
science_keywords = ["医学健康", "营养饮食", "环境保护", "气候变化", "新能源应用", "太空探索", "基因科技", "大脑科学", "生命科学", "材料创新"]

# 社会类关键词列表
social_keywords = ["社会热点", "教育话题", "医疗健康", "经济新闻", "文化传承", "城市生活", "乡村发展", "创业就业", "青年话题", "家庭教育", "养老保障", "住房政策", "交通出行", "社区生活", "公益活动", "志愿服务", "传统文化", "现代生活", "消费趋势", "社交关系"]

# 娱乐类关键词列表
entertainment_keywords = ["娱乐新闻", "电影推荐", "电视剧追剧", "音乐新歌", "综艺节目", "明星八卦", "体育赛事", "游戏攻略", "动漫新作", "短视频热点", "直播精彩", "电竞比赛", "时尚穿搭", "美妆护肤", "美食探店", "旅游攻略", "摄影技巧", "手工DIY", "创意设计", "艺术展览"]
```

##### 自定义兜底话题
```toml
[auto_initiate]
# 兜底话题列表，当LLM生成失败时使用
fallback_topics = ["大家玩原神吗？"]
```

> **💡 配置建议**：这些关键词和兜底话题可以根据你的群聊特点和用户兴趣进行调整。更多话题会让机器人更"懂"你的群友，但也会需要更多API调用。

### 🎯 启动测试

1. 重启MaiBot
2. 在配置的群聊中发送 `/amind help` 查看帮助
3. 等待机器人自动发起话题，或手动测试

---

## 📚 使用指南

### 💬 基础命令

| 命令 | 说明 | 示例 |
|------|------|------|
| `/amind_help` | 显示帮助信息 | - |
| `/amind_list` | 查看当前活跃话题 | - |
| `/amind_check` | 检查话题状态 | `/amind_check 话题ID` |
| `/amind_create` | 创建新话题 | `/amind_create 标题:描述` |
| `/amind_initiate` | 手动发起话题 | `/amind_initiate` |
| `/amind_models` | 查看模型配置 | `/amind_models all` |

### 🎪 自动功能

插件启用后会自动：
- **定时检查** - 每分钟评估话题状态
- **智能发起** - 根据配置概率自动发起新话题
- **状态管理** - 自动归档过期或冷门话题

### 📊 监控功能

使用 `/amind check` 可以查看：
- 📈 话题参与度统计
- ⏰ 最后活动时间
- 👥 参与用户数量
- 🔥 话题热度评分

---

## ⚠️ 注意事项

### 🔧 依赖要求
- **必须**：requests, beautifulsoup4 (用于互联网搜索)
- **Python版本**：3.11+

### 🎛️ 配置提醒
- LLM配置是核心功能，必须正确设置
- 自动发起间隔建议不低于60秒

### 🚨 已知限制
- 测试版阶段，部分高级功能可能不稳定
- 互联网搜索功能需要网络连接
- 大量话题可能影响性能

---

## 📝 版本信息

### 🎯 0.1.0 (当前版本)
- ✅ 基础话题管理功能
- ✅ 自动发起和状态检查
- ✅ 权限控制系统
- ✅ 多源内容整合
- 🚧 高级统计功能（开发中）
- 🚧 性能优化（开发中）

### 🔄 未来规划
- 更智能的话题推荐算法
- 自定义话题模板
- 跨平台话题同步
- 详细的使用统计

---

## 🐛 问题反馈

遇到问题或有建议？欢迎通过以下方式反馈：

- 📧 **Issues**：在GitHub上提交Issue
- 📋 **信息收集**：请提供以下信息至ARC
  - 错误信息或截图
  - 配置文件（敏感信息请脱敏）
  - 使用的MaiBot版本
  - 操作系统信息

> **注意**：当前版本不接受Pull Request，请通过Issue反馈问题和建议。

---

## 📄 许可证

本项目采用 AGPL-3.0 许可证 - 查看 [LICENSE](./LICENSE) 文件了解详情。

项目欢迎 fork。你可以按你认可的方式治理和维护，但若对外提供网络服务，请务必遵守 AGPL-3.0 的相关条款。

---

<div align="center">
**Made with ❤️ for MaiBot Community**

*让聊天更有趣，让麦麦更聪明*

[⬆️ 返回顶部](#-amind---智能话题管理插件)

</div>
