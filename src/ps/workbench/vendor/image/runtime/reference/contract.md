# 图片流数据契约 v0.6.11 Proposal

日期：2026-09-30。证据层级：设计提案和纯软件参考模型；本版从 v0.6.10 修订，未经 A/B/负责人对**本版**同一哈希会签，未获 RTL、STM32 固件或实板验收。工程目标以 `竞赛/通信容错智能调优平台_工程规格_V2.0_2026-09-26.md` 为准。

## 1. 与 v0.5 的关系

v0.5 的线上帧字段、偏移、字节序、CRC 算法、图片上限、主机重组及重传规则继续适用，除本文件明确修订的内容。v0.5 `REG_FLIGHT_W0..W3`、队头/队尾读回、直接 `POP` 和 Gateway CRC 放行规则被本版**替换**，不得混合实现。v0.6.3 的回绕故障锁存、v0.6.4 的 CH1 可变长回报、v0.6.5 的可信关联封存、v0.6.6 的证据只读规则、v0.6.7 的截止/ABORT 时序、v0.6.8 的 tick 退休接口、v0.6.9 的最终 CH1 捕获准入及 v0.6.10 的额外字节和迟到 orphan 修订继续适用；本版修复 orphan 观察器可替换而导致封存漏项的问题。`reference_codec.py` 是 v0.5 参考编解码器的独立复制及修订；`queue_model.py` 与 `ch1_capture.py` 是纯软件模型。所有物理地址只是候选。

## 2. 线上字节契约

所有多字节字段均为大端；CRC-16/CCITT-FALSE（poly `0x1021`、init `0xFFFF`、xorout `0`、无反射），覆盖 SOF 后至 CRC 前的全部字节；`123456789` 的 CRC 为 `0x29B1`。`PROTO_VER=0x02`，与控制 UART V1.0 的帧壳和 TYPE 分开，不修改 V1.0 LEN/CRC 语义。图片上限：128×128 灰度基线，`ITEM_TOTAL≤64`，`1≤PAYLOAD_LEN≤512`，`ATTEMPT_ID=0..3`。`TRIAL_ID` 为线上 16 位，同一 run 内每次启动唯一，失败或超时不复用。

| 帧 | SOF | 字段（依线上顺序；括号为字节数） | 总长 |
|---|---|---|---|
| 配置请求 | `55 CC` | VER(1), RUN_ID(4), IMAGE_ID(1), PIXEL_FORMAT(1), CHANNEL_ORDER(1), WIDTH(2), HEIGHT(2), TOTAL_BYTES(4), ITEM_TOTAL(2), CHUNK_SIZE(2), ORIGINAL_SHA256(32), ITEM_CRC_LIST(2×N), FRAME_CRC(2) | `56+2N` |
| 配置 ACK | `55 CD` | VER(1), RUN_ID(4), IMAGE_ID(1), STATUS(2), FRAME_CRC(2) | 12 |
| 图片请求 | `55 AA` | VER(1), RUN_ID(4), IMAGE_ID(1), TRIAL_ID(2), ITEM_INDEX(2), ITEM_TOTAL(2), ATTEMPT_ID(1), ROUTE_MODE(1), SRC_CRC(2), PAYLOAD_LEN(2), PAYLOAD(L), FRAME_CRC(2) | `22+L` |
| DUT 回报 | `55 BB` | VER(1), RUN_ID(4), IMAGE_ID(1), TRIAL_ID(2), ITEM_INDEX(2), ATTEMPT_ID(1), ROUTE_MODE(1), UART_FLAGS(1), RESULT_STATUS(1), RECVD_LEN(2), RECVD_DATA(M), FRAME_CRC(2) | `20+M` |
| CLEANUP 请求/ACK | `55 EE`/`55 EF` | VER(1), RUN_ID(4), IMAGE_ID(1), CMD/STATUS(2), FRAME_CRC(2) | 12 |

