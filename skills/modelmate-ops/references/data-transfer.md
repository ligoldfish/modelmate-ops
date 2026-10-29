# 数据和模型文件：从本机送到训练可见的位置

代码包与大资产分别处理。先确认文件体积、来源、目标数据集/课题和训练实际读取方式；不要把几十GB数据塞入代码ZIP，也不用代码工具的大小上限判断平台是否支持上传。

## 选择路径

| 条件 | 路线 |
|---|---|
| 已在平台存储且当前用户可读 | 复用真实路径，检查身份与格式，不重复上传 |
| 平台数据集页面支持当前体积 | 在页面创建/选择数据集并上传；无需SSH或额外客户端 |
| 有SSH、单个文件适合SFTP | 上传到已确认的持久化目录，按体积调整工具上限 |
| 超过网页限制、文件多或需分片重试 | 使用该平台支持的对象存储客户端；它与是否有SSH无关 |
| 当前没有授权的上传通道 | 请管理员提供本课题的可用上传方式或已预置路径，继续准备代码；不虚构上传成功 |

网页大小限制、目录配额和可见挂载因部署不同，先看该页面/帮助提示；不硬写统一5GB或30GB。

## A. 只用平台页面上传

1. 在正确工作空间进入“数据管理 → 数据集”或当前部署的等价页面。
2. 创建新的数据集或进入用户已授权的数据集；选择实际数据类型和来源，不为了能上传就随意改变标签或任务类型。
3. 查看文件大小/格式限制，使用“上传/导入”选择本机文件，等待服务端处理完成。页面的浏览器传输进度不等于数据集已经就绪。
4. 在详情记录数据集ID、版本、目录或对象前缀。若平台给出训练可用路径，以它为准；否则根据当前部署帮助和Notebook挂载核对映射。
5. 在Notebook Terminal检查准确位置，核对文件名、大小和格式；正式训练使用的是这份文件，而不是本机路径。

若单文件超限，先走B，不反复上传试探，也不默认把巨大数据拆到代码工作区。已有项目确实使用分片数据时，按其格式与索引进行合法分片。

## B. 无SSH也能用对象存储客户端

先取得本课题授权的存储连接信息；这些**不是训练作业管理凭据**：

| 字段 | 来源 |
|---|---|
| 客户端与协议 | 当前平台帮助或管理员指定，可能是厂商工具或兼容S3的客户端 |
| Endpoint与TLS/区域要求 | 存储连接配置，不能用ModelMate网页地址替代 |
| Bucket和目标前缀 | 数据集详情、用户代码目录或管理员提供的授权范围 |
| 数据访问凭据 | 平台允许获取的存储配置/管理员授权文件，仅在本机客户端使用 |
| Notebook/DPC对应目录 | 平台详情和帮助，之后用小文件实证映射 |

不要向聊天粘贴AK/SK。助手可以使用用户明确提供的本机凭据路径；权限页面不可见时请求正确授权方式，不修改租户权限或重建管理员密钥。

图形客户端的通用步骤：

1. 从平台推荐或厂商官方渠道安装客户端，创建一个独立的本机连接配置。
2. 按部署说明填写协议、Endpoint、区域和凭据，在授权Bucket下进入**准确前缀**。
3. 先上传一个小型验证文件，在Notebook Terminal读取对应挂载位置，确认对象前缀映射正确。
4. 上传实际数据文件/目录，按客户端支持的分片、重试和进度操作；不要承诺所有客户端都支持跨会话续传。
5. 客户端完成后再做下文完整性检查。没有删除原件或全量同步清理的需求时，不使用带删除目标文件语义的同步选项。

### 平台确认兼容S3时的本机CLI例子

以下是 **本机 PowerShell**；只在该部署明确支持AWS CLI的S3协议时使用。安装指引见 [AWS CLI官方文档](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html)，其他平台可按同样字段使用其指定图形客户端。

```powershell
aws configure --profile modelmate-data
```

凭据在用户本机交互输入，区域和输出格式按平台配置；不覆盖其他AWS默认profile。若机构使用凭据文件或其他认证方式，按其文档导入，不把密钥放到命令行参数。然后：

