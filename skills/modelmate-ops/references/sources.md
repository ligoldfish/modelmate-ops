# 来源与验证范围

这是独立维护的社区 skill。平台菜单、配额、镜像、挂载与 SSH 网关实现依部署版本而变化；本工具没有绑定任何个人账号、内网地址或平台管理凭据。

## 一手资料

- [东南大学网络与信息中心：操作指南/快速入门](https://nic.seu.edu.cn/fwzn/gcslfw/czzn_ksrm.htm)：公开的 ModelMate Notebook、页面训练、存储与远程开发流程示例。它的历史配额和镜像表不作为所有部署的默认值。
- [OpenSSH ssh_config](https://man.openbsd.org/ssh_config)：连接超时、保活、主机身份、配置与跳板规则。
- [Microsoft：Windows OpenSSH 密钥管理](https://learn.microsoft.com/en-us/windows-server/administration/openssh/openssh_keymanagement)：私钥、口令和客户端使用。
- [Win32-OpenSSH：文件权限](https://github.com/PowerShell/Win32-OpenSSH/wiki/Security-protection-of-various-files-in-win32-openssh)：Windows ACL 与用户私钥。
- [Paramiko 客户端 API](https://docs.paramiko.org/en/stable/api/client.html) 与 [Transport API](https://docs.paramiko.org/en/stable/api/transport.html)：SSH通道、公钥认证与远程命令。
- [Python zipfile](https://docs.python.org/3/library/zipfile.html)：归档格式与文件处理。这里的受限部署工具另行实施清单、路径与大小验证。
- [AWS CLI命名profile](https://docs.aws.amazon.com/cli/latest/userguide/cli-configure-files.html) 与 [S3文件复制](https://docs.aws.amazon.com/cli/latest/reference/s3/cp.html)：仅供当前部署确认兼容S3时的本机大文件上传路线，不将AWS认证或接口套到所有ModelMate后端。
- [MoXing官方文件API](https://github.com/huaweicloud/ModelArts-Lab/blob/master/docs/moxing_api_doc/MoXing_API_File.md)：仅在当前部署已提供SDK和对象访问时，把对象存储文件导入实际持久化目录；不据此假定所有实例都已配置。

当前实例若提供内置帮助，优先核对“创建 Notebook”“开启节点 SSH 远程登录”“创建训练作业”“获取访问密钥”等条目。公开仓库不保存内网文档镜像，也不复制厂商 SDK 源码。

2026-10-31 核验的部署内置帮助还有两项直接影响排障：“调试Notebook”（文档标识 `zh-cn_topic_0000001808736654`）要求从 Notebook 创建训练时，工作目录不能创建或使用文件、目录软链接；“查看训练作业”（`zh-cn_topic_0000001808576826`）提供批次系统日志 `submit.log` 的查看入口。通过当前部署自己的帮助菜单核对，文档标识与菜单可能随版本变化；不公开内网主机或假定日志的固定存储路径。

华为云 ModelArts 与私有部署 ModelMate 并非同一个接口合同。相关云文档可帮助理解概念，但不据此套用用户名、API路由、凭据或环境变量。

## 已验证和待现场验证

| 层次 | 范围 |
|---|---|
| 离线测试 | 本机临时文件、合成密钥和模拟SSH；profile初始化、主机固定、命令输入、退出码、传输、归档、示例解析与训练 |
| 匿名SSH实践 | Notebook认证、命令、SFTP、数据准备、部署、带版本校验的修改、测试、CPU小训练与结果回传 |
| 网关兼容实践 | 一种Apache SSHD网关会重新解释exec引号；通过固定bash-s请求和stdin传UTF-8脚本解决，未推广为所有服务器行为 |
| 平台页面 | 创建正式作业的公开流程与实际部署约定；每次仍核真实资源、批次及状态 |
| 匿名提交失败取证 | 两次零秒失败的实际作业快照均停止于 pytest 目录链接之前；结合内置约束定位复制阻断。已验收备份、限定移除及源端文件/云对象身份，未包含修复后正式重提成功的证据；详见 [案例与排障步骤](submission-failures.md) |
| 未由CI验证 | 私有平台登录、真实资源配额、正式作业创建、NPU正确性/吞吐、多卡训练、所有网关版本 |

CI文件配置了Linux/Windows多版本Python检查；配置存在不等于已经在GitHub运行通过。公开测试不需要真实凭据，也不访问远端平台。

项目自己的科学有效性、数据划分与预算不由通用部署工具决定。报告时分别列出本地测试、远端Notebook、正式作业与NPU执行证据。
