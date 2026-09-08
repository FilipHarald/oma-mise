import QtQuick
import Quickshell
import Quickshell.Io

// One owned process, no line buffering. Helpers additionally bound raw bytes and
// supervise their descendant groups; Process.signal only addresses the leader.
Item {
  id: root
  property var command: []
  property int stdoutLimit: 65536
  property int stderrLimit: 4096
  property int timeoutMs: 20000
  property int killGraceMs: 1000
  // Clipboard ownership is intentionally long-lived once the executable starts.
  property bool persistent: false
  readonly property bool running: active
  property bool active: false
  property bool failed: false
  property string output: ""
  property int stdoutBytes: 0
  property int stderrBytes: 0
  signal completed(string output, bool success)
  signal started()

  readonly property var environment: {
    var env = {PATH: "/usr/bin:/bin", LANG: "C.UTF-8", LC_ALL: "C.UTF-8"}
    // Do not inherit loader/interpreter injection, command overrides or proxies.
    for (var key of ["HOME", "XDG_RUNTIME_DIR", "XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_STATE_HOME", "XDG_CACHE_HOME"]) {
      var value = Quickshell.env(key)
      if (value && value.length <= 4096 && value[0] === "/" && !/[\u0000-\u001f\u007f]/.test(value)) env[key] = value
    }
    var display = Quickshell.env("WAYLAND_DISPLAY")
    if (display && /^[A-Za-z0-9_.-]{1,128}$/.test(display)) env.WAYLAND_DISPLAY = display
    // systemctl discovers the user bus from XDG_RUNTIME_DIR. Never inherit an
    // arbitrary DBUS_SESSION_BUS_ADDRESS (which could name a remote bus).
    return env
  }

  function start() {
    if (active || process.running) return false
    output = ""
    stdoutBytes = 0
    stderrBytes = 0
    failed = false
    active = true
    watchdog.restart() // includes executable startup, not just onStarted
    process.running = true
    return true
  }
  function signalOwned(number) {
    // The installed API directly calls kill(processId, signal). During startup
    // processId may be zero: never turn a leader signal into a group-wide kill.
    if (!process.running || !(Number(process.processId) > 0)) return false
    process.signal(number)
    return true
  }
  function stop() {
    if (!active || failed) return
    failed = true
    output = ""
    watchdog.stop()
    signalOwned(15)
    escalation.restart()
  }
  function chunk(data, stderr) {
    if (!active || failed) return
    var remaining = (stderr ? stderrLimit - stderrBytes : stdoutLimit - stdoutBytes)
    // QString is decoded UTF-8. Count re-encoded bytes without allocating another
    // string, conservatively charging unmatched surrogates as three bytes.
    // Helpers emit ASCII JSON, so their output has exact byte accounting here.
    var bytes = 0
    for (var i = 0; i < data.length; i++) {
      var code = data.charCodeAt(i)
      if (code < 128) bytes++
      else if (code < 2048) bytes += 2
      else if (code >= 0xd800 && code <= 0xdbff && i + 1 < data.length
               && data.charCodeAt(i + 1) >= 0xdc00 && data.charCodeAt(i + 1) <= 0xdfff) { bytes += 4; i++ }
      else bytes += 3
      if (bytes > remaining) { stop(); return }
    }
    if (stderr) stderrBytes += bytes // discard bounded diagnostics; never log them
    else { stdoutBytes += bytes; output += data } // only concatenate AFTER budget check
  }
  function finish(success) {
    if (!active) return
    var result = success && !failed ? output : ""
    var ok = success && !failed
    watchdog.stop()
    escalation.stop()
    output = ""
    active = false
    completed(result, ok)
  }
  Process {
    id: process
    command: root.command
    clearEnvironment: true
    environment: root.environment
    stdinEnabled: false
    stdout: SplitParser { splitMarker: ""; onRead: data => root.chunk(data, false) }
    stderr: SplitParser { splitMarker: ""; onRead: data => root.chunk(data, true) }
    onStarted: {
      if (root.failed) root.signalOwned(15)
      if (root.persistent) watchdog.stop()
      root.started()
    }
    onExited: (code, status) => root.finish(code === 0 && status === 0)
    // FailedToStart has no exited signal in the installed Process API.
    onRunningChanged: if (!running && root.active) Qt.callLater(function() {
      if (!process.running && root.active) root.finish(false)
    })
  }
  Timer { id: watchdog; interval: root.timeoutMs; onTriggered: root.stop() }
  Timer {
    id: escalation
    interval: root.killGraceMs
    onTriggered: {
      if (!process.running) root.finish(false)
      else if (!root.signalOwned(9)) escalation.restart()
    }
  }
  Component.onDestruction: {
    // Timers cannot outlive this component. Quickshell's Process destructor
    // KILLs/reaps the owned leader; Python's parent-death supervisor cleans groups.
    root.signalOwned(15)
  }
}