配置一致性要求 `TOTAL_BYTES=WIDTH×HEIGHT` 且 `ITEM_TOTAL=ceil(TOTAL_BYTES/CHUNK_SIZE)`；`PIXEL_FORMAT=1`、`CHANNEL_ORDER=0`。成功的 DUT 回报也必须带全部实收 `RECVD_DATA`。DUT 对请求外层 CRC、长度、源 CRC 分别判定；源 CRC 不符为 `REQ_CRC_ERR=0x01`。回报的 `UART_FLAGS` 位 0..3 依次为 PE、FE、NE、ORE；`RESULT_STATUS` 为 OK=0、REQ_CRC_ERR=1、LEN_ERR=2、UART_ERR=3。主机 `HOST_TIMEOUT=0xFE` 仅是截止后的本地结论，不是线上 DUT 状态。

## 3. 7020 可信队列与 AXI 候选接口

图片元数据块候选基址 `0x43C50000`；CH1 块候选 `0x43C60000`。现有 CH0 A/B 已占 `0x43C20000`。这些地址未经 BD Address Editor、HWH 和实板确认。以下偏移是**v0.6.11 候选接口**，不是现有 bitstream 寄存器。AXI 数据字为 32 位，字段占一个字并以低位有效；未使用高位写 0。跨字不是自动原子：只有成功 COMMIT 才把完整 shadow 拷入一个空槽。`BRESP=OKAY` 只表示总线写结束，主机必须再读 COMMIT 回执。

| 偏移 | 名称 | 方向与语义 |
|---|---|---|
| `0x00` | IP_ID | R；v0.6 新块身份待 RTL 分配，不沿用 CH0 IP ID |
| `0x04` | PHASE | R；0 FILL、1 ARMED、2 BUSY、3 DRAIN；复位后 FILL |
| `0x08` | CTRL | W；bit0 CLEAR_SHADOW（仅 FILL），bit1 ARM，bit2 ABORT |
| `0x0C` | COMMIT | W；写 1 尝试一次提交；每次尝试递增 COMMIT_SEQ，回绕前拒绝并停机 |
| `0x10` | COMMIT_SEQ | R；最近一次尝试的 32 位序号 |
| `0x14` | COMMIT_STATUS | R；0 ACCEPTED、1 PHASE、2 INCOMPLETE、3 FULL、4 RANGE、5 DUPLICATE_TRIAL、6 BATCH_MISMATCH、7 GENERATION_WRAP、8 CRC_TABLE_MISMATCH、9 CRC_TABLE_INCOMPLETE、10 COMMIT_SEQ_WRAP、11 SLOT_SEQ_WRAP；保持至下次尝试 |
| `0x18` | COMMIT_SLOT | R；成功时槽号 0..7，失败时全 1 |
| `0x1C` | COMMIT_GENERATION | R；成功时该槽本次 32 位 generation，失败时 0 |
| `0x20..0x50` | SHADOW[0..12] | W/R；按下表字段顺序；每写一字置相应有效位；ARM 后全拒绝 |
| `0x54` | SHADOW_VALID_MASK | R；低 13 位全 1 才完整；CLEAR/成功 COMMIT 清零 |
| `0x58` | ARM_EXPECT_COUNT | W；1..8，仅 FILL |
| `0x5C` | ARM_EXPECT_SEQ | W；须等于 `LAST_ACCEPTED_SEQ`，仅 FILL |
| `0x60` | ARM_STATUS | R；ACCEPTED/REJECTED，与 PHASE 同步读回 |
| `0x64` | SLOT_SELECT | W；0..7 |
| `0x68` | SLOT_SEQ | R；选中槽的 32 位 seqlock 版本。硬件更新期间为奇数，稳定时为偶数；读回前后相同且为偶数才可采信 |
| `0x6C` | SLOT_STATE | R；EMPTY/QUEUED/STARTED/TERMINAL |
| `0x70` | SLOT_GENERATION | R；32 位，复位后首次使用为 1，回绕前拒绝提交并要求停机复位 |
| `0x74..0xA4` | SLOT_FIELD[0..12] | R；完整 13 字段，顺序同 SHADOW |
| `0xA8` | SLOT_RESULT | R；仅 TERMINAL 有效；含终态原因码 |
| `0xAC` | SLOT_EVIDENCE_REF | R；指向不可覆盖事件/原始证据的序号 |
| `0xB0` | ACK_SLOT | W；待确认槽号 |
| `0xB4` | ACK_GENERATION | W；待确认 generation |
| `0xB8..0xD0` | ACK_IDENTITY[0..6] | W；按下表身份顺序提交完整键 |
| `0xD4` | ACK_RESULT | W/R；写 1 尝试确认，读回 ACCEPTED 或拒因；仅终态且键完全一致才释放槽 |
| `0xD8` | LAST_ACCEPTED_SEQ | R；最近一次成功 COMMIT 的序号；与每次尝试递增的 COMMIT_SEQ 分开 |
| `0xDC` | REJECT_ACK | W/R；最近 COMMIT 被拒后，主机核对全部已提交槽与 CRC 表，再写 1 证明已查看；仅 ARM_EXPECT_COUNT、ARM_EXPECT_SEQ 与 `REJECT_ACK_EXPECT_COMMIT_SEQ` 同当前批次和**最近拒绝**序号一致时清锁存，读回 ACCEPTED/ALREADY_ACKED/REJECTED |
| `0xE0` | CRC_TABLE_RUN_ID | W/R；表所属 run，低 32 位 |
| `0xE4` | CRC_TABLE_IMAGE_ID | W/R；表所属 image，低 8 位 |
| `0xE8` | CRC_TABLE_COUNT | W/R；1..64，须等于批次 ITEM_TOTAL |
| `0xEC` | CRC_TABLE_VALID | R；仅表示硬件已接收合法 COUNT 且每一项写入过；不表示硬件知道主机是否逐项比对成功 |
| `0xF0` | FAULT_STATUS | R；无故障为 0；序号/代数回绕、原始缓存或事件溢出等故障锁存原因，直到受控停机、证据封存和新 session 初始化后清除 |
| `0xF4` | REJECT_ACK_EXPECT_COMMIT_SEQ | W；写本次待确认的**最近被拒** COMMIT_SEQ；旧拒绝号不可复用 |
| `0xF8` | LAST_REJECT_ACKED_SEQ | R；最近一次被确认拒绝的序号；重复写同一确认只回 ALREADY_ACKED、不重复改变状态 |
| `0x100..0x1FC` | CRC_TABLE[0..63] | W/R；每字低 16 位为可信 SRC_CRC，其余写 0；仅 FILL 且队列空可改 |

