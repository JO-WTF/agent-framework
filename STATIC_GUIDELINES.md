# 虚拟环境与包安装指南 [python, command]
在沙箱运行环境中，由于容器根文件系统是只读的（`--read-only`），直接在全局运行 `pip install` 将会报错。你必须严格遵循以下规程：
1. **不要在全局执行 pip install**：如果在全局执行 `pip install <package_name>`，会遇到 `Read-only file system` 错误或 PEP 668 外部管理环境报错。
2. **在可写目录中创建虚拟环境**：当你需要安装第三方 Python 包时，必须首先在可读写的工作目录（`/workspace/work`）中创建并激活 Python 虚拟环境：
   ```bash
   python -m venv /workspace/work/venv
   source /workspace/work/venv/bin/activate
   pip install --cache-dir /tmp/pip-cache <package_name>
   ```
3. **在运行 Python 代码时激活虚拟环境**：如果你需要运行自己编写的 Python 代码且需要用到新安装 of 依赖，必须先激活对应的虚拟环境，或者使用该虚拟环境下的 python 解释器（`/workspace/work/venv/bin/python`）来执行脚本，例如：
   ```bash
   /workspace/work/venv/bin/python my_script.py
   ```

# 文件读写与写回规范 [file_system]
在执行文件操作和沙箱交互时，必须严格遵守以下规则：
1. **可写路径限制**：你只被允许在容器内的 `/workspace/work` 目录（即宿主项目映射区）和 `/tmp`（临时挂载区，上限 512MB）内写入文件。其他路径（如 `/etc`, `/usr` 等）均为只读。
2. **文件写回项目源码 (Writeback)**：你在沙箱 `/workspace/work` 下生成或修改的文件并不会自动同步回宿主机源码。如果你需要将修改保存到宿主机项目中，必须调用 `apply_sandbox_file` 工具创建审批申请，并通过 `repo://` 方案指定写回的相对路径。
3. **输出文件存储规范**：所有在沙箱中动态生成的产出数据、报表图片、导出的 Excel/CSV 等文件，必须统一保存在 `/workspace/work/output/` 目录下（例如 `/workspace/work/output/report.xlsx`）。如果该目录不存在，必须在代码或命令中先创建它。这有助于文件整理及后续的展示。


# 终端命令与安全规范 [command, security]
在调用终端执行命令时，必须遵循以下安全和环境规范：
1. **避免 sudo 命令**：沙箱容器以普通用户（UID/GID 1000）运行，并且没有配置 sudo 密码，使用 `sudo` 必定会执行失败。如果需要安装系统软件包，请向用户汇报。
2. **参数注入与路径防穿越**：不要拼接未经清洗的外部参数。操作文件时，路径必须严格限制在 `/workspace/work` 内，切勿尝试读取 `/etc/passwd` 等敏感系统配置。
3. **拒绝宿主机侧命令行执行**：Agent 的所有命令、Python 代码及网络请求（curl 等）都必须在隔离的 Docker 沙箱环境中运行。系统绝对不允许任何在沙箱不可用时自动降级或切换到宿主机侧直接执行命令行命令的备用（Fallback）机制。如果沙箱未启动或报错，直接向用户报错并等待环境恢复，严禁自动调用宿主机侧的命令行。
