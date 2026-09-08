pragma Singleton
import QtQuick
import Quickshell
import Quickshell.Io
import "Presentation.js" as Presentation
import "ui"

Singleton {
  id: root
  property var status: ({level: "yellow", summary: "Checking dotfiles…", details: []})
  readonly property bool refreshing: probe.running || watcherProbe.running
  readonly property int checkIntervalSeconds: 30
  readonly property int remainingSeconds: schedule.remainingSeconds
  property var watcher: ({state: "unknown", can_control: false, error: ""})
  readonly property bool watcherBusy: watcherAction.running || refreshing
  property string controlError: ""
  readonly property color indicatorColor: Presentation.colorFor(status.level)
  readonly property string helper: decodeURIComponent(Qt.resolvedUrl("status.py").toString().replace(/^file:\/\//, ""))
  readonly property string watcherHelper: decodeURIComponent(Qt.resolvedUrl("watcher.py").toString().replace(/^file:\/\//, ""))

  function refresh() {
    if (refreshing || watcherAction.running) return
    probe.start()
    watcherProbe.start()
  }

  function toggleWatcher() {
    if (watcherBusy || !watcher.can_control || (watcher.state !== "running" && watcher.state !== "stopped")) return
    controlError = ""
    watcherAction.command = ["/usr/bin/python3", "-I", "-S", watcherHelper, watcher.state === "running" ? "stop" : "start"]
    watcherAction.start()
  }

  BoundedProcess {
    id: probe
    command: ["/usr/bin/python3", "-I", "-S", root.helper]
    stdoutLimit: 65536
    stderrLimit: 4096
    timeoutMs: 20000
    onCompleted: (output, success) => root.status = Presentation.decode(success ? output : "")
  }
  BoundedProcess {
    id: watcherProbe
    command: ["/usr/bin/python3", "-I", "-S", root.watcherHelper, "status"]
    stdoutLimit: 4096
    stderrLimit: 4096
    timeoutMs: 20000
    onCompleted: (output, success) => root.watcher = Presentation.watcher(success ? output : "")
  }
  BoundedProcess {
    id: watcherAction
    stdoutLimit: 4096
    stderrLimit: 4096
    timeoutMs: 55000
    onCompleted: function(output, success) {
      root.watcher = Presentation.watcher(success ? output : "")
      root.controlError = success ? root.watcher.error : "Could not change watcher state"
      Qt.callLater(root.refresh)
    }
  }
  CheckSchedule {
    id: schedule
    intervalSeconds: root.checkIntervalSeconds
    busy: root.refreshing || watcherAction.running
    onCheckDue: root.refresh()
  }
  Component.onCompleted: refresh()
}
