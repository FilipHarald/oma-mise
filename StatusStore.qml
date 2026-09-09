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
  readonly property bool bootstrapBusy: bootstrapAction.running
  readonly property bool watcherBusy: watcherAction.running || bootstrapBusy || refreshing
  property string controlError: ""
  property string bootstrapError: ""
  readonly property color indicatorColor: Presentation.colorFor(status.level)
  readonly property string helper: decodeURIComponent(Qt.resolvedUrl("status.py").toString().replace(/^file:\/\//, ""))
  readonly property string watcherHelper: decodeURIComponent(Qt.resolvedUrl("watcher.py").toString().replace(/^file:\/\//, ""))
  readonly property string bootstrapHelper: decodeURIComponent(Qt.resolvedUrl("bootstrap.py").toString().replace(/^file:\/\//, ""))

  function refresh() {
    if (refreshing || watcherAction.running || bootstrapBusy) return
    probe.start()
    watcherProbe.start()
  }

  function toggleWatcher() {
    if (watcherBusy || !watcher.can_control || (watcher.state !== "running" && watcher.state !== "stopped")) return
    controlError = ""
    watcherAction.command = ["/usr/bin/python3", "-I", "-S", watcherHelper, watcher.state === "running" ? "stop" : "start"]
    watcherAction.start()
  }

  function runBootstrap() {
    if (bootstrapBusy || refreshing || watcherAction.running
        || !status.actions || status.actions.indexOf("bootstrap") === -1) return
    bootstrapError = ""
    bootstrapAction.start()
  }

  BoundedProcess {
    id: probe
    command: ["/usr/bin/python3", "-I", "-S", root.helper]
    stdoutLimit: 65536
    stderrLimit: 4096
    timeoutMs: 40000
    onCompleted: function(output, success) {
      var nextStatus = Presentation.decode(success ? output : "")
      root.status = nextStatus
      if (success && nextStatus.summary !== "Status unavailable"
          && (!nextStatus.actions || nextStatus.actions.indexOf("bootstrap") === -1)) root.bootstrapError = ""
    }
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
  BoundedProcess {
    id: bootstrapAction
    command: ["/usr/bin/python3", "-I", "-S", root.bootstrapHelper, "apply"]
    stdoutLimit: 4096
    stderrLimit: 4096
    timeoutMs: 900000
    onCompleted: function(output, success) {
      var result = Presentation.actionResult(success ? output : "")
      root.bootstrapError = result.ok ? "" : result.error
      Qt.callLater(root.refresh)
    }
  }
  CheckSchedule {
    id: schedule
    intervalSeconds: root.checkIntervalSeconds
    busy: root.refreshing || watcherAction.running || bootstrapAction.running
    onCheckDue: root.refresh()
  }
  Component.onCompleted: refresh()
}
