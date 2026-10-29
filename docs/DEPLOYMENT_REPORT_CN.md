# ModelMate 平台全流程部署操作报告

版本：v0.1.0 · 更新日期：2026-10-29

项目仓库：[ligoldfish/modelmate-ops](https://github.com/ligoldfish/modelmate-ops) · 许可证：MIT

本报告面向第一次使用 ModelMate / NAIE 的读者。按其中一条路线操作，可以完成代码和数据准备、修改与测试、正式训练作业的页面提交、运行检查以及结果下载。命令以本地 Windows PowerShell、远端 Linux Bash 为例；不同部署的菜单名称可能略有不同，实际资源、路径和存储映射以当前平台页面为准。

报告使用一个小型线性回归项目演示完整流程。它生成64条数据，执行200步梯度下降，输出配置、训练指标和结果，不需要下载模型或安装深度学习框架。熟悉流程后，可按第8节换成自己的训练项目。示例使用 CPU，主要用于验证部署链路；多卡训练的资源安排由实际项目决定。

## 1. 先理解执行位置，再开始操作

下面四个位置很容易混淆。后文每组命令都会标明在哪里执行。

| 位置 | 用来做什么 | 如何进入 |
|---|---|---|
| 本地电脑 | 保存代码、安装 skill、通过 SSH 执行命令、下载结果 | Windows PowerShell |
| Notebook 容器 | 准备文件、检查环境、修改和测试代码 | 平台 JupyterLab Terminal，或本地 SSH 工具 |
| 正式训练容器 | 按页面选择的镜像和资源运行训练入口 | 在平台创建训练作业后自动启动 |
| 持久化存储 | 保存数据、模型、日志和结果，供相应容器读取 | 平台挂载的 Linux 目录，或按平台方式访问对象存储 |

SSH 连接的是 Notebook。它可以完成文件和代码操作，但本报告采用的平台流程仍需在网页创建正式训练作业。Notebook 里跑通代码，也不代表正式训练已经启动。

完整路线是：

```text
登录平台 → 创建 Notebook → 确认工作目录与持久化目录
                          ↓
                  SSH 或网页 Terminal
                          ↓
          准备数据 → 上传代码 → 修改配置 → 小测试
                          ↓
                平台页面创建正式训练作业
                          ↓
           核对启动日志 → 监控 → 导出结果 → 下载验哈希
```

有 SSH 地址和本机凭据时，使用第4节；没有 SSH 时，使用第5节。两条路线都在第6节提交正式作业，最后按第7节取回结果。只需选择一条部署路线。

## 2. 取得仓库并安装 skill

### 2.1 下载和定位仓库

在 GitHub 仓库页面点击 **Code → Download ZIP**，解压到本机。打开解压后的文件夹，应能看到 `README.md`、`scripts`、`skills` 和 `tests`。在此文件夹打开 PowerShell。也可使用已安装的 Git：

**执行位置：本地 PowerShell。**

```powershell
git clone https://github.com/ligoldfish/modelmate-ops.git
cd modelmate-ops
```

使用 ZIP 时，直接打开解压目录，不必运行上面的克隆命令。以下命令确认当前目录，并记录后面使用的绝对路径：

```powershell
python --version
Test-Path scripts/install_skill.py
$MmRepo = (Get-Location).Path
$MmSshTool = Join-Path $MmRepo 'skills/modelmate-ops/scripts/modelmate_ssh.py'
$MmArchiveTool = Join-Path $MmRepo 'skills/modelmate-ops/scripts/project_archive.py'
```

成功标志：Python 为3.10或更新版本，`Test-Path` 输出 `True`。如果命令找不到 Python，先安装 Python，并重新打开 PowerShell；Windows 也可以使用自己已确认的 Python 解释器完整路径。

### 2.2 安装到 Codex

**执行位置：本地 PowerShell，仓库根目录。**

```powershell
python scripts/install_skill.py
```

安装器会打印实际安装目录；已有同名 skill 会先备份到 skills 目录之外。个人 SSH 连接配置不随 skill 覆盖。重新打开一个 Codex 会话后，可以说：

```text
请使用 $modelmate-ops。我的平台已经登录，项目准备部署。
请先确认工作目录、持久化存储和资源，再按 SSH 优先的流程完成准备。
正式训练通过平台页面提交，并记录该次运行的日志和结果路径。
```

没有 Codex 时，也可以直接按本报告运行脚本。安装 skill 不是手动部署的必要条件。

### 2.3 建立独立练习目录

后续命令在同一个 PowerShell 窗口继续执行，以保留 `$Mm...` 变量。关闭窗口后，需重新执行相应变量定义。脚本和数据使用实际路径，不依赖终端一直位于某个目录。

**执行位置：本地 PowerShell。**

```powershell
$MmWork = Join-Path (Split-Path $MmRepo -Parent) 'modelmate-demo-work'
New-Item -ItemType Directory -Force $MmWork | Out-Null
$MmLocalProject = Join-Path $MmWork 'demo-project-v1'
$MmStarter = Join-Path $MmRepo 'skills/modelmate-ops/assets/starter'
python -c "import shutil,sys; shutil.copytree(sys.argv[1],sys.argv[2],ignore=shutil.ignore_patterns('__pycache__'))" $MmStarter $MmLocalProject
python (Join-Path $MmLocalProject 'main.py') --check
python (Join-Path $MmLocalProject 'main.py')
```

如果 `demo-project-v1` 已存在，复制操作会拒绝覆盖。继续使用已确认的目录，或把变量改成新的版本名，无需删除旧目录。

成功标志：先出现 `check: config_parsed`，训练输出 `METRIC=`，最后输出 `COMPLETE=`。默认200步时，结果应接近 `weight=3`、`bias=-0.5`，均方误差显著低于初始值。均方误差是预测值与真实值之差的平方平均，越小越好。这里的目的在于确认代码、配置和输出均可工作。

## 3. 在平台准备 Notebook 与目录

### 3.1 创建或复用 Notebook

**执行位置：ModelMate 网页。**

1. 登录平台，选择正确的租户或工作空间，进入“模型训练 → 模型开发”或当前版本的 Notebook 页面。
2. 点击“新建”，填写英文名称，选择本账号有权限的镜像、资源池和规格。练习只要求镜像内有 Bash、Python3.10+，选择平台允许的最小适用资源即可。
3. 选择代码或启动目录。某些部署要求目录位于租户存储的 `usercode` 子目录下；按页面帮助创建子目录后选择。
4. 有 SSH 选项时可开启“远程 SSH 登录”，及时保存平台提供的凭据原件。有些部署只允许下载一次。
5. 确认自动关闭时长，再创建并启动 Notebook。进入 JupyterLab，等待文件面板与 Terminal 可用。

没有 SSH 开关不影响第5节的流程。若资源池或规格不可选，需要由拥有平台资源管理权限的人调整配额或权限；本地 SSH 不能补出平台资源。

### 3.2 确认用户名、工作目录与存储

**执行位置：JupyterLab 网页 Terminal。** 在文件面板打开希望放置代码的文件夹，再通过菜单打开 Terminal。Terminal 中粘贴命令后按普通 **Enter**；Shift+Enter 用于 Notebook 代码单元。

```bash
whoami
hostname
pwd -P
python3 --version
df -h .
```

记录以下实际值，不把网页姓名当作 SSH 用户名，也不把浏览器 URL 当作文件系统路径。

| 要记录的信息 | 从哪里取得 | 后续用途 |
|---|---|---|
| 平台入口、Notebook 名称 | 平台页面 | 找回同一实例 |
| SSH 主机、端口 | Notebook 详情的 SSH 字段 | 仅 SSH 路线需要 |
| SSH 用户 | 页面连接命令；未提供时核对 `whoami` | 公钥认证 |
| 本机凭据路径 | 本机下载文件 | 仅保存在本机配置 |
| Notebook 工作目录 | 上面的 `pwd -P` | 上传和解包代码 |
| 持久化输出目录 | 平台挂载说明、DPC信息和实际可写目录 | 正式训练保存结果 |
| 网页源码目录映射 | 代码选择器与实际文件列表 | 选择正式训练启动文件 |

Notebook 工作目录不一定就是持久化结果目录。结合平台“存储挂载/DPC/数据集”说明，确定一个**属于自己项目、正式训练也能访问**的持久化父目录。在网页 Terminal 验证：

```bash
read -r -p '输入已确认的持久化父目录绝对路径: ' MM_PERSIST_PARENT
test -d "$MM_PERSIST_PARENT" && test -w "$MM_PERSIST_PARENT" || {
  echo '目录不存在或不可写，请重新核对平台挂载'; exit 1;
}
df -h "$MM_PERSIST_PARENT"
```

本例在该父目录下使用专属的 `modelmate-demo-results` 子目录。每次训练还会生成独立运行子目录。记下该完整路径，下一节将它写入项目配置。正式作业页面需要配置挂载时，要为作业挂载同一存储，并核对容器内路径；Notebook 可写不能单独证明作业容器也可写。

## 4. 路线 A：通过 SSH 部署、修改和测试

### 4.1 安装本机连接依赖

**执行位置：本地 PowerShell。** 使用独立虚拟环境，避免改动已有的科研环境：

```powershell
$MmSshEnv = Join-Path $MmWork 'ssh-tools'
python -m venv $MmSshEnv
$MmPython = Join-Path $MmSshEnv 'Scripts/python.exe'
& $MmPython -m pip install -r (Join-Path $MmRepo 'skills/modelmate-ops/requirements-ssh.txt')
& $MmPython -X utf8 $MmSshTool --help
```

后续 SSH 命令统一使用 `$MmPython`。这些依赖只安装在本机，不改变 Notebook 的训练环境。

### 4.2 从零建立连接

**执行位置：本地 PowerShell。**

```powershell
$MmHost = Read-Host 'Notebook详情中的SSH主机'
$MmPort = [int](Read-Host 'Notebook详情中的SSH端口')
$MmUser = Read-Host 'SSH用户名'
$MmBundle = Read-Host '凭据tar在本机的完整路径'
& $MmPython -X utf8 $MmSshTool probe --host $MmHost --port $MmPort --host-key
```

成功标志：TCP、SSH协议和服务器指纹可读取。网页能打开但 TCP 超时，先检查校园/企业网络、VPN 与该 SSH 端口的可达性。浏览器代理不一定代理原始 TCP；本工具直接连接 SSH 地址，不自动读取 HTTP 代理、OpenSSH 配置或跳板设置。

如果平台或管理员提供了可信指纹，使用下面第一种初始化方式：

```powershell
$MmFingerprint = Read-Host '已核对的主机SHA256指纹，含SHA256:前缀'
& $MmPython -X utf8 $MmSshTool init --host $MmHost --port $MmPort --user $MmUser --credentials-archive $MmBundle --host-key-sha256 $MmFingerprint
```

若没有带外指纹，可以明确采用首次使用信任，改用下面这一条；两条初始化命令选一条即可：

```powershell
& $MmPython -X utf8 $MmSshTool init --host $MmHost --port $MmPort --user $MmUser --credentials-archive $MmBundle --trust-first-use
```

首次使用信任会记录第一次看到的主机指纹，后续不匹配时停止连接。它没有独立证明首次连接的主机身份。默认 profile 保存于本机用户目录的 `.codex/modelmate/connection.json`，记录凭据位置和主机身份，不保存解密后的私钥。

常见凭据包包含 `id_rsa` 与 `password.txt`：后者可能是私钥解密口令，工具用解密后的密钥做公钥认证。成员名不同时加 `--key-member`、`--passphrase-member`；没有口令成员时用 `--passphrase-member=`。独立私钥改用 `--identity-file`，详见 [SSH 参数说明](../skills/modelmate-ops/references/ssh.md)。不要把私钥或口令放入聊天、源码或 GitHub。

如果默认 profile 已存在，先运行 `check`。连接其他实例可用 `--profile` 指定新的本机配置路径，放在 `init/check/run/upload/download` 子命令之前；工具拒绝覆盖旧配置。

```powershell
& $MmPython -X utf8 $MmSshTool check
& $MmPython -X utf8 $MmSshTool run --command 'pwd; hostname; id -un' --timeout 20
```

成功标志：认证与 SFTP 成功，返回的用户和主机符合当前 Notebook。`init` 完成只表示配置已经写入，以上 `check` 才验证登录和文件能力。

### 4.3 配置正式输出目录并打包

**执行位置：本地 PowerShell。** 将第3节取得的实际值输入变量。为了让本报告中拼接的演示命令可以直接执行，下面的远端路径使用英文、数字、`_`、`-`、`.` 与 `/`，不含空格。工具本身可以通过 `--cwd` 和命令文件处理更复杂的路径。

```powershell
function Assert-MmRemotePath([string]$Path) {
  if ($Path -notmatch '^/[A-Za-z0-9._/-]+$') {
    throw '本演示请使用不含空格的英文远端绝对路径'
  }
}
$MmRemoteWork = (Read-Host 'Notebook文件面板对应的pwd -P绝对路径').TrimEnd('/')
$MmOutputRoot = (Read-Host '本项目持久化输出完整路径，以modelmate-demo-results结尾').TrimEnd('/')
Assert-MmRemotePath $MmRemoteWork
Assert-MmRemotePath $MmOutputRoot
$MmConfigPath = Join-Path $MmLocalProject 'config.json'
$MmConfig = Get-Content -Raw -Encoding UTF8 $MmConfigPath | ConvertFrom-Json
$MmConfig.output_root = $MmOutputRoot
[IO.File]::WriteAllText($MmConfigPath, ($MmConfig | ConvertTo-Json), [Text.UTF8Encoding]::new($false))
python (Join-Path $MmLocalProject 'main.py') --check
```

前面的本地训练已经完成；输出配置改成远端路径后，只在本地做配置解析检查，后续训练在远端执行。准备版本名和代码包：

```powershell
$MmTag = (Get-Date -Format 'yyyyMMddTHHmmss') + '-' + [guid]::NewGuid().ToString('N').Substring(0,8)
$MmCodeZip = Join-Path $MmWork "demo-code-$MmTag.zip"
$MmRemoteZip = "$MmRemoteWork/demo-code-$MmTag.zip"
$MmRemoteArchiveTool = "$MmRemoteWork/archive-$MmTag.py"
$MmRemoteProject = "$MmRemoteWork/demo-src-$MmTag"
python $MmArchiveTool pack --source $MmLocalProject --output $MmCodeZip
$MmCodeSha = (Get-FileHash -Algorithm SHA256 $MmCodeZip).Hash.ToLowerInvariant()
& $MmPython -X utf8 $MmSshTool upload --local $MmCodeZip --remote $MmRemoteZip --sha256 $MmCodeSha
& $MmPython -X utf8 $MmSshTool upload --local $MmArchiveTool --remote $MmRemoteArchiveTool
& $MmPython -X utf8 $MmSshTool run --command "python3 $MmRemoteArchiveTool unpack --archive $MmRemoteZip --destination $MmRemoteProject" --timeout 60
```

成功标志：上传摘要校验通过，解包返回 `status: verified`。代码包默认过滤本地环境、输出、权重和常见原始数据；必要的源码包会保留。它用于小型代码部署，不用于搬运大模型。解包目录必须是新目录，原有实验目录不会被覆盖。

### 4.4 验证配置、数据和可写目录

**执行位置：本地 PowerShell；命令由 SSH 在 Notebook 内执行。**

```powershell
& $MmPython -X utf8 $MmSshTool run --cwd $MmRemoteProject --command 'bash -n run_modelmate.sh; python3 main.py --check' --timeout 30
& $MmPython -X utf8 $MmSshTool run --cwd $MmRemoteProject --command 'python3 main.py --prepare-only' --timeout 30
```

`--prepare-only` 应输出64条数据和 SHA256。再用命令文件做实际写入验证，复杂脚本通过标准输入传入 Bash，避免网关重新解释引号：

```powershell
$MmPreflight = Join-Path $MmWork "preflight-$MmTag.sh"
$MmPreflightText = @'
set -euo pipefail
python3 - <<'PY'
import json, pathlib, tempfile
c = json.loads(pathlib.Path('config.json').read_text(encoding='utf-8-sig'))
p = pathlib.Path(c['output_root'])
assert p.is_absolute(), 'output_root must be absolute'
p.mkdir(parents=True, exist_ok=True)
with tempfile.TemporaryFile(dir=p) as f:
    f.write(b'modelmate-write-check')
    f.flush()
print('PERSISTENT_OUTPUT_WRITE_OK=' + str(p))
PY
bash run_modelmate.sh --check
'@
[IO.File]::WriteAllText($MmPreflight, ($MmPreflightText.Replace("`r`n", "`n") + "`n"), [Text.UTF8Encoding]::new($false))
& $MmPython -X utf8 $MmSshTool run --cwd $MmRemoteProject --command-file $MmPreflight --timeout 30
& $MmPython -X utf8 $MmSshTool run --cwd $MmRemoteProject --command 'bash run_modelmate.sh' --timeout 60
```

成功标志：出现 `PERSISTENT_OUTPUT_WRITE_OK`，小训练正常完成，返回 JSON 中 `exit_code` 为0，`stdout` 中有 `COMPLETE=`。这是 Notebook 小测试的结果，正式作业还要在第6节提交。

修改测试练习：将本地 `config.json` 的 `steps` 改成100，再按4.3节生成新的 `$MmTag` 并重新打包到新目录，重复4.4节检查。正式练习建议恢复200步，以便与本报告结果核对。已有项目升级也应保留旧目录和版本记录；不要直接覆盖正在被训练读取的共享源码。

## 5. 路线 B：不用 SSH，通过网页部署、修改和测试

### 5.1 本机打包和网页上传

本路线不安装 SSH 依赖，也不创建连接 profile。先完成第2、3节，然后在本地打包。

**执行位置：本地 PowerShell。**

```powershell
$MmTag = (Get-Date -Format 'yyyyMMddTHHmmss') + '-' + [guid]::NewGuid().ToString('N').Substring(0,8)
$MmCodeZip = Join-Path $MmWork "demo-code-$MmTag.zip"
python $MmArchiveTool pack --source $MmLocalProject --output $MmCodeZip
Get-FileHash -Algorithm SHA256 $MmCodeZip
$MmArchiveTool
$MmCodeZip
```

记下包的 SHA256。通过 JupyterLab 文件面板的上传按钮，将刚才的代码 ZIP 和本机 `$MmArchiveTool` 指向的 `project_archive.py` 上传到第3节选定的工作文件夹。文件面板中的这两个文件应可见。

### 5.2 检查上传内容并解包

**执行位置：该文件夹的 JupyterLab Terminal。**

```bash
pwd -P
ls -l
read -r -p '输入刚上传的代码ZIP文件名: ' MM_ZIP
test -f "$MM_ZIP" || { echo '未找到ZIP，请核对当前目录'; exit 1; }
sha256sum "$MM_ZIP"
```

与本机摘要一致后继续：

```bash
read -r -p '输入新的源码目录名，例如demo-src-v1: ' MM_RELEASE_NAME
MM_WORK="$(pwd -P)"
MM_RELEASE="$MM_WORK/$MM_RELEASE_NAME"
MM_ARCHIVE_TOOL="$MM_WORK/project_archive.py"
python3 "$MM_ARCHIVE_TOOL" unpack --archive "$MM_ZIP" --destination "$MM_RELEASE"
cd "$MM_RELEASE"
```

成功标志：`status: verified`，目录内有 `main.py`、`config.json` 和 `run_modelmate.sh`。如果目录已经存在，换一个新版本名。

### 5.3 修改配置，执行小训练

**执行位置：JupyterLab 文件编辑器。** 打开刚解包目录中的 `config.json`，保留其他字段，将 `output_root` 改成第3节确认的项目持久化完整路径，保存。不要填写浏览器路径或 `s3://` 对象地址。JSON 字符串用双引号，字段之间用逗号。

**执行位置：同一源码目录的网页 Terminal。**

```bash
bash -n run_modelmate.sh
python3 main.py --check
python3 main.py --prepare-only
python3 - <<'PY'
import json, pathlib, tempfile
c = json.loads(pathlib.Path('config.json').read_text(encoding='utf-8-sig'))
p = pathlib.Path(c['output_root'])
assert p.is_absolute(), '请将output_root设为持久化绝对路径'
p.mkdir(parents=True, exist_ok=True)
with tempfile.TemporaryFile(dir=p) as f:
    f.write(b'modelmate-write-check')
    f.flush()
print('PERSISTENT_OUTPUT_WRITE_OK=' + str(p))
PY
bash run_modelmate.sh
```

逐条检查退出情况。网页 Terminal 会直接显示输出，应看到 `PERSISTENT_OUTPUT_WRITE_OK` 与最终的 `COMPLETE=`，没有报错；紧接训练运行 `echo $?` 应为0。示例完成后，可在编辑器把 `steps` 改成100并保存，再运行 `--check` 和小训练，体验改码与验证。正式练习前恢复200。网页编辑器必须保存后才会影响后续执行。

**关键区别：**本路线修改的是 Notebook 中的配置。只有提交正式作业时选择了这份源码，作业才会用到修改后的内容。已经创建的作业可能使用提交时的快照，后续 Notebook 编辑不会自动更新它。

## 6. 在平台页面提交正式训练

### 6.1 按已经验收的源码填写页面

**执行位置：ModelMate 网页。** 进入“模型训练 → 训练作业”或当前版本对应页面，点击“新建”。本示例按以下内容填写：

| 表单字段 | 本示例的填写方式 |
|---|---|
| 作业名称 | 英文且唯一，例如带日期和短版本号的名称 |
| 代码来源 | 选择刚才修改、测试的 Notebook / 源码目录；若页面要求同步或上传，先完成该步骤 |
| 启动文件 | 代码选择器里同一版本目录下的 `run_modelmate.sh` |
| 镜像 | 有 Bash、Python3.10+ 的兼容镜像；尽量与已测试 Notebook 的环境一致 |
| 资源池与规格 | 账号有权限且适合此示例的最小规格；Worker为1 |
| 存储挂载 | 挂载已确认的持久化输出区域，并核对容器内路径与配置一致 |
| 数据集 / 检查点 | 本示例自行生成数据，不依赖外部检查点；页面允许时留空 |
| 运行参数 | 留空，示例读取默认 `config.json` |
| 环境变量 | 留空，普通启动不需要手填 |
| 重试设置 | 练习阶段使用可控次数，避免失败后无限重复 |

Notebook Linux 绝对路径与网页选择器的路径可能不同。通过目录层级、文件名和实际版本对应关系定位入口，不把本机路径直接填入平台。提交前确认输出目录在**作业容器**内的挂载路径也成立；若不同，先修改配置并重新验收。

本示例脚本能接收平台自动传入的空存储参数，也兼容 `CONFIG/config/--CONFIG/--config` 的等号和双 token 形式。常规练习不需要填写这些参数。已有业务项目必须自己具备相同的入口兼容能力，不能因为示例兼容就假定任意项目都兼容。

### 6.2 提交后核对日志

点击提交后，记录平台作业/批次 ID、名称、源码版本、资源、提交时间与持久化输出配置。如果点击后等待或超时，先去作业列表核实是否已经创建，避免重复提交。

进入该作业的“运行日志”，应依次看到：

```text
STARTER_RUN={... "output_dir": "实际运行目录", ...}
METRIC={"step": 1, "mse": ...}
METRIC={"step": 50, "mse": ...}
...
COMPLETE=实际运行目录/result.json
```

成功标志是本次正式作业正常退出，且 `COMPLETE=` 指向的文件实际存在。页面“运行中”只是平台状态；只看到启动信息，也不等于训练已经完成。检查 `STARTER_RUN` 中的 Python、主机、配置和输出目录是否符合预期。

记录这次**正式作业**的 `COMPLETE=` 路径，下一节用它导出。不要误用前面 Notebook 小测试的路径，也不自动选择“最新目录”。

### 6.3 监控、时间估计与恢复

本示例很小，以日志完成情况为准；平台排队和容器启动可能比计算本身更久。真实训练优先使用项目监控器。没有监控器时，只读固定日志和指标文件：

**执行位置：Notebook Terminal；先输入这次实际文件路径。**

```bash
read -r -p '输入本次训练日志完整路径: ' MM_LOG
test -f "$MM_LOG" && tail -n 80 "$MM_LOG"
read -r -p '输入本次metrics.jsonl完整路径: ' MM_METRICS
test -f "$MM_METRICS" && tail -n 5 "$MM_METRICS"
```

正式作业未向共享存储写日志时，使用平台运行日志。Notebook 的 `ps` 或设备占用不能证明另一个作业容器的进程状态。

一般可用近期已完成普通训练轮的平均耗时乘剩余轮数，估算训练部分的剩余时间；验证、刷新和最终评估另算。多个实验并行时按最慢剩余任务估计墙钟时间。还未出现稳定训练轮时，时间标记为“待校准”。停止监控窗口不会停止正式作业；停止训练应在平台管理该批次。恢复训练须指定原运行、配置、检查点和兼容源码，不自动猜最新目录或删除锁文件。

## 7. 取回这次正式作业的结果

### 7.1 决定导出什么

示例的必要分析文件只有三个：`result.json`、`resolved.json`、`metrics.jsonl`。它们分别说明最终指标与源码/数据身份、实际解析的配置与环境、训练过程指标。归档工具额外写入成员清单及每个文件摘要。

真实项目还可能需要任务定义、数据划分、评估协议、逐样本结果、统计汇总、成本和阶段日志。按项目索引建立显式文件表；排除权重以后，也不应递归打包缓存或几百万个中间文件。用于续训的检查点留在持久化存储，分析包不承担续训备份的职责。

### 7.2 SSH 路线：导出并校验下载

**执行位置：本地 PowerShell，沿用第4节变量。** 从正式作业日志复制 `COMPLETE=` 后面的完整路径，不包含 `COMPLETE=` 字样。

```powershell
$MmResultPath = Read-Host '正式作业COMPLETE后的result.json完整路径'
Assert-MmRemotePath $MmResultPath
if (-not $MmResultPath.EndsWith('/result.json')) { throw '应输入result.json完整路径' }
$MmRun = $MmResultPath.Substring(0, $MmResultPath.LastIndexOf('/'))
$MmResultList = Join-Path $MmWork "result-files-$MmTag.json"
[IO.File]::WriteAllText($MmResultList, '["result.json","resolved.json","metrics.jsonl"]', [Text.UTF8Encoding]::new($false))
$MmRemoteList = "$MmRemoteWork/result-files-$MmTag.json"
$MmRemoteResults = "$MmRemoteWork/demo-analysis-$MmTag.zip"
& $MmPython -X utf8 $MmSshTool upload --local $MmResultList --remote $MmRemoteList
$MmExportRaw = & $MmPython -X utf8 $MmSshTool run --command "python3 $MmRemoteArchiveTool export --root $MmRun --file-list $MmRemoteList --output $MmRemoteResults" --timeout 60
if ($LASTEXITCODE -ne 0) { throw '远端结果导出失败，请检查工具输出' }
$MmExportReply = $MmExportRaw | ConvertFrom-Json
if ($MmExportReply.exit_code -ne 0) { throw $MmExportReply.stderr }
$MmExport = $MmExportReply.stdout | ConvertFrom-Json
$MmExport
$MmLocalResults = Join-Path $MmWork "demo-analysis-$MmTag.zip"
& $MmPython -X utf8 $MmSshTool download --remote $MmRemoteResults --local $MmLocalResults --sha256 $MmExport.sha256
Get-FileHash -Algorithm SHA256 $MmLocalResults
```

成功标志：导出只包含三个结果文件和清单，下载摘要与远端导出返回的 `sha256` 一致。将包解到新的本地目录即可阅读：

```powershell
$MmAnalysis = Join-Path $MmWork "analysis-$MmTag"
python $MmArchiveTool unpack --archive $MmLocalResults --destination $MmAnalysis
Get-Content -Raw -Encoding UTF8 (Join-Path $MmAnalysis 'result.json')
```

如果重新开过 PowerShell 或 Notebook 已重建，先恢复实际脚本路径、连接配置、远端归档工具路径与工作目录，再操作，不能仅凭变量名猜测原值。

### 7.3 非 SSH 路线：导出到文件面板并下载

**执行位置：JupyterLab Terminal。** 输入本次正式作业结果文件、归档脚本和可在文件面板看到的目录的实际绝对路径：

```bash
read -r -p '正式作业COMPLETE后的result.json完整路径: ' MM_RESULT
test -f "$MM_RESULT" || { echo '文件不存在，请核对作业与挂载'; exit 1; }
MM_RUN="$(dirname "$MM_RESULT")"
read -r -p 'project_archive.py的完整路径: ' MM_ARCHIVE_TOOL
read -r -p '文件面板可见的下载目录绝对路径: ' MM_DOWNLOAD
test -d "$MM_DOWNLOAD" || { echo '下载目录不存在'; exit 1; }
MM_TAG="$(date -u +%Y%m%dT%H%M%SZ)-$$"
MM_LIST="$MM_DOWNLOAD/result-files-$MM_TAG.json"
MM_PACKAGE="$MM_DOWNLOAD/demo-analysis-$MM_TAG.zip"
python3 - "$MM_LIST" <<'PY'
import json, pathlib, sys
with pathlib.Path(sys.argv[1]).open('x', encoding='utf-8') as f:
    json.dump(['result.json', 'resolved.json', 'metrics.jsonl'], f)
PY
python3 "$MM_ARCHIVE_TOOL" export --root "$MM_RUN" --file-list "$MM_LIST" --output "$MM_PACKAGE"
sha256sum "$MM_PACKAGE"
```

在 JupyterLab 文件面板进入 `MM_DOWNLOAD` 对应目录，刷新后找到新 ZIP，右键 **Download/下载**。如果文件面板看不到 `/tmp` 等目录，不能只在那儿生成文件后等按钮出现；应把输出直接放到已确认的面板目录。

**执行位置：本地 PowerShell。**

```powershell
$MmDownloadedZip = Read-Host '本机已下载ZIP的完整路径'
Get-FileHash -Algorithm SHA256 $MmDownloadedZip
```

与远端摘要一致后，用本地归档工具解包到新目录：

```powershell
$MmAnalysis = Join-Path $MmWork ("analysis-" + [guid]::NewGuid().ToString('N').Substring(0,8))
python $MmArchiveTool unpack --archive $MmDownloadedZip --destination $MmAnalysis
Get-Content -Raw -Encoding UTF8 (Join-Path $MmAnalysis 'result.json')
```

SHA256 是文件内容的摘要；源端与本地摘要一致，才能确认拿到的是同一份包。保留远端结果原件，直到完成分析和备份。

## 8. 将示例换成自己的训练项目

### 8.1 准备项目入口和运行环境

先在本地确认下列内容，再部署到新版本目录。普通启动参数写入项目配置或入口默认值；部署者根据平台实际资产准备默认配置，最终使用者只需选择代码、入口与资源。

| 项目部分 | 需要落实的内容 |
|---|---|
| 启动入口 | 自行定位项目根目录，使用确定的 Python，兼容平台自动注入的参数 |
| Python 与框架 | 核对 CPU架构、Python、驱动、CANN、torch/torch_npu 等兼容关系；使用项目专用运行时 |
| 模型和数据 | 使用容器内实际可读路径，检查文件、版本、划分和必要摘要；不要从文件名推断身份 |
| 配置 | 模型、数据、批大小、线程、随机种子和输出设置均有正常可用默认值，打印最终值 |
| 输出与日志 | 持久化目录、独立运行ID、完整阶段日志，运行中及时刷新重要指标 |
| 多卡执行 | 明确 Worker 是进程还是节点、单元如何分配，按项目实现选择 DDP/FSDP/任务并行等方式 |
| 验收与结果 | 针对性的导入、数据、小步训练和评估检查，明确完成标志与分析文件列表 |

环境激活后，重新检查 `sys.executable`、源码导入位置及必要框架版本，防止 activation 改写 `PYTHONPATH` 后导入到错误版本。路径问题先确认“实际使用的解释器和源码”，不用反复重装依赖来碰运气。不要覆盖平台管理的 NPU 可见性，也不要把示例的 CPU 结果视作 NPU 训练验证。

物理 batch、跨卡调度和缓存会影响执行效率；是否同时改变科学实验需由项目判断。一个卡对应一个实验、所有卡共同训练一个实验、空闲卡辅助推理各有适用条件。增加卡数不会自动合并显存，显存利用和吞吐需要实际模型与通信测试。

### 8.2 数据与模型较大时的上传方法

代码 ZIP 有明确文件数和体积限制；数据和模型另走传输路线：

| 条件 | 可采用的办法 | 验收 |
|---|---|---|
| 页面允许且文件规模合适 | 平台数据集或存储页面上传，再为 Notebook/训练配置访问 | 核对平台记录及实际挂载文件 |
| SSH 已可用且直传适合 | `upload` 单文件，显式设置所需 `--max-bytes` 和超时 | 本地预期SHA与远端回读一致 |
| 无SSH、浏览器不适合大文件 | 当前平台支持的对象存储客户端或数据导入方式 | 确认上传对象、平台导入/挂载、容器可读 |

完整参数和条件见 [数据传输指南](../skills/modelmate-ops/references/data-transfer.md)。只有当前平台明确提供兼容 S3 的端点时，才使用相应 S3 客户端配置。对象地址不能直接当 Linux 目录；没有挂载时，按平台认可的导入方式把对象读到实际路径。训练作业管理凭据与对象存储凭据也不是同一类权限。

从本机大文件开始的验收顺序为：记录大小和摘要 → 传输完成 → 核对远端实际文件 → 确认训练容器可读 → 把实际路径写入配置 → 小样本读取。下载模型时同时记录来源与版本；既有资产复用也要核身份，避免重复传输和误用。

### 8.3 修改、复用与恢复

保留代码包、版本号、配置摘要和部署目录。代码修补前确认当前文件符合预期版本，限定修改范围，保留备份或Git差异，再做相关测试。已提交作业使用的是哪份源码，要从本次启动日志与快照核实。

复用历史数据或结果时，登记来源和兼容条件；恢复训练时明确给出运行ID和检查点。代码快照、数据挂载与输出共享目录的语义可能不同：修改 Notebook 文件不一定更新快照，而修改共享数据可能立即影响活跃训练。操作前辨明本次任务实际读取的位置。

研究项目的分析包通常至少保留：最终解析配置、源码/数据身份、训练与评估汇总、必要的逐样本输出、阶段日志、运行成本和失败恢复记录。多百万文件缓存应通过索引选择必要记录或生成统计，不在导出时遍历整个缓存树。

## 9. 常见问题：先定位阶段，再修复

| 现象 | 先检查什么 | 处理方式 |
|---|---|---|
| Python 找不到脚本 | 当前执行位置和完整路径 | 本机用已记录的脚本绝对路径；远端先确认 `pwd -P` |
| 粘贴后 Shift+Enter 无反应 | 是否在 Terminal | Terminal 用 Enter；Notebook 单元用 Shift+Enter |
| 网页正常、SSH超时 | SSH地址端口、Notebook状态、网络/VPN | 检查TCP可达性；仍不通时使用非SSH路线继续准备 |
| SSH握手成功但认证失败 | Linux用户名、密钥归档成员、解密口令 | 用 `whoami` 核用户，区分密钥口令与登录密码 |
| 主机指纹变化 | Notebook/网关是否重建 | 独立核实身份后新建相应profile，不跳过检查 |
| 普通SSH能跑简单命令，复杂引号失败 | 网关是否重解释exec参数 | 使用本工具固定的 `bash -s` 和命令文件 |
| 中文粘贴后Python报字符串未闭合 | 终端编码、传输时内容是否损坏 | 优先上传UTF-8/LF文件并验摘要，避免长脚本手工中转 |
| `Unknown option: --checkpoint_url` | 平台自动注入的存储参数 | 在业务入口显式兼容已知参数及空值，仍拒绝未知拼写 |
| `Unknown option: --CONFIG=...` | 配置参数大小写、等号、外层引号 | 在入口实现明确解析，CLI覆盖默认；不使用eval |
| 激活环境后模块找不到 | Python路径、源码根目录、导入位置 | 环境激活后重新设置并核对项目导入，不依赖提交终端目录 |
| Notebook成功、正式作业失败 | 镜像、Python、挂载、权限、源码快照 | 对比两处最终配置及启动日志，修正实际差异后新提交 |
| 多卡有显存但推进慢或有空卡 | 实际任务调度、阶段、batch与数据等待 | 检查进程/日志/吞吐，按项目优化；不能只数日志末尾几行 |
| 进度100%但作业未结束 | 是否还在验证、评估、保存或导出 | 用实际阶段与最终产物判断完成 |
| 导出文件过多、打包很慢 | 是否递归扫描缓存/中间文件 | 用显式文件表/项目exporter，固定文件和字节上限 |
| 下载包看不见 | 文件面板的真实根目录 | 把包生成到已确认可见目录，再刷新下载 |
| 工具因目标已存在而拒绝 | 是否误用旧版本名 | 换新名字或核对既有完成件；不要随手删除原结果 |

更多参数级诊断见 [故障说明](../skills/modelmate-ops/references/troubleshooting.md)。报错时记录执行位置、命令、退出码和最小必要日志，私钥、口令、Cookie与真实连接配置留在本机。

## 10. 验证范围与交付记录

本版本包含37项离线测试，覆盖连接初始化、主机固定、加密密钥处理、命令传输、退出码、SFTP、摘要校验、拒绝覆盖、归档验证、安装备份、公开内容检查、示例参数解析和训练。测试不需要真实平台凭据。

另在实际 Notebook 上验证过 SSH 登录与SFTP、代码部署、配置修改与测试、数据准备、CPU小训练、显式结果归档和校验下载。200步示例的均方误差从约3.345降至约6.04×10^-26，参数接近3与-0.5；这证明该小训练链路能够工作，不提供NPU吞吐或大型训练的结论。

正式训练通过页面创建的方式来自平台公开流程与实际操作约定。本仓库的自动化工具不声称已提供平台作业管理API。具体页面提交、资源配额和训练容器挂载需要在读者自己的实例上验收。GitHub Actions运行状态可在仓库 **Actions** 页面查看，CI只验证离线代码与文档。

建议为每次真实部署保存下面这份记录。内容留在项目私有工作区，不把真实连接凭据提交到公开仓库。

| 记录项 | 应保存的内容 |
|---|---|
| 源码 | commit/发布版本、代码包SHA256、部署目录 |
| 运行 | 平台作业/批次ID、入口、镜像、资源、最终解析配置 |
| 资产 | 模型/数据来源、版本、实际读取路径及必要摘要 |
| 证据 | 阶段日志、完成标志、结果列表、运行耗时与设备证据 |
| 回收 | 结果包SHA256、本地保存位置、分析与备份状态 |

到这里，一次部署的闭环是：同一版本源码经过测试，在页面创建了可识别的正式作业，输出保存到确认的持久化位置，必要结果按清单导出，并在本机通过摘要核对。后续升级按新的源码版本重复相关步骤，历史运行与结果继续保留。

## 参考与进一步阅读

- [ModelMate Ops README](../README.md)：安装与skill调用入口。
- [SSH指南](../skills/modelmate-ops/references/ssh.md)、[非SSH指南](../skills/modelmate-ops/references/non-ssh.md)、[共用工作流](../skills/modelmate-ops/references/workflow.md)：具体参数与按需操作。
- [来源与验证范围](../skills/modelmate-ops/references/sources.md)：平台公开入门资料、SSH/Paramiko/Python文档和适用边界。
- [东南大学网络与信息中心公开操作指南](https://nic.seu.edu.cn/fwzn/gcslfw/czzn_ksrm.htm)：Notebook、训练页面与存储操作的公开实例，配额和镜像以各自平台为准。
- [GitHub仓库与问题反馈](https://github.com/ligoldfish/modelmate-ops)：代码、版本和维护记录。
