# A_Mind 插件更新日志

所有重要变更都将记录在此文件中。

---

## [0.2.0] - 2025-01-13

### ✨ 新增 (Added)

#### 关键词权重管理系统
- **功能描述**：支持手动配置不同类别关键词的权重，精确控制话题生成倾向
- **配置项**：`[planX.keyword_weights]` 配置节
  - `enable_manual_weights` - 启用手动权重（覆盖AI自动分析）
  - `tech_weight` - 技术类关键词权重（0.0-1.0）
  - `science_weight` - 科学类关键词权重（0.0-1.0）
  - `social_weight` - 社会类关键词权重（0.0-1.0）
  - `entertainment_weight` - 娱乐类关键词权重（0.0-1.0）
- **新增命令**：
  - `/kw show [plan]` - 查看当前权重配置
  - `/kw set [plan] <参数>` - 设置权重
  - `/kw enable [plan]` - 启用手动权重
  - `/kw disable [plan]` - 启用自动偏好
  - `/kw reset [plan]` - 重置为默认值

#### 关键词轮询机制
- **功能描述**：优化关键词选择逻辑，确保所有配置的关键词都能被均匀使用
- **实现方式**：
  - 添加类变量 `_keyword_indices` 跟踪每个Plan的关键词索引
  - 每次触发自动移动索引位置（每次移动3位）
  - 支持多Plan独立轮询
- **效果**：之前只使用前3个关键词的Bug已修复，现在所有关键词都会被使用

#### 日志系统优化
- **功能描述**：统一使用logger系统，所有日志可通过配置灵活控制
- **修改文件**：
  - `core/a_mind_plan_tick_task.py` - 20个print改为logger
  - `handlers/a_mind_start_handler.py` - 5个调试print改为logger
  - `database.py` - 3个数据库print改为logger
  - `core/amind_logger.py` - 移除配置调试print
- **日志级别分类**：
  - **DEBUG** - 详细调试信息（Tick执行、配置读取、概率检查等）
  - **INFO** - 重要事件（概率检查通过、自动发起成功等）
  - **WARNING** - 警告信息（并发检查、配置为空等）
  - **ERROR** - 错误信息（队列处理失败、数据库错误等）
- **新增配置**：
  - `[logging.preset]` - 预设模式（minimal/normal/verbose/debug）
  - `[logging.level]` - 全局级别覆盖
  - `[logging.modules]` - 模块级别独立控制

### 🔧 变更 (Changed)

#### 关键词选择逻辑
- **变更前**：每次只使用前3个关键词，后面的永远不会被使用
- **变更后**：通过轮询机制确保所有关键词均匀使用
- **影响**：话题类型更加多样化，避免话题单调

#### 日志输出方式
- **变更前**：大量使用print()直接输出，无法控制
- **变更后**：统一使用logger系统，支持灵活配置
- **影响**：可以通过配置控制日志详细程度，减少无关输出

### 🐛 修复 (Fixed)

#### 关键词池Bug
- **问题**：关键词配置18个，但只有前3个被使用
- **原因**：`search_queries[:3]` 固定取前3个
- **修复**：实现轮询机制，每次取不同位置的关键词
- **影响**：现在所有配置的关键词都能被使用

#### 日志混乱问题
- **问题**：日志输出混乱，无法控制详细程度
- **原因**：print()输出不受logger系统控制
- **修复**：将所有print改为logger调用
- **影响**：日志更加规范，可通过配置灵活控制

### 📝 文档 (Documentation)

#### 新增文档
- 更新 `README.md` - 添加新功能说明和使用指南
- 新增 `CHANGELOG.md` - 版本变更记录（本文件）
- 新增 `TODO.md` - 待办事项列表和未来规划

### 📊 代码统计

#### 新增文件
- `commands/keyword_weights_command.py` (~250行) - 权重管理命令
- `core/amind_logger.py` (~370行) - 日志管理器
- `test_amind_new_features.py` (~400行) - 自动化测试脚本

#### 修改文件
- `handlers/auto_initiate_action.py` - 添加轮询机制和权重管理
- `core/a_mind_plan_tick_task.py` - 20个print改为logger
- `handlers/a_mind_start_handler.py` - 5个print改为logger
- `database.py` - 3个print改为logger
- `core/amind_logger.py` - 移除调试print
- `plugin.py` - 添加权重配置schema
- `config.toml` - 添加logging.modules和keyword_weights配置
- `README.md` - 更新功能说明

#### 代码变更量
- 新增代码：~1350行
- 修改代码：~100行
- 删除代码：~50行（主要是print语句）
- 净增加：~1400行

---

## [0.1.0] - 2025-01-11

### ✨ 新增 (Added)
- 基础话题管理功能
- 自动发起和状态检查
- 权限控制系统
- 多源内容整合（互联网搜索、知识库）
- 多层模型配置系统（全局/服务/Plan三级）
- 基础命令集（创建、查看、检查、发起等）

### 🎯 核心功能
- LLM驱动的话题生成和决策
- 向量相似度匹配
- 参与度评分系统
- 时间衰减算法

---

## 版本说明

### 版本号格式
- **主版本号**：不兼容的API变更
- **次版本号**：向后兼容的功能新增
- **修订号**：向后兼容的问题修复

### 更新类型标识
- ✨ **新增** (Added) - 新功能
- 🔧 **变更** (Changed) - 功能变更
- 🗑️ **废弃** (Deprecated) - 即将移除的功能
- ❌ **移除** (Removed) - 已移除的功能
- 🐛 **修复** (Fixed) - 问题修复
- 📝 **文档** (Documentation) - 文档更新

---

## 未来计划

### [0.3.0] - 计划中
- 🚧 并发搜索优化
- 🚧 关键词组合搜索

### [0.4.0] - 规划中
- 🚧 话题推荐算法优化
- 🚧 用户偏好学习系统
- 🚧 话题热度预测

---

## 致谢

感谢所有使用和反馈 A_Mind 插件的用户！
