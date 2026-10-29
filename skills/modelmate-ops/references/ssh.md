# SSH 路线：首次连接到远端部署

本路线让助手在本机直接操作 Notebook。先跑通连接，再按 [共用工作流](workflow.md) 部署和提交。如果平台没有 SSH、网络暂时不支持或用户不愿配置，直接走 [非 SSH 路线](non-ssh.md)，不阻塞项目。

## 1. 取得这几个信息

| 信息 | 从哪里取得 |
|---|---|
| 运行中的 Notebook | 平台“模型开发/Notebook”列表与实例详情 |
| 主机与端口 | 该实例当前 SSH 字段或完整连接命令，不能用网页 HTTPS 端口替代 |
| SSH 用户 | 连接命令；若平台只给地址，在该实例网页 Terminal 运行 `whoami`；网关用户名与容器用户也可能不同 |
| 本机凭据路径 | 平台下载的私钥或凭据归档，保留原件；只向助手提供文件路径 |
| 主机指纹 | 优先平台/管理员的可信记录；没有时明确采用首次使用信任并记录来源 |

实例停启/重建后可能换入口，先核当前页面。网页姓名通常不是 SSH Linux 用户。登录的是哪个 Notebook，需要在认证后用 `hostname`、`pwd` 和实际项目目录再次确认。

## 2. 本机准备

以下命令均在 **本地终端、仓库根目录**执行。先确认 Python3.10+，安装的是本机连接依赖：

```powershell
python -m pip install -r skills/modelmate-ops/requirements-ssh.txt
$MmTool = (Resolve-Path 'skills/modelmate-ops/scripts/modelmate_ssh.py').Path
python -X utf8 $MmTool --help
```

已安装 skill、无需保留仓库工作目录时，也可将 `$MmTool` 设为实际 skills 安装目录下的脚本绝对路径。Linux/macOS 可以直接使用 `python3 skills/modelmate-ops/scripts/modelmate_ssh.py`，参数相同。

