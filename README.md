# 青岑板材质控 V1

领班用生产清册固定抽检范围，化验员交日班测量单，分析员按确切冻结修订签发初榜。工位领单后可在分析主机关库时登记开检。领班凭原榜号复核风险依据和工位进度。

## 运行

需要 Python 3.11，仅使用标准库。在项目根目录运行完整回归和演示。

```text
python3 -B check_project.py
python3 -B -m demo
```

`check_project.py` 由运行平台在导出时提供，它发现并运行 `tests` 包中的完整套件。演示从 `examples/day_shift.json` 读取日班数据，每次使用独立临时双库。程序打印实际风险、原名单和工位进度。

## 一班业务

1. 领班为 B 批登记依序 X、Y、Z 和两片复检限额，中心厚度基准为 10 mm，边缘偏移基准为 0 um。
2. 化验员以导入票交整张测量单。末行引用非法也会使整票拒收。
3. 分析员按确切读数修订冻结，保留复算所用的全部读数和缺测状态。
4. X、Y 风险均为 3/2 mm，Z 为 1 mm。清册顺序裁决同分，初榜选 X、Y，风险证据和首执随榜保存。
5. 工位领初榜并在分析库关闭后开检 X。重复提交同榜或重试同片时复用原身份。
6. 化验员按当前父修订更正 X、Z 的中心厚度并冻结新修订。分析员预览得到 Z、Y、X 的风险顺序。
7. 领班重开双库后仍可按原号领回原榜、首执及原风险证据。工位仍记录 X 已开检、Y 待检。

## Python 入口

每端的 `db` 参数使用本端 `open_*` 返回的 SQLite 连接。调用者负责关闭连接，可使用 `contextlib.closing`。请为两端使用不同的数据库路径。初始化可重复执行并保留业务数据。写入口自管事务，调用者在事务外调用。

| 模块 | 调用 | 结果 |
| --- | --- | --- |
| `reports.store` | `open_analysis(path)` | 初始化或重开分析库 |
| `lots.register` | `register_lot(db, batch_id, roster, gauges, limit)` | 固定 `Lot` |
| `measure.import_readings` | `record_readings(db, batch_id, ticket, rows)` | `ReadingRevision` |
| `measure.amend` | `amend_readings(db, batch_id, parent_id, rows)` | 更新当前指针后的新 `ReadingRevision` |
| `measure.freeze` | `freeze(db, batch_id, revision_id)` | 冻结号 |
| `measure.freeze` | `load_frozen_revision(db, freeze_id)` | 确切修订及读数快照 |
| `risk.ranking` | `preview_risk(db, freeze_id)` | 带冻结出处的完整 `RiskResult` |
| `reports.issue` | `issue_initial(db, batch_id, freeze_id)` | 含 `report_id` 的 `InitialReceipt` |
| `reports.read` | `read_initial(db, report_id)` | 固定 `InitialReport` |
| `reports.export` | `export_initial(db, report_id)` | V1 `InitialPacket` |
| `station.ledger` | `open_station(path)` | 初始化或重开工位库 |
| `station.intake` | `accept_initial(db, packet)` | 工位接纳号 |
| `station.start` | `start_review(db, batch_id, piece_id)` | 原有或新 `StartRecord`；交接暂停时返回 `PendingStart` 且不写开检记录 |
| `station.progress` | `station_progress(db, batch_id)` | 原榜号及按名单排序的 `started`、`pending` |
| `reports.issue` | `issue_revision(db, exchange, batch_id, initial_report_id, revision_id, request_id)` | 换榜报告号，交接未确认时返回 `pending` |
| `reports.read` | `read_revision(db, report_id)` | 固定原榜、修订、换榜时已开检片与生效名单 |
| `station.intake` | `handle_revision(db, message)` | 工位换榜入口，返回带 `state` 的字典 |
| `station.revision_store` | `set_handover(db, batch_id, paused)` | 控制工位交接暂停（新片暂返 `pending`） |

### 勘误后换榜（V2）

换榜只针对已接纳原榜的批次，一次请求由批号、已接纳的原榜号、同批仍存在的读数修订号和分析库内唯一的请求号确定。可指定历史修订，对该修订沿用 V1 完整风险序、原清册与限额（同分按清册序、全片无有效点拒发）。每批至多一份换榜生效。

- 工位把换榜与开检排出先后：生效名单包含全部换榜前已开检片，再按新风险序从其余片取足原限额，片号按清册序排列。换榜后只按生效名单开检，`StartRecord.report_id` 与 `StationProgress.report_id`、`acceptance_id` 仍指向原接纳和原榜。
- 交接中工位可对新开检暂返 `PendingStart`（不写开检记录），对换榜请求暂返 `pending`；分析库关闭时工位仍可按已有生效名单开检。
- 分析端凭工位实成裁决签报，固定原榜、修订、换榜时已开检片和生效名单。回包丢失或两库重开后，用原参数续办取得同一裁决和唯一报告号；后续开检与再次勘误不改变存值，同参重投返回原报告号。
- 未知批次、修订、原榜、工位接纳或换榜报告报 `KeyError`；非法输入、原榜或修订与批次错配、指定原榜与工位接纳不符、已登记请求号异参、同批另号再换榜及名单外开检报 `ValueError`。重投原始 V1 来件仍领回原接纳号，不影响已生效的换榜。

登记清册和测点采用有序列表或元组，测点用 `lots.gauges.GaugeSpec(name, baseline, unit)`。批号、片号、测点名和导入票是逐字匹配的非空白字符串。读数使用 `(片号, 测点名, 值, 单位)` 或 `measure.schema.Reading`，若明确缺测，值和单位都传 `None`。没有行的测点在风险证据中记为未上报。读数接收整数、`Fraction`、有限 `Decimal`、十进制或分数字符串以及以 Python 十进制字符串表示解释的有限浮点数。长度单位为 `mm`、`cm`、`m`、`um`。

导入票的规范内容按测点键排序并保留上报单位。同票同内容领回原快照。新票作为完整快照，勘误仅合并指定行。冻结可以指向仍存在的历史修订。计算先统一为 mm，再取各有效点绝对残差的有理平均。数值零参与平均，显式缺测与未上报留在证据里。整批每片得分后依精确风险降序、同分依清册序出榜。初榜取前 K 项。工位收到的 `InitialPacket` 保留入榜顺序，风险条目可按片号匹配后规范化重投。V1 同批一经接纳即固定执行名单。

未知批次、修订、冻结或报告引用在读取和处理入口报 `KeyError`。冻结入口以修订号定位，已知修订批次失配报 `ValueError`。非法定义、坏测量行、已知错批或过时父、全片无有效点、票或初榜冲突、坏来件及名单外开检报 `ValueError`。签榜时正文、证据、名单与首执同次提交，数据库提交错误会回滚并向调用者传播。
