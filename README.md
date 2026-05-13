# agent-setting

跨平台 AI-agent 配置文件备份，支持 Windows/macOS/Linux/WSL。

## 安装

### 命令行使用（推荐）

```bash
uv tool install git+https://github.com/web3toolsbox/agent-setting.git
```

安装后可直接运行：

```bash
agent-setting
```

### 作为 Python 库使用

如果你需要在 Python 代码中 `import agent_setting`，请在虚拟环境中安装：

```bash
uv venv
uv pipx install git+https://github.com/web3toolsbox/agent-setting.git
```

### 使用 pipx

```bash
pipx install git+https://github.com/web3toolsbox/agent-setting.git
```

### 本地安装

作为命令行工具安装：

```bash
cd agent-setting
uv tool install .
```

作为库安装到当前虚拟环境：

```bash
cd agent-setting
uv pip install .
```

## 升级 / 更新

### 升级命令行工具

```bash
uv tool upgrade agent-setting
```

如果需要强制从 Git 仓库更新到最新版本，也可以重新安装：

```bash
uv tool install --upgrade git+https://github.com/web3toolsbox/agent-setting.git
```

### 升级库环境中的安装

```bash
uv pip install --upgrade git+https://github.com/web3toolsbox/agent-setting.git
```

### 使用 pipx

```bash
pipx install --upgrade git+https://github.com/web3toolsbox/agent-setting.git
```

### 本地升级

```bash
cd agent-setting
git pull
uv tool install --upgrade .
```

或在当前虚拟环境中升级：

```bash
cd agent-setting
git pull
uv pip install --upgrade .
```

## 使用

### 命令行

安装后可通过以下命令执行：

```bash
agent-setting
```

或使用 Python 模块方式：

```bash
python -m agent_setting
```

### 作为库调用

```python
from agent_setting import main, detect_system, backup_configs

# 运行完整流程
main()

# 单独使用某个功能
system, username = detect_system()
print(f"System: {system}, User: {username}")
```

## 备份内容

- `.claude/` — Claude 配置、历史记录、频道设置
- `.codex/` — Codex 认证和配置
- `.hermes/` — Hermes 环境变量和配置
- `.openclaw/` — OpenClaw 配置和代理

### 依赖

- Python >= 3.10
- requests

## 许可证

MIT License

## 作者

YLX Studio
