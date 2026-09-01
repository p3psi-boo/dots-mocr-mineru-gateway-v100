from dotmocr_api.service_logs import ServiceLogBuffer


def test_service_log_buffer_returns_recent_and_incremental_entries():
    logs = ServiceLogBuffer(capacity=100)
    first = logs.emit("info", "gateway", "started", version="test")
    second = logs.emit("warning", "queue", "busy", queued=2)

    recent = logs.read(limit=1)
    assert recent["items"] == [second.as_dict()]
    assert recent["latest_sequence"] == 2

    incremental = logs.read(after=first.sequence)
    assert incremental["items"] == [second.as_dict()]
    assert incremental["instance_id"] == logs.instance_id
