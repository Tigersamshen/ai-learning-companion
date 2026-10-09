# 工具接口

统一入口：`python3 <plugin-root>/scripts/learning_tools.py [--root <data-root>] <command>`。
数据目录按 `--root`、`AI_LEARNING_ROOT`、用户外部配置、旧版插件 config.json、`~/Documents/AI学习助手` 的顺序选择。外部配置默认位于 `~/Library/Application Support/ai-learning-companion/config.json`，可用 `AI_LEARNING_CONFIG` 指定。新版安装器将配置和学习数据保存在插件缓存之外。每次调用返回一个 JSON；错误退出码 1，人工内容冲突退出码 2。
工具仅管理 `<root>/学习笔记库/主题/<topic-id>/`；机器状态为 `<root>/state/<topic-id>.json`。
topic-id 用英文、数字、短横线或下划线；标题可用中文。正文/JSON用文件参数，不拼接 shell 字符串。

## 主题和进度

- `topic-init --id SLUG --title 标题 --mission 具体目的 --success 可观察结果`：新主题初始化；同一 ID 不覆盖已有目标。
- `status --topic SLUG`：返回 `topic`、`workspace`、`phase`、`mode`（`new_topic`/`continue`）、`next_action`、`pending_quiz`、`awaiting_evaluations`、`diagnosis`、`route`、`current_node`、`learning_records`、`sync`。不会返回正确答案和解析；`awaiting_evaluations` 返回已提交开放题的原题、rubric、作答和 attempt_id，方便中断后评阅，无需读取 raw state。
- `diagnosis-finish --topic SLUG [--skip]`：结束诊断，默认预算六题。少于预算允许用户主动缩短；全对只确认下界，记录上界未定位。存在待答题时先等作答或明确取消。
- `checkpoint --topic SLUG --phase diagnosing|planning|teaching|reviewing|complete [--node NODE] [--note 备注]`：保存教学断点。首次进入 teaching/reviewing 需诊断完成及非空路线；pending 时不得跨过作答继续教学。
- `mission-update --topic SLUG --mission 新目的 --success 新结果 --confirmed`：仅用户已经明确同意后调用，保留学习记录/路线/诊断成果；受影响路线由 route-set 局部更新。
- `route-set --topic SLUG --file ROUTE.json [--replace]`：默认按节点 ID 合并、追加边，保留其他分支；显式 replace 才全量替换。
- `route-visual --topic SLUG --manifest RESULT.render.json`：将本主题内已查看并验证的路线 PNG 关联到当前路线。Obsidian 默认显示该 PNG；路线或 PNG 字节变化后自动撤下旧预览，等待重新渲染与关联。

路线 JSON：`{"nodes":[{"id":"c1","label":"概念","status":"unknown","source_refs":["https://..."],"evidence_refs":[]}],"edges":[["c1","c2"]]}`。
状态为 `confirmed`/`pending`/`unknown`。confirmed 必须引用有效的 demonstrated/correction 学习记录，自述先验或目标变化不能单独作为掌握证据。边必须指向存在节点且不成环。

## 测验（一次一个问题）

`quiz-create --topic SLUG --file QUESTION.json`：保存并投影公开题面，返回实际显示顺序。已有 pending 不换题。诊断达到预算后拒绝继续全面加题，应调用 diagnosis-finish。

选择题 spec：
```json
{"id":"q1","kind":"choice","phase":"diagnostic","concept_id":"c1","question":"问题？","options":[{"id":"a","text":"选项甲"},{"id":"b","text":"选项乙"}],"correct":["b"],"explanation":"提交后显示的解析","source_refs":["https://..."],"shuffle":true}
```
`kind` 为 `choice`/`multi`/`open`；`phase` 为 `diagnostic`/`teaching`/`review`。open 题用 `rubric`（非空评分标准）替代 options/correct。选项 ID 必须稳定唯一；不把不知道写成普通错误选项。

- `quiz-submit --topic SLUG --quiz q1 --attempt a1 --answer ANSWER.json`：answer 可为 JSON 文件路径或 JSON 字符串；`{"selection":["b"]}`、`{"dont_know":true}`、`{"cancelled":true}`、开放题 `{"text":"我的推导"}`。提交后返回 `result.outcome`。同一 attempt/quiz 的相同提交幂等，不同内容拒绝；原顺序持久化。
- `quiz-assess --topic SLUG --quiz q1 --file ASSESSMENT.json`：开放题提交后由教师按原 rubric 评阅；要求 `{"outcome":"correct|wrong","rationale":"评阅依据","model":"当前实际模型名","rubric":"实际采用标准"}`，不能假造评阅模型。dont_know/cancelled 无需评阅。
- outcome 为 `correct`/`wrong`/`dont_know`/`cancelled`/`awaiting_evaluation`；未答题由 pending 状态表示，取消不计诊断预算。

## 记录和同步

- `record-learning --topic SLUG --file RECORD.json`：`{"title":"理解变化","summary":"具体学会什么及意义","kind":"demonstrated","evidence_refs":["q1"],"evidence":"用户怎样表现理解","implications":"下一步","supersedes":null}`；kind 为 demonstrated/prior_knowledge/correction/mission_change。自述先验用 prior_knowledge 并明确 evidence 文字；其他理解记录需已评阅作答引用，不能把看完 HTML 当证据。mission_change 引用已记录的目标变化。
- `sync --topic SLUG`：幂等生成课程索引、路线、课时日志、学习记录；人工修改冲突时保留原文件并写 `<root>/state/conflicts/` 待合并版本，返回 conflict。每次正式状态变化先记 pending，投影失败后仍保留状态，可重复 sync 补写。
- `note-patch --topic SLUG --path 相对路径 --file BODY.md --expected-hash SHA256`：显式保存审核过的合并内容，先核对当前文件 hash。无 hash 不允许覆盖未经工具管理的已有内容。
- `review-list --topic SLUG`：列出 wrong/dont_know 涉及概念和已确认记录，复习教学由 teach 进行，不创建提醒。
- `open --topic SLUG [--path 课程索引.md] [--target auto|obsidian|browser]`：默认 HTML 交给系统浏览器，其他文件使用 deployment.json 已登记 Vault ID 的 Obsidian CLI；优先使用 Codex 浏览器时可直接打开返回的绝对 HTML 路径。
- `vault-status`：检查 CLI 和 Vault 登记，不读其他笔记正文。
- `render --kind mermaid|svg --input SOURCE --output-dir DIR [--stem NAME]`：调用 diagram_renderer，返回 source/svg/png/preview/log 和 rendered/failed。rendered 不等于 visual_verified；maker 必须亲自看图。
- `diagram-verify --manifest RESULT.json --note 检查结论`：**仅亲自查看返回 PNG 并核对内容/布局后**记视觉检查通过。

HTML 小测只提供浏览器即时反馈，不导入正式结果。机器状态中正确答案不属于考试级保密，正常题面/索引/日志在提交前不含答案或解析。

本机实测运行条件：Chrome 和 Obsidian 的 IPC 在 Codex 文件沙箱内可能无法访问。明确日志是环境权限限制时，通过正常命令审批重试获授权的本地操作；保留隔离 Chrome 配置，不关闭 Chrome 的进程沙箱。不要把 CLI 的“找不到 Obsidian”误报为未安装；同时检查应用是否正在运行。
