// Stage this file beside a copy of ui/ as shell.qml, then run quickshell -p there.
import QtQuick
import Quickshell
import "ui"

Item {
  id: root
  property var child
  property int index: 0
  property double began: 0
  property var cases: [
    {name: "clean", script: "print('ok', end='')", ok: true, text: "ok"},
    {name: "stdout newline-free overflow", script: "import os; os.write(1, b'x'*1000000)", ok: false},
    {name: "stderr newline-free overflow", script: "import os; os.write(2, b'x'*1000000)", ok: false},
    {name: "watchdog and KILL escalation", script: "import signal,time; signal.signal(signal.SIGTERM, signal.SIG_IGN); time.sleep(30)", ok: false},
    {name: "nonzero", script: "print('untrusted'); raise SystemExit(1)", ok: false},
    {name: "failed launch", missing: true, ok: false},
    {name: "cancel failed launch safely", missing: true, cancel: true, ok: false},
    {name: "persistent ownership survives watchdog", script: "import time; time.sleep(30)", persistent: true, ok: false},
    {name: "UTF-8 byte overflow", script: "import os; os.write(1, ('é'*33).encode())", ok: false},
    {name: "environment isolation", script: "import os; assert os.environ['PATH']=='/usr/bin:/bin'; assert 'PYTHONPATH' not in os.environ; assert 'LD_PRELOAD' not in os.environ; print('safe',end='')", ok: true, text: "safe"}
  ]
  function check(value, message) {
    if (!value) { console.error("FAIL: " + message); Qt.exit(1) }
  }
  function next() {
    if (index === cases.length) { console.log("PASS: all runtime cases"); Qt.quit(); return }
    var sample = cases[index]
    child.persistent = sample.persistent === true
    began = Date.now()
    child.command = sample.missing ? ["/nonexistent-oma-mise-test"] : ["/usr/bin/python3", "-I", "-S", "-c", sample.script]
    check(child.start(), "start " + sample.name)
    check(!child.start(), "single flight " + sample.name)
    if (sample.cancel) child.stop()
    if (sample.persistent) ownershipTimer.start()
  }
  Component.onCompleted: {
    var component = Qt.createComponent("ui/BoundedProcess.qml")
    check(component.status === Component.Ready, "BoundedProcess ready: " + component.errorString())
    if (component.status !== Component.Ready) return
    child = component.createObject(root, {stdoutLimit: 64, stderrLimit: 64, timeoutMs: 300, killGraceMs: 100})
    check(typeof child.signalOwned === "function", "guarded process signal API")
    if (typeof child.signalOwned !== "function") return
    check(!child.signalOwned(15), "never signal pid zero before launch")
    child.outputChanged.connect(function() { check(child.output.length <= 64, "reject overflow BEFORE concatenation") })
    child.completed.connect(function(output, success) {
      var sample = cases[index]
      check(success === sample.ok, sample.name + " success")
      check(output.length <= 64, "bounded retention")
      if (sample.text !== undefined) check(output === sample.text, "complete stdout")
      if (!success) check(output === "", "fail-closed output")
      check(child.stdoutBytes <= 64 && child.stderrBytes <= 64, "counters never cross cap")
      if (sample.name === "watchdog and KILL escalation") check(Date.now() - began >= 350, "TERM grace precedes KILL")
      console.log("PASS: " + sample.name)
      index++
      Qt.callLater(next)
    })
    next()
  }
  Timer { running: true; interval: 10000; onTriggered: { console.error("FAIL: runtime suite timed out"); Qt.exit(1) } }
  Timer {
    id: ownershipTimer
    interval: 650
    onTriggered: {
      root.check(root.child.running, "persistent process not killed by transfer timeout")
      root.child.stop()
    }
  }
}
