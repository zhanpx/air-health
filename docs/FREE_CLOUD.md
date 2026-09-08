# 没有服务器：免费云与低成本部署

核对日期：2026-09-08。只提供教程，未代为开通 Billing、创建云资源或接受任何付费承诺。

[返回 README](../README.md) · [完整教程](TUTORIAL.md)

## 没有服务器？先选免费或低成本方案

免费额度是有条件的资源优惠，不是无限使用、永不停机或永不收费的承诺。

| 方案 | 适合什么 | 先看限制 |
| --- | --- | --- |
| Google Cloud Free Tier | 学习 Linux 部署、个人低流量看板；下面给出配置主线 | 合资格 e2-micro 与标准磁盘有额度；IP、流量等仍可能收费。[Google Cloud：免费计划与试用](https://docs.cloud.google.com/free/docs/free-cloud-features)[Google Cloud：网络与 IP 定价](https://cloud.google.com/vpc/network-pricing) |
| Oracle Always Free | 申请成功且有容量时，可考虑兼容的个人服务 | 主区域、机型、资源总额与空闲回收；Arm 还需核对 CLI 架构。[Oracle Cloud：Always Free](https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier_topic-Always_Free_Resources.htm) |
| 旧电脑 / Linux 小主机 | 已有设备，希望优先本地保存数据 | 不用另买云主机，但有电费、网络、持续开机和异地备份成本。 |
| 临时试用 / 免费托管平台 | 短期学习和演示 | 先看是否休眠、是否有持久磁盘；不是所有平台都支持 systemd 与 SQLite 常驻写入。 |

### Google 的两种“免费”不是一回事

**Free Trial：** 符合资格的新用户试用，当前为 90 天、300 美元额度；需要验证身份和有效支付方式。试用结束前未升级，相关资源会停止。
**Free Tier：** 特定产品的月度用量额度，需要有效 Billing 账号。付费账号超额会计费；计划目前没有固定结束日期，但 Google 可以调整规则。[Google Cloud：免费计划与试用](https://docs.cloud.google.com/free/docs/free-cloud-features)

### 推荐学习顺序

先完成小范围数据同步和网页查看，再开启大量原始记录回填、定时备份和 AI。对预算极其敏感、不能接受任何云端附加费用的读者，优先考虑已有 Linux 设备；不要把“有免费实例”理解为整套架构保证 0 元。

> 用户提供的知乎文章作为选题线索：本次访问返回 403，未能核验正文，不转述其中步骤或把它作为价格依据。文末保留该链接，实际配置以官方控制台与定价为准。

## Google 免费额度虚拟机：配置步骤

这一步只创建自己的服务器；后面的 Google Health OAuth 仍需用户授权。[Google Cloud：免费计划与试用](https://docs.cloud.google.com/free/docs/free-cloud-features)[Google Cloud：创建虚拟机](https://docs.cloud.google.com/compute/docs/instances/create-start-instance)

1. 在自己的 Google Cloud 账号创建专用项目并关联有效 Billing。先区分试用账号和已升级付费账号，再启用 Compute Engine API。可与 Health API 使用同一项目，便于学习；服务账号身份不能代替个人健康数据 OAuth。

2. 进入 Compute Engine → VM instances → Create instance。不要直接接受默认机型与默认磁盘，按下表逐项检查，再查看创建页的价格估算。

| 设置 | 免费额度主线配置 |
| --- | --- |
| 区域 | us-west1（Oregon）、us-central1（Iowa）或 us-east1（South Carolina）三选一；不是所有美国区，也不是香港/新加坡区。 |
| 机型 / 供应模式 | E2 → e2-micro；标准、非抢占式实例。不要误选 e2-small、e2-medium 或 Spot。 |
| 实例时长 | 按 Billing 账号合并 eligible 实例使用时长，每月额度相当于一台持续运行；不是每个项目各送一台。 |
| 系统与磁盘 | 选择无额外许可费的 Ubuntu / Debian 镜像；Standard persistent disk（pd-standard）。合计额度 30 GB-month，注意不是 Balanced、SSD 或 Hyperdisk。 |
| 网络与防火墙 | 先阅读下一页再决定公网 IP。SSH 仅允许可信来源或受控访问；不要开放 8765 / 8766，不必为 Cloudflare 出站隧道开放网页入站端口。 |

3. 创建前检查地区、机型、磁盘类型、额外数据盘、快照计划、IP 和网络价格。估算显示目录价不等于最终账单，也不能仅凭预计折扣认为所有项目免费；创建后在 Billing Reports 查看 SKU 与抵扣。

4. 创建成功后，通过控制台 SSH 或自己已验证的 SSH 密钥登录，执行前文基础环境检查。将后面命令中的 health-server 替换成自己的 SSH 别名，继续“Google Cloud：创建正确的项目”和基础安装步骤。

> 教程没有替读者开通 Billing 或创建资源。请自行核对资格、支付验证和创建页信息；不要购买共享云账号，不要在教程评论中提供银行卡、账号或 SSH 私钥。

## 免费算力之外：IP、联网与防扣费

### 最容易遗漏：公网 IPv4

标准 VM 的在用静态或临时公网 IPv4 当前标价为每小时 0.005 美元，月度免费仅 1 小时。按 730 小时估算，仅这一个 IP 约 3.65 美元/月，尚未计其他项目。停止 VM 不一定释放静态 IP，闲置预留地址也可能继续收费。[Google Cloud：网络与 IP 定价](https://cloud.google.com/vpc/network-pricing)

| 联网方案 | 权衡 |
| --- | --- |
| 公网 IPv4 + SSH + HTTPS 隧道 | 容易理解，但属于“免费算力 + 可能收费网络”，不能写成永久免费服务器。 |
| 不分配公网 IPv4，使用可用 IPv6 | IPv6 地址本身当前不收费，但需验证 DNS、软件源、Google OAuth/Health、模型服务与 cloudflared 的全链路 IPv6 能力。不能保证原教程零改动可运行。 |
| 私有 VM + Cloud NAT / 中转 | 能解决某些出站需求，但 NAT、IP、中转机与流量可能另外收费。SSH/IAP 的入站能力不等于通用互联网出站能力。 |

### 磁盘、流量与 AI 也要分别算

检查持久磁盘、额外磁盘、快照、日志、出口流量、DNS 和备份存储。Compute Engine 免费计划列出的出口额度为每月 1 GB，从北美到目的地区域不含中国和澳大利亚；实际还要按所选网络层级与目的地核算。Cloudflare 隧道不会自动免除 Google 出口费用。AI 账号费用另算。[Google Cloud：免费计划与试用](https://docs.cloud.google.com/free/docs/free-cloud-features)[Google Cloud：网络与 IP 定价](https://cloud.google.com/vpc/network-pricing)

### 开通后立刻设置成本观察

创建小额月度预算，例如 5 美元，并启用 50%、90%、100% 邮件提醒；前几天按服务/SKU查看计费。**普通 Alerts-only 预算不会自动封顶**。预览版 spend cap 仅覆盖特定 API 服务且存在延迟，不会停止持续的计算或存储计费，不能替 VM 保证零账单。[Google Cloud：预算与提醒](https://docs.cloud.google.com/billing/docs/how-to/budgets)[Google Cloud：Spend cap budgets](https://docs.cloud.google.com/billing/docs/how-to/budgets-spend-caps)

> 不再使用时，先备份并确认恢复方案，再逐项检查实例、保留磁盘、快照、预留 IP、NAT 与其他资源。只关机不是“清零费用”。不要把自动停机作为健康数据可靠性的唯一保障。

## 小规格运行策略与其他免费选项

### e2-micro 先跑基础功能

官方规格为约 1 GB 内存、共享 CPU；2 个可见 vCPU 不等于 2 个持续满速核心。[Google Cloud：E2 机型规格](https://docs.cloud.google.com/compute/docs/general-purpose-machines#e2_shared-core) 以下是针对本项目的工程建议，不是性能实测或云厂商保证：

| 阶段 | 建议 |
| --- | --- |
| 首次部署 | 先回填 7 至 30 天，验证步数、睡眠和少量运动；不要首次就并发回填多年逐点心率。 |
| 日常运行 | 保留单一同步任务入口；同一时刻只做一种重任务，错开回填、备份和 AI。 |
| AI 分析 | 本项目调用远端模型，不在 VM 上部署大模型。CLI 本身也占内存；先关闭定时 AI，测试后再启用。 |
| 磁盘与保留 | 按需保留高频原始数据、限制日志与备份份数；注意备份副本会与原数据竞争 30 GB 磁盘。 |
| 稳定性 | 出现 OOM、延迟或磁盘不足，先减少任务和范围；必要时升级或迁移，不能为了“免费”牺牲数据可靠性。 |

Linux：检查内存、磁盘以及内核 OOM 等事件

```bash
free -h
df -h /var/lib/air-health
sudo journalctl -k -n 100 --no-pager
```

### Oracle Always Free：备选，不承诺能申请到

当前官方列有最多两台 AMD Micro，或共享额度内的 Arm A1 计算资源；A1 页面所列额度相当于 2 OCPU / 12 GB，并有合计块存储额度。创建须在主区域，容量可能不足，空闲实例可能被回收。不要直接沿用旧文章的更大配额，也不要制造虚假负载规避回收。[Oracle Cloud：Always Free](https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier_topic-Always_Free_Resources.htm)

Arm 方案先验证 Python、Codex CLI 和 cloudflared 的对应架构支持；保留异地加密备份。Cloud Shell 适合配置操作，不应当作常驻服务器；Cloud Run 等服务则需重新设计持久存储与定时任务，不能原样复制 systemd 教程。

> 选定服务器后，后续数据权限、OAuth、私有存储与登录保护完全不变。“免费”不能降低健康数据保护标准。

## 用户提供的参考文章

https://zhuanlan.zhihu.com/p/1977711962109538485

本次返回 403，未能核验正文；未据此转述配置或价格。免费额度和计费以正文所链官方说明及读者实际账号为准。
