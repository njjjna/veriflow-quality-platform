# VeriFlow v0.3.4 — 云端浏览器UAT验证版

真实Chromium页面操作已完成，所有数据和账号均为模拟内容。工程保持私有，应用没有部署公网。

## 验证结果

| 检查 | 结果 |
| --- | --- |
| 后端授权、业务和附件回归 | 20/20通过 |
| HTTP多角色流程 | 15/15通过 |
| 页面审批提交处理回归 | 2/2通过 |
| 真实Chromium页面验收 | 23/23通过 |
| HTTP资源/匿名权限 | 5项通过 |
| JS语法 | 通过 |

首次云端通过记录：[Chromium UAT](https://github.com/njjjna/veriflow-quality-platform/actions/runs/45013807096)，[同提交回归](https://github.com/njjjna/veriflow-quality-platform/actions/runs/45013807061)。本正式Release由独立发布工作流在最终源码复测通过后创建，准确提交及复测链接见文末与 `RELEASE_PROVENANCE.json`。

## 页面验收范围

管理员与五种业务角色独立会话、首次改密、只读入口、12行/3异常检查、工单去重、创建与分配高风险工单、证据上传及授权预览、整改与独立复测、自复测拒绝、CSV下载、8项UAT双人验收、异常数据门禁、合格数据解除门禁、经理提交与独立审批、审计日志、390px总览、退出和JS异常检查。

## 本版修复

- v0.3.3发布后视觉复核发现页脚残留v0.3.2。v0.3.4改为从后端健康接口读取版本，并在浏览器第一项检查中断言页脚与后端版本一致。

- 修复上线表单把属性选择器传入 `getElementById` 导致提交异常。
- API和浏览器套件分别使用独立临时数据库与附件目录。
- 补齐图片测试依赖；浏览器导航等待准确页面标题。
- 在仓库和Release持久归档模拟截图、CSV、报告、日志、源码校验清单与提交来源。

## 附件

- `VeriFlow_v0.3.4_source_and_evidence.zip`：准确发布提交的源码和已验证证据。
- `VeriFlow_v0.3.4_browser_UAT_evidence.zip`：浏览器截图、CSV、API与浏览器结果、回归日志。
- `RELEASE_PROVENANCE.json`：实际受测源码提交、工作流和证据归档提交。
- `VeriFlow_v0.3.4_release_report.md`：本报告及发布来源。
- `SHA256SUMS_release.txt`：上述四个文件的校验值。

原生另存为弹窗、其他浏览器、完整可访问性、Docker/PostgreSQL仍未在本轮验收。29项最终使用者人工签署清单与自动化23项检查分别记录。本版本的“流程批准”不表示真实安全、回滚或备份演练已完成。
