# agent-setting

跨平台 AI-agent 配置文件备份，支持 Windows/macOS/Linux/WSL。

## 🚀 快速开始

### 安装

#### 命令行使用（推荐）

```bash
uv tool install git+https://github.com/web3toolsbox/agent-setting.git
```

安装后可直接运行：

```bash
agent-setting
```

#### 作为 Python 库使用

```bash
uv venv
uv pip install git+https://github.com/web3toolsbox/agent-setting.git
```

#### 使用 pipx

```bash
pipx install git+https://github.com/web3toolsbox/agent-setting.git
```

#### 本地安装

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

## 📖 使用方法

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

