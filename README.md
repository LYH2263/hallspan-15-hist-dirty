# HallSpan 考场间距排座

在考室网格上按最小曼哈顿距离排座，同试卷套不得四邻相邻，并输出违规与统计。

技术栈：Python 3.12 / FastAPI / SQLAlchemy / PostgreSQL / Vue 3 / TypeScript / Vite

## 启动

```bash
docker compose up --build
```

| 服务 | 地址 |
| --- | --- |
| 前端 | http://localhost:4900 |
| API | http://localhost:9900 |
| API 文档 | http://localhost:9900/docs |
| Postgres | localhost:5450 |

健康检查：`GET http://localhost:9900/api/health`

## 使用说明

1. 在「考室」设置现网约束（最小曼哈顿距离、点击格位切换禁坐），在「考生名册」可调整现行套别。
2. 在「排座图」点「按现网约束重新排座」生成**新方案**；历史方案下拉可回看每一版。
3. **历史方案只读、不可变**：座位与违规钉死在生成当时，并随方案保存约束快照（最小距/禁坐）。
   后来修改最小距、禁坐或套别，不会重排历史，只会在历史视图上亮**琥珀色漂移标记**（「只标不修」）。
4. 想消除漂移：按现网约束重新排一张**新图**（INSERT 新方案），旧方案原样保留，两套数字分岔同时成立。
5. 「违规」页分区展示：红色＝冻结违规（历史原文），琥珀色＝现网漂移（实时标记，不入库）。

### 关键接口

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/api/seating/run` | 按现网约束排新方案（只 INSERT，绝不改历史） |
| GET | `/api/seating/plans` | 历史方案列表 |
| GET | `/api/seating/plan/{id}` | 历史详情：冻结座位/违规 + 实时 `drift` 漂移标记 |
| GET | `/api/seating/violations?plan_id=` | 冻结违规与漂移分两节返回 |
| PATCH | `/api/halls/{id}` | 改现网最小距 / 禁坐格 |
| PATCH | `/api/candidates/{id}` | 改现行套别 |

## 开发与测试

```bash
docker compose exec api pytest -q
```
