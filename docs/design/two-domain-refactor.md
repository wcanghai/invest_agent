# 双业务域架构设计

`daily_report` 使用分层结构：`data_sources` 只采集和标准化，`storage` 独占 SQLite，`rendering` 只生成 Markdown，`service` 负责编排，`web` 只提供 HTTP 和页面。日报库以复合主键保证行情、新闻幂等，以报告日期主键保证当天第一份成功报告永久复用。

`tdx_data` 使用 `client → archive_service → repository` 单向依赖。额外接口保存在 `additional_data.py`，只展示或返回数据，不写数据库。TDX 库与日报库分离，防止大规模归档事务影响日报读取。

网络和本地 TQ 访问集中在数据源/客户端函数；业务服务可通过 callable、factory 或测试替换进行离线验证。
