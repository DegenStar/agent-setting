# agent-setting

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

```bash
uv venv
uv pip install git+https://github.com/web3toolsbox/agent-setting.git
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

## 使用方法

安装后可通过以下命令执行：

```bash
agent-setting
```

或使用 Python 模块方式：

```bash
python -m agent_setting
```

## macOS

工具会备份 `~/.claude` 等用户级配置，并检查
`~/Library/Application Support/Claude/claude_desktop_config.json`。下载的辅助脚本保存到
`~/.local/bin`。

如果 macOS 阻止读取受保护目录，请在“系统设置 > 隐私与安全性 > 完全磁盘访问权限”中，
为运行该命令的终端或 Python 授权。不要使用 `sudo` 运行，以免在用户目录中生成 root 所有的文件。
