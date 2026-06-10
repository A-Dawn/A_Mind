# A_Mind MaiBot SDK Migration

## 2026-06-10 - Phase 9 MaiBot 1.0.0 Lifecycle Task Refresh

- Bumped plugin version from `1.0.0` to `1.0.1`.
- Fixed the MaiBot 1.0.0 configuration-complete path where `ON_START` had already fired before A_Mind was fully configured, so enabled Plan tasks were not created until a full restart.
- Extracted A_Mind background task registration into a reusable refresh path shared by the legacy `ON_START` event handler and the SDK facade.
- `AMindSDKPlugin.on_load()` now schedules a delayed task refresh, and `on_config_update(scope="self")` refreshes tasks immediately after plugin config updates.
- Disabled Plan tasks are cancelled during refresh, and all A_Mind Tick tasks are stopped on plugin unload.
- Plan and global-pool Tick tasks now activate the plugin context during execution, so background LLM and direct `send.text` calls resolve the correct SDK capabilities.
- Verified `py_compile` for the plugin entrypoint, startup handler, and both Tick task modules; simulated SDK config updates confirm Plan task creation and cleanup.

## 2026-05-07 - Version Bump

- Bumped plugin version from `0.4.0` to `0.5.0` for the MaiBot SDK runtime migration release.
- Updated README badge and changelog to mark `0.5.0` as the current version.

## 2026-05-07 - Baseline

- Current branch: `dev`.
- Target host: current local `MaiBot/dev`.
- Findings:
  - MaiBot now validates only Manifest v2.
  - A_Mind still uses the legacy `src.plugin_system` entrypoint and Manifest v1.
  - MaiBot has a legacy import compatibility layer, but A_Mind is blocked at manifest validation before that layer can help.
  - Direct import probing shows the legacy business components can still be instantiated, but plugin-level config access is missing under the new runtime.

## Migration Strategy

1. Add a Manifest v2 file and a `create_plugin()` SDK entrypoint.
2. Wrap the existing business components with a new `MaiBotPlugin` facade so commands, event handlers, and legacy actions can still execute.
3. Keep existing service/model/repository code intact in the first pass.
4. Replace legacy LLM/config/send dependencies incrementally after the plugin can load under the SDK runtime.

## 2026-05-07 - Phase 1 SDK Facade

- Added `AMindSDKPlugin`, a `MaiBotPlugin` facade around the existing `AMindPlugin` business components.
- Added `create_plugin()` so MaiBot loads A_Mind through the new SDK contract instead of the legacy plugin scanner.
- Added a unified dispatch layer for legacy Command, EventHandler, and Action components.
- Added default config generation from the existing legacy `ConfigField` schema to preserve the current configuration surface.
- Upgraded `_manifest.json` to Manifest v2 and declared the runtime capabilities used by the compatibility facade.

Validation:

- Manifest v2 validation passes with no errors.
- `create_plugin()` returns `AMindSDKPlugin`.
- MaiBot `PluginLoader` discovers and loads `A-Dawn.A-Mind`.
- The SDK facade exposes 18 components.
- Host `ComponentRegistry` accepts all 18 component declarations.

## 2026-05-07 - Phase 2 Legacy LLM Bridge

- Patched the legacy LLM compatibility module aliases used by A_Mind so `get_available_models()` returns the expected task names instead of an empty dict.
- Routed legacy `llm_api.generate_with_model()` calls through `PluginContext.llm.generate()`.
- Covered both `maibot_sdk.compat.apis.llm_api` and `src.plugin_system.apis.llm_api` because the import hook can leave distinct module objects in `sys.modules`.

Validation:

- After `PluginLoader` load, both LLM module aliases report the patched model list: `planner`, `replyer`, `tool_use`, `utils`.
- `python -m py_compile plugin.py` passes.

## 2026-05-07 - Phase 3 Invocation Probes