字段顺序与位宽：`RUN_ID`32、`IMAGE_ID`8、`TRIAL_ID`16、`ITEM_INDEX`16、`ITEM_TOTAL`16、`ATTEMPT_ID`8、`ROUTE_MODE`8、`PAYLOAD_LEN`16、`TRUSTED_SRC_CRC`16、`ROUTE_EPOCH`32、`RX_PROFILE`8、`D`8、`S`8。`S` 用 8 位二补码，合法候选仍按工程规格 V2.0 的 d/s 集合；Direct 可用 RX_PROFILE=0 表示仅观测。ACK 身份顺序：`RUN_ID, IMAGE_ID, TRIAL_ID, ITEM_INDEX, ATTEMPT_ID, ROUTE_MODE, ROUTE_EPOCH`。`slot+generation+完整身份` 均匹配才可 ACK；只按槽号或只按队头 POP 禁止。

首版每批最多 8 项。先写完整可信 CRC 主表，硬件 `CRC_TABLE_VALID` 只检查 COUNT/写入有效掩码；**PYNQ 必须另逐项读回并与 ledger 比较**，不一致不得 COMMIT/ARM。首项 COMMIT 后表、run/image 和全局配置均锁定，直至所有槽终态且 ACK 释放。每项 COMMIT 须检查该槽的 `TRUSTED_SRC_CRC` 等于表中 `ITEM_INDEX` 条目，且 ITEM_TOTAL 等于表项数。FILL 中预填，COMMIT 成功仍处于 FILL；ARM 校验数量、`LAST_ACCEPTED_SEQ`、CRC 表有效与批次路由，锁定后按提交顺序 START。ARM 后禁止 shadow、COMMIT、改变 ROUTE_MODE/ROUTE_EPOCH/RX_PROFILE/d/s；运行中不补。START 后该 trial ID 永久占用，即使失败或 ABORT；硬件复位后主机 ledger 仍须防重用。ABORT 禁新 START；未开始项记 `ABORTED_UNSENT`，在途项仍等待实际终止或既定超时。各槽终态和原始证据写定之后才可带身份 ACK；所有槽 ACK 完成回 FILL，下一批才可换路由。物理切换还须独立电气互锁签核。