```powershell
$MmEndpoint = Read-Host '平台提供的存储HTTPS Endpoint'
$MmBucket = Read-Host '授权Bucket名称'
$MmPrefix = Read-Host '数据集详情中确认的对象前缀，不含开头斜线'
$MmData = Read-Host '本机数据文件完整路径'
$MmObject = Read-Host '此次新对象文件名'
$MmTarget = 's3://' + $MmBucket + '/' + $MmPrefix.Trim('/') + '/' + $MmObject
aws --profile modelmate-data --endpoint-url $MmEndpoint s3 cp $MmData $MmTarget
```

目标名应是新的明确对象，避免覆盖现有数据。目录上传需要该客户端对应的递归选项及目标清单，由助手按实际格式准备。签名、区域、CA或路径寻址不兼容时回到该部署支持的客户端，不通过关闭TLS校验或更换随机Endpoint试探。

## C. SSH单文件上传

目标目录已经在持久化挂载中创建并验证时，可使用本机SSH工具：

```powershell
$MmData = Read-Host '本机数据文件完整路径'
$MmRemoteData = Read-Host '远端新文件绝对路径'
$MmDataBytes = (Get-Item -LiteralPath $MmData).Length
$MmDataSha = (Get-FileHash -LiteralPath $MmData -Algorithm SHA256).Hash
python -X utf8 $MmTool upload --local $MmData --remote $MmRemoteData --max-bytes $MmDataBytes --sha256 $MmDataSha --timeout 120
```

`$MmTool` 的定义见 [SSH指南](ssh.md)。默认2GiB上限可以显式调整到已知文件大小，远端文件名不允许覆盖。该工具会回读远端内容验证摘要，意味着额外网络读取；大量资产优先选适合分片传输的存储通道。传输失败的暂存文件保留，后续只核对这次准确文件，不清整个目录。

## 完整性与训练路径

### 对象存储已上传，但Notebook没有对应挂载

先区分“对象已经在桶里”与“Linux已有同一文件”。若数据集详情给出可直接访问的DPC路径，就核对该路径；没有挂载时，不能把 `s3://...` 生硬改成 `/opt/...`。

使用该部署提供的数据导入/挂载功能，或在Notebook Terminal用**已配置当前用户存储访问的官方SDK**下载到已确认的持久化目录。以下只适用于平台已提供并配置 MoXing 的实例，先检查依赖；其他版本按自己的SDK/导入文档，不盲目安装一套云端客户端：

```bash
python3 -c 'import importlib.util; print(importlib.util.find_spec("moxing") is not None)'
```

确认 MoXing 在当前实例可用且已获得相应对象访问后，在网页Terminal执行下面的单文件导入。两个路径由助手从本次数据集和挂载替换完整，不含口令：

```bash
python3 - <<'PY'
from pathlib import Path
import moxing as mox
source = 's3://BUCKET/CONFIRMED_PREFIX/DATA_FILE'
target = Path('/absolute/verified/persistent/directory/DATA_FILE')
if target.exists() or not target.parent.is_dir():
    raise RuntimeError('Use an existing verified parent and a new destination file')
mox.file.copy(source, str(target))
print(target)
PY
```

这是[官方文件API](https://github.com/huaweicloud/ModelArts-Lab/blob/master/docs/moxing_api_doc/MoXing_API_File.md)的条件式用法，不声称所有ModelMate都预配该SDK或凭据。若没有可用SDK/访问权限，使用平台的数据导入节点或请管理员预置到可读路径，不上传本机密钥到代码目录凑通。

另一些项目由正式训练入口读取平台 `data_url`，在启动时下载到作业缓存。此时配置应保留对象URI/数据集身份，并从正式作业日志验收下载与实际缓存路径；不能用忽略 `data_url` 的演示入口证明真实数据已经接入。

本机用 `Get-FileHash`（Windows）或 `sha256sum`（Linux）记录原文件摘要；在Notebook Terminal对映射后的**准确文件**运行：

```bash
read -r -p '训练将读取的数据绝对路径: ' MM_DATA_FILE
ls -lh -- "$MM_DATA_FILE"
sha256sum -- "$MM_DATA_FILE"
```

与本机摘要比对，再按文件格式流式检查行数/schema/少量样本。多文件数据用原有manifest或索引，不把数十GB文件整份读入内存。若需解压，确认目标是新目录、归档路径无越界、空间足够，并使用适合数据体积的工具；代码ZIP工具不是大数据解压器。

最后把确认后的真实路径写入项目配置，由助手核对读权限与训练容器挂载。成功标准是“目标训练能读取预期数据及身份”，不仅是客户端提示上传完成。
