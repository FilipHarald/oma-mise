import QtQuick

QtObject {
  id: root
  property int intervalSeconds: 30
  property bool busy: false
  property double now: Date.now()
  property double nextCheckAt: now + intervalSeconds * 1000
  readonly property int remainingSeconds: busy ? 0 : Math.max(0, Math.ceil((nextCheckAt - now) / 1000))
  signal checkDue()
  function reset() {
    now = Date.now()
    nextCheckAt = now + intervalSeconds * 1000
  }
  onBusyChanged: if (!busy) reset()
  onIntervalSecondsChanged: reset()
  Component.onCompleted: reset()
  property Timer ticker: Timer {
    interval: 250
    running: true
    repeat: true
    onTriggered: {
      root.now = Date.now()
      if (!root.busy && root.remainingSeconds === 0) {
        root.reset()
        root.checkDue()
      }
    }
  }
}