每次正常运行的 COMMIT 尝试（成功或拒绝）都增加 `COMMIT_SEQ`；达到上限后不再递增，故障期间重复写只回读锁存故障。成功时额外更新 `LAST_ACCEPTED_SEQ`。**最近一次尝试若被拒绝，ARM 必须拒绝**，即使前 8 项已成功提交且 ARM_EXPECT_SEQ 恰好等于 COMMIT_SEQ。主机可在不丢弃前 8 项的情况下读取拒绝原因、逐槽及 CRC 表重新核对，然后设置正确的 ARM_EXPECT_COUNT、`LAST_ACCEPTED_SEQ` 和**本次最新拒绝**的 `REJECT_ACK_EXPECT_COMMIT_SEQ`，再写 `REJECT_ACK`。旧拒绝序号的确认不得清除新拒绝；同一确认重复写只返回 ALREADY_ACKED 且不重复改变状态。回执和审计事件保存被确认的拒绝序号。未核对就清锁存属于主机错误，硬件只核身份与序号，不能宣称证明主机确实看过每个槽。新的成功 COMMIT 也可清先前拒绝态。COMMIT_SEQ、SLOT_SEQ 或 generation 接近 32 位回绕时，不静默回到 0；**包括 COMMIT 被 SLOT_SEQ/GENERATION 回绕拒绝在内，三类回绕均须在返回拒因前锁存 `FAULT_STATUS` 与首个故障事件**。故障锁存后不得通过 `REJECT_ACK` 或后续成功 COMMIT 清除，停止新 START/COMMIT/结果 ACK 和 shadow/CRC 表修改；原槽、原始证据与故障寄存器保持可读。受控停机封存后以新 session 初始化，主机持久 ledger 继续防试次重放。已有在途项的终止、截止与证据封存仍需 RTL 时序专项会签，不得因故障宣称其成功完成。

同一个 PL 时钟边沿若出现多个互斥控制请求，`ABORT` 和硬件故障锁存优先；结果终态事件先于结果 ACK；COMMIT、REJECT_ACK、ARM 两两同拍时拒绝这些互斥操作并记录 `OP_CONFLICT`，不能把某操作在同拍的副作用用于另一操作的准入。主机须分开写、读回每次状态后再发下一命令。软件模型是顺序函数调用，**不证明**这个时钟级优先级；需后续 RTL/TB 插入同拍竞争验证。

主机读回顺序：先读回 CRC 主表身份、数量及各 CRC → 写全 shadow → 读 VALID_MASK → 写 COMMIT → 读 COMMIT_SEQ/STATUS/SLOT/GEN/LAST_ACCEPTED_SEQ → SLOT_SELECT → 读 SLOT_SEQ、STATE、GEN、全部 13 字段、结果与证据引用、再读 SLOT_SEQ；两次 SLOT_SEQ 相等且为偶数、字段与主机 ledger 相同，才能接受该次快照。PL 对每个槽的变更必须原子发布：开始更新时 SLOT_SEQ 变奇，完整字段/状态/证据写定后变为下一个偶数。建槽、START、终态、ABORT 标记、ACK 释放均触发版本变化；选中槽期间即使更新也不能让主机读到“旧版本 + 新字段”。切换 SLOT_SELECT 时重新开始读回，不能沿用前一槽版本。无证据的 `OKAY` 不算 COMMIT 接受。结果事件必须保存槽、generation、完整身份、结果码、证据引用；事件溢出是 INVALID，不能覆盖尚未 ACK 的证据。

