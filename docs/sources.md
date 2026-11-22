# 设计参考与开源/公开资料（2026-11 核查）

这份项目的业务假设、界面与代码由本项目独立编写，没有从以下项目直接复制代码。引用标准用于**设计参考**，不是声称获得合规认证或被相关机构认可。

1. **OWASP Application Security Verification Standard (ASVS) v5.0** — 验证用户认证、会话与功能授权的安全要求。https://asvs.owasp.org/
2. **OWASP API Security Top 10 (2023)** — API1 Broken Object Level Authorization、API5 Broken Function Level Authorization，指导每个请求检查所属项目和功能角色。https://owasp.org/projects/api-security-project
3. **OWASP Session Management Cheat Sheet** — 会话ID不可预测、HttpOnly/Secure/SameSite等指导。https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html
4. **OWASP CSRF Prevention Cheat Sheet** — cookie身份认证下的CSRF风险控制。https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html
5. **OWASP WSTG: CSV Injection** — 导出用户可控文本到Excel/CSV存在公式注入风险。https://wstg.owasp.org/latest/4-Web_Application_Security_Testing/07-Injection/20-CSV_Injection/
6. **ISO/IEC 25010:2023** — 质量模型参考；正式标准全文可能需要授权，不复制商业受版权保护的条文。https://www.iso.org/standard/78176.html
7. **W3C WCAG 2.2** — 界面可访问性参考。https://www.w3.org/TR/WCAG22/
8. **FastAPI official testing documentation** — 使用TestClient进行可复现API验证。https://fastapi.tiangolo.com/tutorial/testing/
9. **SQLAlchemy 2.0 docs** — 数据模型、关系型数据库与session生命周期。https://docs.sqlalchemy.org/en/20/
10. **PostgreSQL row security documentation** — 未来启用数据库层行权限控制时参考；当前代码尚未实现RLS。https://www.postgresql.org/docs/current/ddl-rowsecurity.html

公开规范或技术框架的采用，并不等同于拿到ISO、OWASP或医院监管体系认证。所有生产上线条件需由真实业务/安全责任人确认。
11. **《医疗卫生机构网络安全管理办法》（国卫规划发〔2022〕29号）** — 医疗机构网络与数据安全治理背景；本演示不构成制度合规评价。https://app.www.gov.cn/govdata/gov/202208/31/488953/article.html
12. **《中华人民共和国个人信息保护法》第二十八条** — 医疗健康属于敏感个人信息范畴；因此本项目严格使用模拟机构数据。https://www.samr.gov.cn/zw/zfxxgk/fdzdgknr/bgt/art/2023/art_f374e8245320413181742e6d1baf4366.html
13. **GB/T 22239-2019 网络安全等级保护基本要求** — 用于正式信息系统上线前的安全治理参考；本产品没有进行等保测评。https://openstd.samr.gov.cn/bzgk/std/newGbInfo?hcno=BAFB47E8874764186BDB7865E8344DAF
