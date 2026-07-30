from __future__ import annotations

from pathlib import Path

from lidiya_navigator.adapters import MockAdapter
from lidiya_navigator.core import Navigator
from lidiya_navigator.guardian import Guardian
from lidiya_navigator.ledger import WakeLedger
from lidiya_navigator.models import TaskEnvelope, WakeEvent
from lidiya_navigator.task_store import JsonTaskStore
from lidiya_navigator.triggers import completion_event


DATA = Path(__file__).parent / ".runtime"
TASK_ID = "wake-demo-001"


def main() -> None:
    store = JsonTaskStore(DATA / "tasks")
    ledger = WakeLedger(DATA / "wake-ledger.jsonl")
    navigator = Navigator(MockAdapter(), Guardian(), ledger)

    if store.exists(TASK_ID):
        task = store.load(TASK_ID)
    else:
        task = TaskEnvelope(
            task_id=TASK_ID,
            goal="驗證導航可喚醒、回覆、保存並恢復任務",
            completion_criteria=["模型成功回覆", "任務狀態被寫入磁碟"],
            allowed_actions=["model_reply", "write_runtime_state"],
            forbidden_actions=["shell", "network_download", "production_write"],
            max_turns=3,
        )

    event = WakeEvent(event_type="MANUAL_WAKE", source="demo", task_id=TASK_ID, trust_level="internal")
    reply = navigator.handle(event, task, "請執行本輪喚醒測試。")
    store.save(task)
    print(reply.message)
    print(f"state={navigator.state.value}, turn={task.turn_count}")

    if not reply.completed:
        next_event = completion_event(TASK_ID, {"previous_reply": reply.message})
        reply = navigator.handle(next_event, task, "請依前一輪結果繼續，直到符合完成條件。")
        store.save(task)
        print(reply.message)
        print(f"state={navigator.state.value}, turn={task.turn_count}")


if __name__ == "__main__":
    main()
