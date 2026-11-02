# 等图片页终态、结果生成完成并下载证据后执行。
if image_web.pilot:
    assert image_web.pilot.join(0), "仍在采集或修复，请等待"
    assert image_web.pilot.status()["state"]!="READY", "先在网页停止未执行项"
web_handle.shutdown()
board_session.close()
print("服务和接收器已关闭，请备份完整会话、namespace_allocations.jsonl及trial_registry")
print(board_session.root)
