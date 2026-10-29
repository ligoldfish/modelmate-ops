# ModelMate Ops

一个面向 **ModelMate / NAIE 平台零基础使用者**的 Codex skill。助手优先通过 SSH 准备数据、部署和修改代码、执行测试、监控与取回结果；没有 SSH 时，可完整使用 JupyterLab 文件面板与网页 Terminal。

正式训练采用平台页面创建，再接回日志和结果。你只需说明项目目标，不必先掌握平台术语或手动配置一长串环境变量。

本机数据很大、网页传不上去时，按[数据上传路线](skills/modelmate-ops/references/data-transfer.md)选择平台数据集、SFTP或平台支持的存储客户端；无需为了传大数据先开通SSH。

这是独立社区工具，不是华为官方客户端。不同部署的菜单、挂载、资源和网络有所不同，skill 会根据当前实例核实，不绑定某个学校、账号、模型或实验项目。

第一次使用平台，建议直接按[全流程部署操作报告](docs/DEPLOYMENT_REPORT_CN.md)完成一次练习：报告将 SSH 和无 SSH 两条路线分别串成完整操作，提供每步执行位置、可运行命令与成功标志。[发布页](https://github.com/ligoldfish/modelmate-ops/releases)同时提供 PDF 阅读版和完整包。

## 你将走完的流程

```text
登录平台并选择工作空间
    ↓
创建或复用 Notebook
    ↓
优先 SSH ────────── 无 SSH：JupyterLab + Terminal
    ↓                         ↓
准备数据 → 部署代码 → 修改与测试 → 确认默认配置
    ↓
平台页面创建训练作业
    ↓
检查启动 → 固定日志与输出 → 监控/排障 → 打包下载
```

## 安装

需要 Python **3.10 或更新版本**。把仓库下载并解压，或克隆到本机后，进入仓库根目录，运行：

```powershell
python scripts/install_skill.py
```

默认安装到 Codex 的用户 skills 目录；已有同名版本先完整备份，个人 SSH profile 不受影响。脚本会打印实际安装和备份位置。自定义安装目录见 `python scripts/install_skill.py --help`。

**使用 SSH 才需要**安装本机连接依赖：

```powershell
python -m pip install -r skills/modelmate-ops/requirements-ssh.txt
```

这不会安装或更改远端训练环境。非 SSH 路线、归档工具和示例训练只依赖 Python 标准库。

重新打开一个 Codex session 后，直接说：

```text
请使用 $modelmate-ops。我的平台已登录，项目代码在本机，请从头帮我部署。
优先使用 SSH；正式训练提交前给出实际源码、入口、资源和输出配置。
```

平台入口和项目代码路径换成你自己的实际信息。助手会先利用现有上下文，再只询问缺少的信息。

## 路线 A：优先 SSH

准备运行中的 Notebook、详情页显示的 SSH 地址/端口/用户名，以及平台凭据在**本机的路径**。有些部署提供含加密私钥和口令的 tar 包；不要将包或口令贴到聊天、提交到 Git。

```text
请使用 $modelmate-ops。Notebook 已运行，有 SSH 地址和凭据文件。
请建立本机连接配置，验证远端身份和文件传输，再部署我的项目。
```

首次连接工具支持 `init`，不要求预先创建 JSON。此后自动读取本机 profile。主机指纹固定后发生变化会停止操作；首次信任来源会被记录。实际命令、网络诊断与密钥格式见 [SSH 指南](skills/modelmate-ops/references/ssh.md)。

## 路线 B：不用 SSH

```text
请使用 $modelmate-ops。我只能打开平台和 JupyterLab，没有 SSH。
请带我通过文件面板和 Terminal 完成上传、部署、修改、测试、页面提交与结果下载。
```

助手有浏览器控制能力时可以协助页面操作；没有时提供对应页面的明确动作、可粘贴命令和成功标志。JupyterLab **Terminal 使用普通 Enter**；Shift+Enter 用于 Notebook 代码单元。完整步骤见 [非 SSH 指南](skills/modelmate-ops/references/non-ssh.md)。

## 没有项目，先练习一次

skill 中的 [starter](skills/modelmate-ops/assets/starter) 是纯标准库小型线性回归示例：生成64条数据、执行200步真实优化、记录日志与结果，不下载模型。复制到独立目录：

```powershell
python -c "import shutil; shutil.copytree('skills/modelmate-ops/assets/starter', 'demo-project', ignore=shutil.ignore_patterns('__pycache__'))"
python demo-project/main.py --check
python demo-project/main.py
```

这先验证本地示例。再让助手走一次 SSH 或非 SSH 部署。正式提交前，助手应把示例配置中的输出目录改为该平台**已确认可写的持久化目录**；默认相对 `outputs` 适合本地/Notebook 练习，不作为正式作业的可靠输出位置。无需填网页环境变量。

已有项目直接使用自己的入口与依赖；示例不是所有部署的强制前置步骤。

## 提交训练与回收结果

两条路线都遵循 [共用工作流](skills/modelmate-ops/references/workflow.md)。SSH 登录 Notebook 不等于获得平台作业管理接口；默认由平台页面创建正式作业。若你的版本确有官方管理 API，可另行核验，工具不会猜测接口或套用存储密钥。

助手会准备可直接照填的提交表，记录平台生成的批次 ID，然后监控该次运行。结果按明确索引导出，排除权重不等于扫描剩余全部文件，下载后核对 SHA256。

## 仓库结构

```text
skills/modelmate-ops/
  SKILL.md               给 Codex 的任务入口
  agents/openai.yaml     skill 展示信息
  references/            SSH、非SSH、共用流程、故障与来源
  scripts/               SSH连接与受限归档工具
  assets/starter/        可部署的最小训练例子
scripts/                 本机安装与公开内容检查
tests/                   无平台凭据的离线测试
.github/workflows/       Linux/Windows CI 配置
```

## 验证与维护

```powershell
python -m unittest discover -s tests -v
python scripts/check_public_release.py
```

测试使用临时文件和模拟连接，不需要平台账号，也不会创建训练作业。CI 验证代码与文档完整性，不验证真实 NPU 性能。匿名实践中已验证 SSH 命令、文件传输、部署、修改测试、Notebook CPU训练与结果回收；正式作业的页面创建按当前部署核对。

提交问题时给出操作系统、Python/客户端版本、执行位置、阶段、退出码及脱敏后的最小日志。不要上传私钥、口令、真实 profile、Cookie、token 或完整认证日志。公开资料与验证边界见 [sources.md](skills/modelmate-ops/references/sources.md)。

代码采用 [MIT License](LICENSE)。