## 4. Gateway 完整帧闭合和四类 CRC

Gateway 对每次已 START 的槽，仅接收该 route epoch、所选 A/B 路的本次 CH0 原始字节；另一 A/B 路完整保留作比较。先收满 20 字节头，再按可信 PAYLOAD_LEN 计算预期总长 `22+L`；必须收到该长度并经过预登记的帧结束空闲窗，才视为边界完整。超时、短帧、额外字节、溢出、迟到字节或来源不明的数据全部保存并拒转发；不得把下一 trial 的字节拼到本次。FE/PE/NE/ORE 任一位或硬件缓冲溢出都拒转发，分别记具体位与原始字节。UART 错误门槛属于保守首版，今后放宽须新版本及实测。

在边界、身份、长度、版本、线上 SRC_CRC 与可信 SRC_CRC、同次所选路 payload 来源均成立后，按下表分类：

| 输入 FRAME_CRC | 实际 payload CRC 对可信 SRC_CRC | 决策 |
|---|---|---|
| 正确 | 相等 | 正常转发本次实际 payload；保存原帧和新帧 |
| 错误 | 不等 | 可转发本次**实际错误 payload**，保持可信 SRC_CRC，重算发往 STM32 的外层 CRC；标 `FORWARD_ACTUAL_BAD_PAYLOAD` |
| 错误 | 相等 | `DROP_FRAME_CRC_ONLY_OR_AMBIGUOUS`；不静默修复外层 CRC |
| 正确 | 不等 | `DROP_INCONSISTENT_SOURCE_CRC`，调查上游配置或故障位置 |

CRC16 不能绝对证明故障位置。转发前必须记录原始 FRAME_CRC 是否正确、实际 payload CRC、所选 A/B、原始字节、候选转发字节、槽/generation；不能用原图替换译码。Direct 的 CH0 A/B 仅是 PA10 近端观测，不能归因于 STM32 内部 d/s 调节。

## 5. CH1 原始回报、时间和容量

CH1 从 STM32 PA9 对**每一个正常或异常接收字节**保存 `{data:uint8, flags:uint8, timestamp_ticks:uint64}`；flags 的低四位为 PE/FE/NE/ORE，其余位写 0。时间戳来自同一单调 64 位采样计数器，记录计数器时钟身份、实测频率、session/reset epoch；时钟值目前不按 100 MHz 猜定。读 64 位计数和对应字节必须为同一事件的原子快照；计数器回绕前停机封存并重建 epoch，不静默归零。帧描述符另存开始/结束 tick、结束原因、槽/generation 和原始字节范围，再独立解析 `55 BB` 回报。

CH1 **不能在首字节前预知 DUT 实际回报的 `RECVD_LEN=M`**。首字节前将可信 attempt 身份（RUN_ID、IMAGE_ID、TRIAL_ID、ITEM_INDEX、ATTEMPT_ID、ROUTE_MODE）、route epoch、槽号/generation、接收窗口、deadline、532 字节线上上限、缓存容量与正数 idle guard 复制为**不可变快照**；请求长度 `L` 只用于后续比较，不作为帧闭合长度。未经关联而收到的字节保留为原始证据，事后补身份或由主机任意填写“期望总长”不得把它们转成有效回报。关联字段在本次捕获期间不可覆盖；重新关联须新建捕获实例/硬件描述符，旧原始证据仍保持原归属。

