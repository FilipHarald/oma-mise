import QtQuick
import QtTest
import "../ui"

TestCase {
  name: "CheckSchedule"
  CheckSchedule { id: schedule; intervalSeconds: 1 }
  SignalSpy { id: due; target: schedule; signalName: "checkDue" }
  function test_due_and_busy() {
    schedule.busy = true
    due.clear()
    wait(1200)
    compare(due.count, 0)
    schedule.busy = false
    compare(schedule.remainingSeconds, 1)
    tryCompare(due, "count", 1, 1800)
    schedule.busy = true
  }
}
