import os, fcntl
if "board_session" in globals():
    raise RuntimeError("本内核已初始化过，不重复执行")
runs = root / "board_runs"
assert runs.is_dir()
assert "board_lock" in globals() and not board_lock.closed, "先完成第1步的独占检查"
fcntl.flock(board_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
alloc = runs / "namespace_allocations.jsonl"
assert alloc.is_file(), "禁止重建或重置历史编号文件"
numbers = [json.loads(line)["number"] for line in alloc.read_text(encoding="utf-8").splitlines() if line.strip()]
assert numbers == list(range(1, len(numbers) + 1))
n = len(numbers) + 1
assert n < 0x10000000
session_dir = runs / ("session_%08x" % n)
assert not session_dir.exists()
with alloc.open("a", encoding="utf-8") as f:
    f.write(json.dumps({"number": n}) + "\n")
    f.flush(); os.fsync(f.fileno())
directory_fd = os.open(str(runs), os.O_RDONLY)
try: os.fsync(directory_fd)
finally: os.close(directory_fd)
buses = {bank: MMIO(base, size) for bank, (base, size, _) in BANKS.items()}
board_session = CandidateSession(
    buses, session_dir, local_epoch=0x10000000+n, peer_epoch=0x20000000+n,
    session=0x30000000+n, control_epoch=0x40000000+n,
    exclusive_owner=True, poll_limit=10000)
control_uart = RealtimeUARTLiteControlTransport(
    MMIO(0x42c00000, 0x10000), board_session.journal,
    library=native_library, exclusive_owner=True, timeout=2.0,
    receiver_cpu=1, receiver_priority=10, receiver_idle_ns=50000)
try:
    control_uart.start_receiver()
    board_session.initialize(control_uart)
    print("READY:", board_session.upload.ready)
    print("会话故障:", board_session.fault)
    print("证据目录:", board_session.root)
    print("实际线程调度:")
    print(json.dumps(control_uart.scheduling_snapshot(), indent=2))
    mark_preflight = inspect_raw_mark_interface(board_session, MMIO, root / (name + ".hwh"))
    print("CH2 采集接口预检:")
    print(json.dumps(mark_preflight, indent=2, ensure_ascii=False))

    mpg1_preflight = inspect_multipoint_capability(board_session, buses)
    print("7010 MPG1 能力预检:")
    print(json.dumps(mpg1_preflight, indent=2, ensure_ascii=False))

    from image_owner import ImageOwner
    from image_service import ImageService
    from web_service import start
    import shutil
    web_workspace=root/"web_workspaces"/session_dir.name
    assert not web_workspace.exists()
    shutil.copytree(candidate/"functional/results",web_workspace,
                    ignore=shutil.ignore_patterns("lab_state.sqlite","service.lock"))
    image_web=ImageService(web_workspace,session_root=board_session.root,assets_root=root/"web_image_assets",
        owner_factory=lambda asset,seed:ImageOwner(board_session,buses,asset,seed,board_lock,candidate))
    web_handle=start(web_workspace,image=image_web,port=8765)
    print("上传图片服务已连接新会话；尚未封存图片计划，未执行CONFIG/ITEM、未发送试验START")
    print("保持内核运行，浏览器打开 http://127.0.0.1:18768/upload")
except BaseException:
    if control_uart.context:control_uart.pause_receiver()
    print("保留现场，不重复执行。证据目录:",board_session.root)
    raise