捕获状态候选为 `WAIT_WINDOW → HEADER(18B) → BODY_AND_CRC → IDLE_GUARD → VALIDATE → TERMINAL`。前 18 字节由 CH1 原样保存；其中 `RECVD_LEN` 在字节偏移 16..17。头达到 18 字节后检查 SOF、版本、`M≤512` 与 `20+M≤532`/缓存容量，得到**未证实的**候选总长 `20+M`，不能据此采信线上身份。头坏、超界或缺字节时保留原始流，按边界/超时/长度原因置 INVALID。收满候选长度后进入空闲窗；窗内额外字节使本候选 INVALID。空闲窗届满才做完整回报 CRC、全部线上身份与**封存的**可信 attempt 核对。同一 tick 的闭帧原因须按优先级归并；该 tick 结束后分类封存，原始字节及终态不可因后续读取、迟到 orphan 或外部变量变化而改写。仅 CRC 和身份均通过者为 `VALID_DUT_REPORT`；其 `RESULT_STATUS` 可以是实际的 DUT 错误，`M` 可以为 0、介于 0 与请求 `L` 之间或等于 `L`，不能将完整的短数据错误回报误报为串行短帧。外层回报 CRC 通过并不等于原图字节/源 CRC 正确；后者由 PYNQ 用真实 `RECVD_DATA`、可信源 CRC 和 ledger 另行判定。

结束原因：候选长度加预登记空闲窗、窗内额外字节、字节间超时、attempt 截止、缓冲溢出或 ABORT。同一 tick 有多个条件时保守优先级为 `BUFFER_OVERFLOW > ABORTED > ATTEMPT_DEADLINE > EXTRA_BYTES > INTERBYTE_TIMEOUT > EXACT_LENGTH`。即使候选字节数恰好，ABORT 必须是 `INVALID_ABORTED`，attempt 截止必须是 `INVALID_ATTEMPT_DEADLINE`，字节间超时须记 `INVALID_UNCLOSED_FRAME_TIMEOUT`。额外字节、坏 CRC、身份不匹配、迟到字节、无关联字节全部保留，不能伪造或补全回报。额外字节在空闲窗内使候选帧 INVALID；窗外迟到字节进入独立 orphan 原始流/事件，不追加到已终止帧。`HOST_TIMEOUT` 只能由 PYNQ 在已登记 deadline 过后生成，硬件不得合成 DUT 报文。此软件模型只检查调用者给定的事件序列，不能证明实际 UART 空闲窗和同拍优先级。

v0.6.8 继续采用半开接收窗口：字节 `timestamp < attempt_deadline_tick` 才属于本次候选；等于截止 tick 的字节进入独立 orphan 流，同 tick 的 ABORT/溢出可高于截止；晚于截止的字节也只进入 orphan，不能再用其触发的溢出覆盖已发生的截止。候选长度空闲窗的闭合 tick 若 `>= attempt_deadline_tick`，包括**恰好相等**，必须判 `INVALID_ATTEMPT_DEADLINE`，除非同 tick 确有 ABORT/溢出。显式截止事件早于预登记 tick 必须拒绝；若调用方直到较晚 tick 才处理定时器，模型仍以预登记的截止 tick 作结束时间，较晚事件不得倒改终态。软件模型要求事件按非递减 tick 输入；同 tick 的顺序调用视为一组，较高优先级原因可提升拍内暂定分类，下一 tick 输入后不可倒改。`raw` 为不可变字节串，逐字节样本、错误及 orphan 事件为不可变快照序列；外部代码不得通过持有或修改事件对象改写时间戳、错误原因及终态判定。硬件实现必须在每拍汇总条件后一次性提交终态，软件顺序调用不证明 RTL 已实现该时序。

v0.6.8 软件接口区分**拍内暂定**与**拍后最终**：`close()`/`byte()` 在同 tick 返回后，`classify()` 可显示当前分类，但上层不得以它或 `closed=True` 作为最终接受依据。调用 `retire_tick(t)` 将事件水位推进至较后 tick，或输入下一 tick 事件；只有 `finalized=True` 且 `classify_final()` 返回最终分类时，才可消费结果。在闭合 tick 输入的实际额外字节（且未越过 attempt deadline、未触发更高优先级溢出）须追加到本候选原始字节和时间样本，并把 `EXACT_LENGTH` 提升为 `INVALID_EXTRA_BYTES`；**下一 tick** 的字节才进入独立 orphan。拍内证据可追加，拍后原始帧及终态封存。`retire_tick` 不制造 UART 字节；若推进时越过尚未处理的登记 deadline，结束 tick 仍取登记值。RTL 应按同拍事件聚合实现，与 Python 函数的先后调用无关。

