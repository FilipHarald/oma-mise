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
    probe.running = true
    watcherProbe.running = true
  }

  function toggleWatcher() {
    if (watcherBusy || !watcher.can_control) return
    controlError = ""
    watcherAction.command = ["python3", watcherHelper, watcher.state === "running" ? "stop" : "start"]
    watcherAction.running = true
  }

  Process {
    id: probe
    command: ["python3", root.helper]
    stdout: StdioCollector {
      onStreamFinished: root.status = Presentation.decode(text)
    }
    onExited: function(exitCode, exitStatus) {
      if (exitCode !== 0 || exitStatus !== 0) root.status = Presentation.decode("")
    }
  }
  Process {
    id: watcherProbe
    command: ["python3", root.watcherHelper, "status"]
    stdout: StdioCollector { onStreamFinished: root.watcher = Presentation.watcher(text) }
  }
  Process {
    id: watcherAction
    stdout: StdioCollector {
      onStreamFinished: {
        root.watcher = Presentation.watcher(text)
        root.controlError = root.watcher.error
      }
    }
    onExited: function(exitCode, exitStatus) {
      if ((exitCode !== 0 || exitStatus !== 0) && root.controlError === "") root.controlError = "Could not change watcher state"
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
