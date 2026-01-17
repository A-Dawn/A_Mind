# A_Mind 插件配置参考手册

## 📖 文档说明

本文档提供A_Mind插件所有配置项的完整参考。

**版本**: 2.0.0
**最后更新**: 2025-01-12

---

## 目录

1. [快速开始](#1-快速开始)
2. [插件基础配置](#2-插件基础配置)
3. [日志配置](#3-日志配置)
4. [权限配置](#4-权限配置)
5. [LLM配置](#5-llm配置)
6. [服务配置](#6-服务配置)
7. [提示词配置](#7-提示词配置)
8. [话题管理配置](#8-话题管理配置)
9. [匹配配置](#9-匹配配置)
10. [状态检查配置](#10-状态检查配置)
11. [自动发起配置](#11-自动发起配置)
12. [Plan配置](#12-plan配置)
13. [配置迁移](#13-配置迁移)

---

## 1. 快速开始

### 1.1 最小配置

```toml
[plugin]
enabled = true

[logging]
preset = "normal"
```

### 1.2 配置文件位置

```
plugins/ARC_A_Mind/config.toml
```

### 1.3 配置自动生成

**重要**: 不要手动创建 `config.toml`！系统会根据 `config_schema` 自动生成。

---

## 2. 插件基础配置

### 2.1 plugin

插件基础设置。

| 配置项 | 类型 | 默认值 | 说明 |
|-------|------|-------|------|
| `enabled` | bool | `false` | 是否启用插件 |
| `config_version` | string | `"2.0.0"` | 配置文件版本（不要手动修改） |

**示例**:
```toml
[plugin]
enabled = true
```

---

## 3. 日志配置 (v2.0新增)

### 3.1 总体控制

| 配置项 | 类型 | 默认值 | 说明 |
|-------|------|-------|------|
| `enabled` | bool | `true` | 是否启用日志输出 |
| `preset` | string | `"normal"` | 预设模式：`minimal`/`normal`/`verbose`/`debug` |
| `level` | string | `"INHERIT"` | 全局日志级别 |

**预设模式对比**:

| 模式 | services | handlers | commands | core | database | 说明 |
|-----|---------|---------|---------|------|---------|------|
| `minimal` | ERROR | WARNING | ERROR | ERROR | ERROR | 最小输出 |
| `normal` | WARNING | INFO | ERROR | WARNING | ERROR | 正常使用 |
| `verbose` | INFO | INFO | INFO | INFO | WARNING | 详细监控 |
| `debug` | DEBUG | DEBUG | DEBUG | DEBUG | DEBUG | 开发调试 |

### 3.2 模块级别控制

```toml
[logging.modules]
services = "INHERIT"    # 服务层 (information_retriever, brainstorm_generator等)
handlers = "INHERIT"   # 处理器层 (auto_initiate_action, state_check_action等)
commands = "INHERIT"    # 命令层 (create_topic_command等)
core = "INHERIT"        # 核心模块 (config_manager, dependency_container等)
database = "INHERIT"    # 数据库 (database_manager, topic_repository等)
```

**可选值**: `INHERIT`, `CRITICAL`, `ERROR`, `WARNING`, `INFO`, `DEBUG`, `OFF`

### 3.3 功能开关

```toml
[logging.features]
show_search_results = false           # 显示搜索结果详情
show_llm_prompts = false              # 显示LLM提示词
show_topic_matching = false           # 显示话题匹配详情
show_initiation_workflow = false      # 显示自发起工作流详细步骤
show_performance_metrics = false       # 显示性能指标（耗时、计数等）
```

### 3.4 输出格式控制

```toml
[logging.format]
show_timestamp = false      # 显示时间戳
show_module_name = false     # 显示模块名称
use_colors = true            # 使用彩色输出
compact_mode = true          # 紧凑模式
```

### 3.5 文件输出（可选）

```toml
[logging.file_output]
enabled = false                      # 是否启用文件输出
path = "logs/amind.log"              # 日志文件路径
max_size_mb = 10                      # 单个文件最大大小（MB）
backup_count = 5                      # 保留备份数量
```

### 3.6 配置示例

#### 简洁模式（推荐）

```toml
[logging]
preset = "minimal"
```

#### 自定义模式

```toml
[logging]
preset = "normal"
level = "WARNING"

[logging.modules]
services = "ERROR"       # 覆盖预设，服务层只显示错误
handlers = "INFO"        # 继承全局WARNING
commands = "INHERIT"     # 继承全局WARNING
```

---

## 4. 权限配置

### 4.1 基础权限设置

```toml
[permissions]
super_admins = ["123456789", "987654321"]        # 超级管理员用户ID
admin_groups = ["群组1", "群组2"]               # 管理员群组ID
enable_inheritance = true                     # 启用权限继承
inheritance_controlled_by_user = true        # 继承由用户控制
global_admin_mode = false                    # 全局管理员模式
```

### 4.2 权限说明

| 权限类型 | 说明 |
|---------|------|
| `super_admins` | 拥有所有权限的用户 |
| `admin_groups` | 管理员群组内的所有用户 |
| `global_admin_mode` | 开启后所有用户均为管理员 |

---

## 5. LLM配置

### 5.1 全局LLM配置

```toml
[llm]
use_builtin = true                              # 使用内置LLM
model_name = "utils"                           # 模型选择：utils/replyer/planner
fallback_openai = false                        # OpenAI备选
openai_api_key = ""                             # OpenAI API密钥
fallback_model_name = "replyer"                 # 备选模型
temperature = 0.7                              # 生成温度
max_tokens = 1500                              # 最大token数
```

### 5.2 服务特定LLM配置

```toml
[services.brainstorm]
model_name = "utils"                           # 头脑风暴专用模型
fallback_model_name = "replyer"               # 备选模型
temperature = 0.8                             # 创意生成需要更高温度
max_tokens = 2000

[services.decision]
model_name = "planner"                         # 决策选择需要规划模型
fallback_model_name = "utils"                 # 备选模型
temperature = 0.3                             # 决策需要更低温度
max_tokens = 1000
```

---

## 6. 服务配置

### 6.1 互联网搜索配置

```toml
[internet_search]
engine = "duckduckgo"                          # 搜索引擎：duckduckgo/tavily/searxng
timeout = 15                                    # 请求超时（秒）
max_results = 5                                 # 最大结果数
```

#### Tavily搜索（需要API密钥）

```toml
[internet_search.tavily]
api_key = ""                                    # Tavily API密钥
max_results = 10
search_depth = "basic"                         # basic/advanced
```

#### SearXNG搜索（自建）

```toml
[internet_search.searxng]
base_url = ""                                   # SearXNG实例URL
max_results = 5
```

### 6.2 知识库配置

```toml
[knowledge_base]
enabled = true                                 # 是否启用知识库
top_k = 5                                        # 返回最相关的K条结果
similarity_threshold = 0.6                      # 相似度阈值
```

---

## 7. 提示词配置

```toml
[prompts]
matching_system_prompt = "你是一个话题匹配专家..."
initiate_brainstorm_prompt = "请基于以下信息进行头脑风暴..."
initiate_decision_prompt = "请从以下话题选项中选择最适合发起讨论的一个..."
evaluation_prompt = "请评估以下话题的进展情况和用户参与度..."
visibility_analysis_prompt = "分析以下话题的参与情况，判断应该保持公开还是转为私有..."
```

---

## 8. 话题管理配置

```toml
[topic_management]
max_active_topics = 5                         # 最大同时活跃话题数
max_topic_duration_days = 7                    # 话题最大持续时间（天）
auto_archive_days = 30                         # 自动归档时间（天）
default_visibility = "public"                  # 默认可见性：public/private
force_visibility = ""                          # 强制可见性（空表示不强制）
enable_auto_visibility_change = true          # 启用自动可见性转换
auto_initiate_interval_hours = 24              # 自发起检查间隔（小时）
auto_initiate_max_attempts = 3                 # 单个话题最大自发起次数
```

---

## 9. 匹配配置

```toml
[matching]
similarity_threshold = 0.6                     # LLM匹配相似度阈值
keyword_boost = 1.2                            # 关键词匹配权重
context_window = 15                             # 上下文消息窗口大小
time_decay_factor = 0.95                        # 时间衰减因子
```

---

## 10. 状态检查配置

```toml
[state_check]
check_interval_minutes = 20                    # 状态检查间隔（分钟）
min_replies_for_check = 5                       # 触发检查的最小回复数
engagement_threshold = 0.3                     # 用户参与度阈值
enable_termination_detection = true            # 启用用户终止意图检测
```

---

## 11. 自动发起配置

```toml
[auto_initiate]
enable_personality_injection = true           # 是否在自发起话题中注入系统人设
initiate_strategy = "balanced"                 # 自发起策略：creation_only/activation_only/balanced/random
creation_probability = 0.5                     # 创建型自发起概率
activation_probability = 0.5                    # 激活型自发起概率
creation_topics_count = 3                      # 创建型自发起生成话题数
creation_use_adaptive_search = true           # 创建型自发起是否使用自适应搜索
creation_adaptive_keywords = ["AI", "技术", "讨论"]  # 自适应搜索关键词列表
```

---

## 12. Plan配置

Plan是插件的独立任务实例，可以配置多个Plan同时运行。

### 12.1 Plan基础配置

```toml
[plan1]
enabled = true                                   # 是否启用此Plan
stream_config = "qq:1145141919810:group"        # 目标聊天流（格式：平台:ID:类型）
tick_interval_seconds = 120                     # 周期任务执行间隔（秒）
trigger_probability = 0.2                        # 触发概率（0.0-1.0）
description = "群组1的自动话题管理"              # Plan描述
```

### 12.2 Plan专属配置

Plan可以覆盖全局配置：

```toml
[plan1]
enabled = true
stream_config = "qq:1145141919810:group"
tick_interval_seconds = 120

# Plan专属LLM配置
[plan1.services.brainstorm]
temperature = 0.9                                 # 覆盖全局的0.8

# Plan专属日志配置
[plan1.logging]
preset = "verbose"                              # 覆盖全局的normal
```

### 12.3 多Plan示例

```toml
# Plan 1: 群组1 - 详细模式
[plan1]
enabled = true
stream_config = "qq:1145141919810:group"
tick_interval_seconds = 120
trigger_probability = 0.3

[plan1.logging]
preset = "verbose"

# Plan 2: 群组2 - 简洁模式
[plan2]
enabled = true
stream_config = "qq:1145141919811:group"
tick_interval_seconds = 300
trigger_probability = 0.1

[plan2.logging]
preset = "minimal"

# Plan 3: 私聊 - 正常模式
[plan3]
enabled = true
stream_config = "qq:1145141919812:private"
tick_interval_seconds = 600
trigger_probability = 0.05
```

---

## 13. 配置迁移

### 13.1 版本升级

当 `config_version` 变化时，系统会自动迁移配置。

**v1.0.0 → v2.0.0 迁移内容**：

1. 添加 `logging` 配置节（使用normal预设）
2. 更新 `config_version` 到 `2.0.0`
3. 保持原有配置不变

**迁移示例**：

**升级前 (v1.0.0)**:
```toml
[plugin]
enabled = true
config_version = "1.0.0"
```

**升级后 (v2.0.0)**:
```toml
[plugin]
enabled = true
config_version = "2.0.0"

# 新增的logging配置节（自动添加）
[logging]
enabled = true
preset = "normal"
level = "INHERIT"

# ... 其他logging配置
```

### 13.2 向后兼容性

旧配置文件无需修改即可使用，系统会：
- 保留所有原有配置值
- 自动添加新的配置节（使用默认值）
- 更新版本号

---

## 附录A: 配置模板

### A.1 最小配置模板

```toml
[plugin]
enabled = true

[logging]
preset = "minimal"
```

### A.2 推荐配置模板

```toml
[plugin]
enabled = true

[logging]
preset = "normal"

[permissions]
super_admins = ["你的QQ号"]

[llm]
model_name = "utils"

[topic_management]
max_active_topics = 5
default_visibility = "public"
```

### A.3 调试配置模板

```toml
[plugin]
enabled = true

[logging]
preset = "debug"

[logging.features]
show_search_results = true
show_llm_prompts = true
show_initiation_workflow = true
```

---

## 附录B: 环境变量

插件支持以下环境变量：

| 环境变量 | 说明 | 默认值 |
|---------|------|-------|
| `AMIND_LOG_LEVEL` | 覆盖日志级别 | - |
| `AMIND_DB_PATH` | 自定义数据库路径 | - |

---

**文档维护**: ARC
**最后更新**: 2025-01-12
**文档版本**: 2.0.0