v0.6.9 将同拍额外字节规则扩展到**已收满候选却先收到 `INTERBYTE_TIMEOUT` 事件**的顺序：在闭合 tick 仍有真实额外字节时，按 `EXTRA_BYTES > INTERBYTE_TIMEOUT` 归并，字节进入本候选原始样本；deadline、ABORT、溢出仍按更高优先级处理。软件模型由调用方提供 `EXACT_LENGTH` 与 `INTERBYTE_TIMEOUT` 的定时器事件，`retire_tick()` 只推进事件水位并处理已登记的 attempt deadline；它本身不推导空闲窗或字节间超时。RTL 必须实现实际计时器与同拍聚合，不能把软件函数调用视为时钟级证明。

v0.6.10 明确反向调用顺序：候选长度已满时，如先收到真实额外字节，该字节立刻加入原始样本并暂定闭合为 `EXTRA_BYTES`；同 tick 随后的 `INTERBYTE_TIMEOUT` 或 `EXACT_LENGTH` 不得降级或抛出伪长度异常，随后的 deadline、ABORT、溢出仍按既定高优先级提升。下一 tick 才可退休并供主机消费。这是软件顺序模型约定，真实 PL 仍须独立验证同拍聚合。

最大合法回报 `20+512=532` 字节。`8×544B` 只能视为原始字节缓存预算草案；以每字节 8+8+64=80 bit 存储，八槽仅样本位就需 `348160 bit`（约 10 个 36 Kbit BRAM 的理论下限），另需描述符、事件、orphan 流及读出裕量。无背压 UART 下，原始缓存满、事件 FIFO 满或 PS 读不及时时必须锁存独立溢出计数/原因、保留未 ACK 的首次证据并把受影响 trial 标 INVALID；不可覆盖旧字节或算 DUT 损坏。CH1 的空闲窗、字节间超时、attempt deadline 数值、计数器时钟、BRAM/FIFO 规模和 PS 读取最坏延迟待 RTL 资源预算与实板测量签核，当前不可凭软件模型定值。

## 6. 图像证据与恢复

PYNQ 以真实 CH1 回报重组首轮图；未提交项为 UNSENT，已提交但 deadline 过后无回报为 MISSING，短数据为 POSITION_UNCERTAIN。坏图空位可显示占位色，但保留原始字节。仅重传失败项，重传使用新 trial ID，至多三轮；恢复图只采用真实成功回报，成功须状态 OK、flags 0、长度、回报 CRC、源 CRC 与逐字节原图全部符合。最终比较完整 SHA-256。每次提交、原始 CH0/CH1、选择路、Gateway 原/新 CRC、STM32 实收、终态、ACK、重传及封存哈希均独立保存；异常第一次证据不可覆盖。

v0.6.9 软件参考接口要求主机在本次队列 COMMIT/slot/generation 读回之后、**首个 CH1 字节之前**调用 `bind_capture_attempt()`，由图片管理器创建本次唯一的 `Capture` 句柄，并登记完整线上身份、route epoch、slot/generation、窗口与 deadline。首次与重传回报仅接受该句柄的 `finalized=True` 结果；管理器再次核对预登记身份/窗口、完整封存原始字节和解析结果。`VALID_DUT_REPORT` 只是 CH1 准入，随后还要按 DUT status/flags、实际长度、源 CRC/字节与原图比较。CH1 为 `INVALID_*` 时保存完整逐字节样本、错误、orphan、原始帧、终止原因和时间；首轮项标 `CAPTURE_INVALID`，重传则在独立的重传历史中标注捕获失败并保持首轮掩码，之后可按新 trial 重传；不得从 CRC 正确的帧前缀生成 `MASK_OK` 或恢复图。未收任何候选字节的 `HOST_TIMEOUT` 需要已登记窗口和晚于 deadline 的时间证据；部分字节或其他终止原因不可改称超时。软件句柄所有权只证明模型内部准入；真实 PYNQ 仍须核对队列硬件回执与事件、保存原始证据后才能 ACK。