已有共享Anaconda环境、希望隔离连接依赖时，可在本机仓库使用：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r skills/modelmate-ops/requirements-ssh.txt
```

后续SSH命令中的 `python` 换成这个虚拟环境的解释器，助手记录其绝对路径并统一使用；不用修改远端环境或系统Python，也不要求激活脚本改变Shell策略。Linux/macOS 对应 `.venv/bin/python`。

## 3. 从零建立连接配置

在本机 PowerShell 取得实际字段，不把口令输入到聊天：

```powershell
$MmHost = Read-Host 'Notebook详情中的SSH主机'
$MmPort = [int](Read-Host 'Notebook详情中的SSH端口')
$MmUser = Read-Host '平台SSH用户名'
$MmBundle = Read-Host '凭据tar在本机的完整路径'
python -X utf8 $MmTool probe --host $MmHost --port $MmPort --host-key
```

`probe` 默认只测 TCP 和协议 banner；加 `--host-key` 才进行无认证密钥交换并显示服务器公钥指纹，不读取私钥。超时设置有限，不靠 ping 单独判断 SSH 可达。

平台/管理员提供可信指纹时：

```powershell
$MmFingerprint = Read-Host '已核对的SHA256主机指纹，含SHA256:前缀'
python -X utf8 $MmTool init --host $MmHost --port $MmPort --user $MmUser --credentials-archive $MmBundle --host-key-sha256 $MmFingerprint
```

若无带外指纹，明确选择 TOFU（首次使用信任）后使用：

```powershell
python -X utf8 $MmTool init --host $MmHost --port $MmPort --user $MmUser --credentials-archive $MmBundle --trust-first-use
```

TOFU 记录的是首次观测，不声称已由独立渠道验证；后续连接固定该指纹，发生变化会停止。只有这两种信任方式之一才能初始化，不使用“接受所有主机”的策略。

默认保存到本机 `~/.codex/modelmate/connection.json`，并生成对应 receipt；只有本机凭据路径，不复制解密后的私钥或口令。文件已存在时拒绝覆盖。换一个实例可使用独立 profile：

```powershell
python -X utf8 $MmTool --profile '.private/another-notebook.json' init --host $MmHost --port $MmPort --user $MmUser --credentials-archive $MmBundle --trust-first-use
python -X utf8 $MmTool --profile '.private/another-notebook.json' check
```

这里 `.private` 相对于本机当前目录，已被仓库忽略；profile 仍不应外发。所有子命令的 `--profile` 都放在子命令**之前**。助手可根据已有字段直接调用，不必逐条让用户手填。

### 凭据格式

- 平台 tar 若含 `id_rsa` 和 `password.txt`，后者可能是**加密私钥的解密口令**，不是网页密码，也不等于服务器支持密码登录。工具在内存中解密，用公钥认证。
- 成员名不同时，在 `init` 增加 `--key-member` / `--passphrase-member`。归档中没有口令文件时传 `--passphrase-member=`。归档成员按名字读取，不把整个包解压到工程。
- 独立私钥使用 `--identity-file` 替代 `--credentials-archive`，可配 `--passphrase-file` 或 `--passphrase-env`。口令不能直接作为 CLI 字面值。
- 默认按原字节读取口令；只有确认末尾换行是保存时附加的，才用 `--strip-passphrase-newline`。
- `init` 不证明认证成功，下一步还要 `check`。需要更严格核对实例时可提供 `--expected-remote-user` 与 `--expected-notebook-hostname`。

## 4. 验收身份、命令与文件能力

```powershell
python -X utf8 $MmTool check
python -X utf8 $MmTool run --command 'pwd; hostname; id -un' --timeout 20
```

`check` 应分别报告认证、远端用户/主机/目录以及 SFTP 状态。认证成功而 SFTP 失败时，只处理文件子系统，不要重新诊断为网络完全不通。初次身份与平台预期不符时先核映射，别直接操作源码。

## 5. 部署和修改代码

从仓库根打包项目到源目录之外：

```powershell
python skills/modelmate-ops/scripts/project_archive.py pack --source demo-project --output demo-code.zip
```

工具输出 ZIP 的 SHA256 与排除项。默认排除凭据、环境/结果目录、权重及常见数据扩展名；名为 `models`、`datasets`、`data` 的源码包会保留。核对清单中的完整依赖，必要的小型附件可用明确 file-list 选择。文件数、检查条目与字节都有上限，不用于大模型资产搬运；数据上传按工作流另走存储。

由助手确认远端上传目录与**尚不存在**的解包目录，例如当前项目工作区中的 `source-v1`。上传 ZIP 和归档脚本到已确认的 Notebook 目录，再执行：

```text
upload --local <本机demo-code.zip> --remote <远端上传目录/demo-code.zip>
upload --local <本skill的project_archive.py> --remote <远端上传目录/project_archive.py>
run --command 'python3 project_archive.py unpack --archive demo-code.zip --destination source-v1' --cwd <远端上传目录>
```

上面展示子命令参数关系，尖括号由助手换成真实路径；运行时仍要在前面加本机 `python $MmTool`。`unpack` 先验证路径、类型、大小与每个成员 SHA，再创建新目录。重复部署使用新名字，修改既有代码使用带备份的限定补丁。

多行、环境激活和复杂引号优先写入本机 UTF-8/LF 命令文件：

```powershell
python -X utf8 $MmTool run --command-file 'remote-check.sh' --cwd '<已确认的远端项目绝对路径>' --timeout 30
```

`remote-check.sh` 是本机文件。工具把内容送入远端 `bash -s` 的标准输入，避免部分网关重新解释 exec 引号；按 Bash 语法解释，不执行 shebang。此模式用于非交互脚本，标准输入已用于传程序。别通过它交互输入密码；额外数据使用显式文件或脚本内 heredoc。

## 6. 页面提交与下载

数据、依赖、测试、持久化输出以及页面提交表按 [workflow.md](workflow.md) 执行。SSH 进入 Notebook 不等于进入独立训练容器，也不等于已有训练管理 API。

日志输出包后，先取得远端真实 SHA256，再下载到新的本机文件名：

```text
download --remote <远端分析包> --local <本机新路径> --sha256 <源包摘要>
```

上传会回读摘要，下载可与预期摘要比对，两者拒绝覆盖。未给 `--sha256` 的下载只报告接收内容摘要，不能证明与预期源件一致。大结果优先用项目 exporter 或显式文件表，避免递归全打。

## 7. 连接失败时

| 最后通过的阶段 | 下一步 |
|---|---|
| 无法解析地址 | 核域名、DNS、校园/企业网络与 VPN |
| TCP 超时/拒绝 | 核端口、Notebook状态、SSH开关和允许的网络路径 |
| TCP通但不是SSH banner | 核网页端口/SSH网关映射，不反复换密钥 |
| 已到SSH但主机指纹变了 | 核实例或网关更换，经可信途径确认后使用新profile，别自动接受变化 |
| 私钥无法加载 | 核文件格式、归档成员名、口令来源与文件权限，不打印内容 |
| 公钥认证失败 | 核SSH用户名、实例密钥绑定、算法和账户状态 |
| 已认证但命令失败 | 看返回退出码/stderr，核Bash、目录、激活环境与权限 |

本 helper 直接连接目标 TCP，不自动读取 OpenSSH config、ssh-agent、ProxyJump 或 HTTP 代理。浏览器/VPN能打开网页并不保证这条 TCP 路由可用。需跳板时采用平台批准的原生 OpenSSH 路线单独验证；不要用公共中继或盲目换443。暂时无法连接就切到非SSH路线继续部署。

Windows 的 `Bad permissions` 应检查实际 ACL；不把 Linux chmod 当作完整 Windows 权限修复。原生 OpenSSH 客户端不需要在本机安装 sshd 服务。超时只结束本机等待，不证明远端子进程已停止；长训练使用正式作业调度，不作为一条超长 SSH run 挂住。