- Fixed `ConfigManager` so it accepts either a plugin-like object with `get_config()` or a callable config getter. This restores `/amind_models`, which previously passed a lambda into `ConfigManager`.
- Verified SDK command dispatch with `/amind_help`; the command reaches the legacy component and sends through `PluginContext.send`.
- Verified `/amind_models`; the command now completes and uses the patched model list.
- Verified `amind_global_pool_collector` event dispatch with a serialized SDK-style message dict.
- Verified `a_mind_on_start` with disabled plans/global pool settings; startup handler returns successfully.
- Extended the LLM patch to update already-imported A_Mind submodules that used `from ... import get_available_models`, preventing stale function references.
- Added `component_type` beside `type` in component declarations so both Runner registration and direct Host registry validation can consume the same facade output.

Validation:

- MaiBot `.venv` reports SDK `2.4.0`; A_Mind manifest validation passes under that runtime.
- MaiBot `PluginLoader` loads `A-Dawn.A-Mind` as `AMindSDKPlugin`.
- Host `ComponentRegistry` registers all 18 facade declarations: 13 commands, 3 event handlers, and 2 legacy actions exposed as tools.
- Invocation probe passes for `/amind_help`, `/amind_models all`, `amind_global_pool_collector`, and `a_mind_on_start`.

## 2026-05-07 - Phase 4 Command and Event Regression

- Added SDK-to-legacy message fields `user_id` and `sender` so legacy permission checks can read the caller identity from SDK-style messages.
- Injected the legacy `container`, `plugin_dir`, and `_plugin` references into command instances before dispatch. This lets permissions, config-file helpers, and legacy dependency access behave like the old runtime.
- Added automatic regex `groupdict()` extraction for command dispatch. This restores commands such as `/kw show plan1` that depend on `matched_groups`.

Validation:

- Isolated database regression passed for: `/amind_help`, `/amind_models all`, `/amind_create`, `/amind_list`, `/amind_update`, `/amind_visibility`, `/amind_stream status/unbind/bind/pause/resume`, `/amind_pool status/whitelist/profile/dryrun`, `/kw show plan1`, `amind_global_pool_collector`, `a_mind_on_start`, `/amind_delete`.
- Deep-path regression passed for: `/amind_debug show_state`, `/amind_check`, `amind_message_tracker`, and direct `amind_state_check` action dispatch.
- `amind_message_tracker` called the patched LLM bridge and updated topic reply statistics in the isolated test database.
- Observed legacy permission behavior: users listed only in `debug.allowed_debug_users` satisfy `debug`; a user listed first as `super_admin` does not automatically upgrade to `debug`.

## 2026-05-07 - Phase 5 Native SDK Tool Declarations

- Converted legacy Action facade declarations to native SDK `TOOL` declarations.
- Preserved the existing legacy Action business implementation by routing tool invocations through the existing `_dispatch_action()` adapter.
- Added Tool parameter schema generation from legacy `action_parameters`, plus detailed descriptions built from action description, requirements, and associated message types.
- Added `tool.get_definitions` to manifest capabilities for native SDK tool introspection.

Validation:

- Host `ComponentRegistry` now reports the two former legacy actions as native `tool` entries instead of compatibility `action` entries.
- Direct tool/action dispatch for `amind_state_check` continues to pass against an isolated database.

## 2026-05-07 - Phase 6 Deep Tool and Config Write Regression

- Injected the legacy `container`, `plugin_dir`, and `_plugin` references into SDK Tool dispatch. This matches the command dispatch adapter and restores lazy service access for legacy Action implementations such as `A_mind_auto_initiate`.
- Declared the legacy `toml` package dependency in Manifest v2 as a Python package dependency. Several legacy config commands still import `toml` directly, and the current MaiBot test venv did not include it by default.
- Verified MaiBot's dependency pipeline recognizes `toml>=0.10.2,<1.0.0` as an install requirement for `A-Dawn.A-Mind` and does not block plugin loading.

Validation:

- Deep isolated regression passed with a temporary database and temporary `config.toml`.
- `A_mind_auto_initiate` as a native SDK Tool successfully completed the existing-topic workflow, scheduled a send, started response monitoring, and incremented `auto_initiate_count`.
- `A_mind_auto_initiate` successfully completed the creation workflow when no existing topic was eligible, created a new topic, bound it to the active stream, and scheduled a send.
- `/kw set plan1`, `/kw enable plan1`, `/kw show plan1`, and `/kw reset plan1` all passed against the temporary config file after the `toml` dependency was available.

## 2026-05-07 - Phase 7 Additional Runtime Surface Regression

- Tested the exposed SDK component set through MaiBot's Host `ComponentRegistry`: all 18 components register, with 13 commands, 3 event handlers, 2 native tools, and 0 legacy actions.
- Verified `get_tools_for_llm()` exposes `A-Dawn.A-Mind.amind_state_check` and `A-Dawn.A-Mind.A_mind_auto_initiate` as native SDK tools.
- Exercised `/amind_initiate`, including the command path that creates a legacy `AutoInitiateAction` internally instead of going through the SDK Tool adapter.
- Fixed `/amind_initiate <id> stream:<stream_config>` so the explicit `stream:` override wins over the command message's `chat_stream`. `AutoInitiateAction` reads `message.chat_stream` first, so the command now wraps the message with an overridden chat stream before executing the workflow.
- Confirmed invalid stream overrides are rejected without scheduling a send.
- Confirmed admin permission denial still works under SDK dispatch, and `on_config_update(scope="self")` propagates updated config into legacy permission checks.
- Confirmed the startup event handler still returns successfully with no enabled plans and global pool task creation enabled.
- Confirmed `TopicCaptureAction` is not part of the current exposed component set, so it remains outside the active SDK runtime surface for this migration pass.

Validation:

- Isolated regression passed for `/amind_create`, `/amind_initiate 1`, `/amind_initiate 1 stream:qq:12345:group`, invalid stream override, admin permission denial, config hot update, `a_mind_on_start`, SDK Host registry registration, and tool definition aggregation.

## 2026-05-07 - Phase 8 MaiBot Runner Integration Regression

- Started MaiBot's real `PluginRunnerSupervisor` with `A-Dawn.A-Mind` loaded through the Runner subprocess instead of the isolated in-process loader.
- Registered MaiBot host capabilities for the test supervisor and overrode LLM capabilities with deterministic test responses to avoid requiring real model credentials.
- Added a temporary in-memory Platform IO capture driver and a `chat_manager` test session for `qq:runner-group:group`, so SDK `ctx.send.text` calls exercised MaiBot's real `send_service` and route resolution without connecting to an external adapter.
- Confirmed the persisted `config.toml` disables the plugin by default; temporarily enabling `[plugin].enabled` allowed Runner activation, then the file was restored to disabled after testing.
- Confirmed Runner activation registers the same runtime surface: 13 commands, 3 event handlers, 2 native tools, 0 legacy actions.
- Confirmed command invocations through `plugin.invoke_command` and real send pipeline for `/amind_help`, `/amind_models all`, and `/kw show plan1`.
- Confirmed native tool invocation through `plugin.invoke_tool` for `amind_state_check`.
- Confirmed constructed `on_message` chat flow dispatches through Runner with the expected session id.
- Confirmed stateful database command flow through Runner and send pipeline: `/amind_create`, `/amind_list`, `/amind_delete`, and `/amind_list` after deletion.
- Confirmed config hot update delivery through `notify_plugin_config_updated()` by temporarily enabling admin mode for the stateful create/delete test without changing the persisted config.

Validation:

- Real Runner load status for A_Mind: `success`.
- Captured send outputs included help text, model config text, keyword weight text, topic created, topic list, topic deleted, and empty topic list.
- The temporary topic created during the Runner test was deleted in the same run.
- Non-A_Mind manifest errors for sibling plugin directories were observed because MaiBot Runner scans child directories of the configured plugin root; they did not affect A_Mind activation or component execution.