v0.6.10 的 `attempt_history.jsonl` 保持记账时点的只读快照。对管理器拥有的 Capture，在记账后抵达的 orphan 逐样本附带 run/image/item/trial/attempt/route、槽/generation/route epoch 身份，追加到 `late_capture_events.jsonl` 和审计日志；封存清单将该文件纳入 SHA-256。即使管理器清理活动句柄，已追加事件仍保留。一次封存仅覆盖封存截止前已收到的事件；封存之后若又有迟到 orphan，应另作增量封存，不能修改旧封存或把它反填到首次回报快照。硬件需给出 orphan 收集截止/事件水位和无漏项证明，本软件回调不能替代。

v0.6.11 要求软件模型的 orphan 观察器**一次绑定、不可替换或解绑**。管理器在首次记账前绑定，仅本管理器持有的 Capture 可建立该绑定；若 Capture 已被其他调用者预先绑定，报告准入须失败，不得先记为成功再遗漏后续 orphan。重复报告记账不得覆盖已有绑定。观察器记录失败时本次 `byte()` 必须抛错，Capture 不得留下该 orphan 而管理器没有对应证据；管理器该次事件的列表写入须回滚。调用方应停机处理失败，不能把软件异常当作有效 DUT 回报。这是参考模型内部的一次性绑定约束，不宣称 Python 进程能抵御任意恶意内存修改；硬件证据链另待设计与实测。

## 7. PYNQ→AX7010 图片上行链：待物理选型

源是 7020/PYNQ 保存的图片字节，目的为 AX7010 图片发送缓冲，之后 AX 从 W19 发受扰 UART。当前资料**未证明**这条上行链的 7020 出脚、AX 入脚、连接器、波特率或实测吞吐。现有 7020 P5-5/6 ↔ AX J11-3/4 是 230400 8N1 的 V1 控制 UART，不能再写成“空闲 P5 高速 UART”，也不能用它循环发送图片当成已实现的独立高速链。B 提出的第二路路由 UART 使用 7020 P2 与 AX J10-9/10 的候选脚，仅服务路由证明，亦不得承载图片 payload；其具体 P2 脚号与底板 V3.6 原理图存在冲突，待实物和正式针脚表核对，不按 P2-17/18 直接接线。

| 候选上行方案 | 目前证据 | 冻结前必须给出的事实 |
|---|---|---|
| 另设跨板 UART | 2 Mbps 仅情景预算 | 两端空闲 FPGA 脚、连接器/方向、电压、专用线束、收发器、时钟误差、实际持续吞吐、与 V1/路由 UART 隔离 |
| SPI 或其他并行/串行链 | 无现成板间实现证据 | 主从角色、实物端子、信号数、时序、缓冲、协议与持续吞吐 |
| PS 网络/USB 中转 | 无当前系统集成证据 | 两板可达路径、延迟、失联处理、对 AX PL 缓冲的可靠交付 |

负责人和 A 须在后续版本附连接图、板级引脚来源、实物占用核查、数据速率与 CRC/背压策略；B 复核 AX 端写入路径。未定前仅可做软件图片参考测试和预算，不开始以上行已存在为前提的集成。

## 8. 会签前未决项

7020 最终地址/IP ID、ACK/事件 FIFO 的 RTL 时序、CH0/CH1 空闲窗与 deadline 数值、容量和读出带宽、AX7010 图片上行物理链、STM32 连续流固件、模式选择器及 PA10 电气、RX_PROFILE 编码/d/s 具体硬件映射，均待 A/B/负责人对本版文件哈希共同复核并通过后续实现与实板门槛。此文不能作为接线许可或生产 bitstream 依据。
