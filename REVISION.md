# 勘误后换榜交接

初榜、读数及风险口径见 `README.md`。换榜针对已经接纳原榜的批次。分析主机与工位可分别停用，各自初始化和重开自己的 SQLite 库。换榜信息经调用参数和返回值交接，分析侧只持有分析库连接和工位调用函数。

## 换榜与开检

一次请求指定批号、已接纳的原榜号、同批确切读数修订和请求号。可指定仍存在的历史修订。对该修订沿用 V1 完整风险序与原清册、限额，包括同分规则以及无有效点时的拒发规则。每批至多一份换榜生效。

工位将换榜与开检排出先后，已开检片占用原限额，余位按新风险序补足。生效名单含全部换榜前已开检片，再依风险顺序从其余片取足原限额。换榜后按生效名单开检并查进度。交接中工位可对新的开检暂返 `pending`，此时没有新增开检记录。分析库关闭时，工位可按已有生效名单办理开检。已开检片重投仍可复领原 `StartRecord`。

分析端凭工位实成裁决签报，固定原榜、修订、换榜时已开检片和生效名单，片号按清册序。报告按号读取保存值。通信恢复后可用原参数继续，最终取得同一裁决及唯一报告号。工位已经生效而分析端尚未签报时，后续开检可照常进行，续签仍使用换榜时的开检集合。分析库的签报写入失败可用原参数续办。

## 调用与返回

- `reports.issue.issue_revision(db, exchange, batch_id, initial_report_id, revision_id, request_id)` 提交或续办。工位实成且分析报告保存后返回正整数报告号。交接暂未确认时返回字符串 `pending`。已签报的同参重投返回原号。
- `station.intake.handle_revision(station_db, message)` 是工位换榜调用入口。`exchange(message)` 调用这一入口并返回其字典结果。中间消息及裁决表示由实现定义。用于交接的返回字典有 `state` 字段，`pending` 表示尚未生效，`applied` 表示附带了已在工位提交且可复领的生效裁决。`exchange` 可因工位暂不可达或丢失应答抛出 `ConnectionError`。业务拒绝仍沿用对应异常。
- `reports.read.read_revision(db, report_id)` 返回包含 `report_id`、`batch_id`、`initial_report_id`、`revision_id`、`request_id`、`started_at_activation` 和 `selected` 的字典。最后两项是按清册序排列的片号元组。
- `station.start.start_review` 和 `station.progress.station_progress` 保持原调用签名。`StationProgress` 的 `acceptance_id` 和 `report_id` 仍指向原接纳及原榜。换榜前继续按原规则读进度。换榜后，`started` 和 `pending` 是生效名单中已开检、未开检的片，按清册序。`StartRecord` 的 `report_id` 仍为原榜号。

请求号是在分析库内绑定本次业务的非空名称，重投使用同一对库。批号与请求号沿用 V1 名称约定，数字编号是 SQLite 范围内的正整数且排除布尔。合法格式但查无批次、修订、原榜、工位接纳或换榜报告时报 `KeyError`。非法输入、原榜或修订与批次错配、指定原榜与工位接纳不符、已登记请求号异参、同批另号再换榜及平时在有效名单外开检报 `ValueError`。业务拒绝不为该请求启用名单或签报。重投原始 V1 来件仍可领取原接纳号，且不改变已经生效的换榜结果。

## 样例与交付验证

使用 `examples/day_shift.json`。初榜 X、Y，限额 2。勘误修订的风险序为 Z、Y、X。X 先开检时，换榜报告的 `started_at_activation` 为 `('X',)`，`selected` 为 `('X', 'Z')`，未开检的 Y 被拒。换榜先完成时，这两项分别为 `()` 和 `('Y', 'Z')`，X 被拒。

可用 `tests.fixtures.pause_before` 控制工位调用的先后。`tests.revision_link.make_exchange` 可让工位处理请求后丢弃首个 `applied` 回包，并保持该调用函数断线。用新的调用函数重新连到同一工位库。X 已开检的分支中，工位切换后丢失回包，再关分析库并实际开检 Z。此后再勘误，重开两端并用原参数续办。报告仍引用原指定修订和原榜，固定 `('X',)` 与 `('X', 'Z')`。重投同参返回原报告号。

沿现有 `.pointwise-runtime.json` 运行。完成后让 `verify` 实际核对上述联动及原回归，检查失败时返回非零。让 `demo` 展示样例中的实际名单、工位开检和丢回包后的按号续领。运行清单中的命令沿用现有 argv 形式。保留现有初榜演示入口、接口、原榜存值和全部原测试。
