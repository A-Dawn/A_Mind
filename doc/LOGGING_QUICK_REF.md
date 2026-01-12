# A_Mind 日志控制快速参考

## 🎯 4种预设模式

### minimal (最小日志)

**适合**: 普通用户日常使用

```toml
[logging]
preset = "minimal"
```

**输出**: 只显示ERROR和部分WARNING

---

### normal (正常模式) - 默认

**适合**: 平时使用，平衡信息量

```toml
[logging]
preset = "normal"
```

**输出**:
- services: WARNING
- handlers: INFO
- commands: ERROR
- core: WARNING
- database: ERROR

---

### verbose (详细模式)

**适合**: 监控插件运行状态

```toml
[logging]
preset = "verbose"
```

**输出**: 所有模块INFO级别，包含详细过程信息

---

### debug (调试模式)

**适合**: 开发者调试问题

```toml
[logging]
preset = "debug"
```

**输出**: 所有模块DEBUG级别，包含所有诊断信息

---

## 🔧 精细控制示例

### 只调整服务层

```toml
[logging]
preset = "normal"

[logging.modules]
services = "ERROR"       # 服务层只显示错误
# 其他模块继承normal预设
```

### 只显示错误和警告

```toml
[logging]
preset = "normal"
level = "WARNING"         # 全局改为WARNING
```

### 完全自定义

```toml
[logging]
preset = "verbose"        # 提供基础配置
level = "INFO"           # 但全局改为INFO
enabled = true

[logging.modules]
services = "ERROR"       # 进一步覆盖
handlers = "WARNING"     # 继承INFO
commands = "ERROR"       # 继承INFO
core = "WARNING"
database = "ERROR"

[logging.features]
show_search_results = true
show_initiation_workflow = false
```

---

## 📊 模块分类

| 模块 | 包含的文件 | 说明 |
|-----|----------|------|
| **services** | information_retriever.py<br>brainstorm_generator.py<br>decision_selector.py<br>auto_sender.py<br>response_monitor.py | 业务逻辑服务 |
| **handlers** | auto_initiate_action.py<br>state_check_action.py<br>message_tracker.py<br>a_mind_start_handler.py | 事件处理器 |
| **commands** | create_topic_command.py<br>list_topics_command.py<br>delete_topic_command.py<br>... (共11个) | 命令处理 |
| **core** | config_manager.py<br>dependency_container.py<br>permissions.py<br>a_mind_plan_tick_task.py | 核心基础设施 |
| **database** | database_manager.py<br>topic_repository.py<br>reply_repository.py | 数据库操作 |

---

## 🎛️ 功能开关

```toml
[logging.features]
show_search_results = false         # 搜索结果详情（通常很吵）
show_llm_prompts = false            # LLM提示词（非常长）
show_topic_matching = false         # 话题匹配详情
show_initiation_workflow = false    # 自发起工作流步骤
show_performance_metrics = false     # 性能指标（耗时、计数）
```

**在verbose/debug模式下自动启用大部分开关**

---

## 💡 常见使用场景

### 场景1: 想看插件在做什么，但不想看到太多日志

```toml
[logging]
preset = "minimal"
```

### 场景2: 想监控自发起功能，但不想看到搜索详情

```toml
[logging]
preset = "verbose"

[logging.features]
show_search_results = false    # 关闭搜索详情
show_initiation_workflow = true # 显示自发起步骤
```

### 场景3: 服务层日志太多，想关闭

```toml
[logging]
preset = "normal"

[logging.modules]
services = "ERROR"  # 服务层只显示错误
```

### 场景4: 调试特定功能（如信息检索）

```toml
[logging]
preset = "normal"    # 其他模块使用正常模式

[logging.modules]
services = "DEBUG"   # 但服务层使用调试模式

[logging.features]
show_search_results = true
```

### 场景5: 完全禁用日志（不推荐）

```toml
[logging]
enabled = false
```

---

## ⚡ 快速切换

### 从正常模式切换到调试模式

```toml
# 原来
[logging]
preset = "normal"

# 改为
[logging]
preset = "debug"
```

### 只想看错误

```toml
[logging]
preset = "minimal"
level = "ERROR"

[logging.modules]
services = "ERROR"
handlers = "ERROR"
commands = "ERROR"
core = "ERROR"
database = "ERROR"
```

### 查看所有信息（不推荐生产环境）

```toml
[logging]
preset = "debug"

[logging.features]
show_search_results = true
show_llm_prompts = true
show_topic_matching = true
show_initiation_workflow = true
show_performance_metrics = true
```

---

## 📝 配置优先级速查

```
1. 模块配置 logging.modules.{category}     [最高优先级]
2. 全局级别 logging.level
3. 预设模式 logging.preset                [最低优先级]
```

**示例**:
```toml
[logging]
preset = "minimal"     # 基础：WARNING
level = "INFO"          # 覆盖：INFO

[logging.modules]
services = "ERROR"     # 最终：services使用ERROR
# 其他模块使用INFO
```

---

## 🔍 问题诊断

### 日志太多无法查看？

```toml
[logging]
preset = "minimal"
```

### 想看看搜索到什么内容了？

```toml
[logging]
preset = "verbose"

[logging.features]
show_search_results = true
```

### 调试某个功能不工作？

```toml
[logging]
preset = "debug"

[logging.modules]
# 只调试相关模块
services = "DEBUG"
handlers = "DEBUG"
commands = "ERROR"
core = "ERROR"
database = "ERROR"
```

---

## 📖 完整文档

- **配置参考**: `doc/CONFIG_REFERENCE.md`

---

**快速参考** v2.0.0 | 2025-01-12
