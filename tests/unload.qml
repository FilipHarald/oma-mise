// Stage this file as shell.qml beside ui/BoundedProcess.qml; no Wayland access.
import QtQuick
import Quickshell
import "ui"
Item {
  id: root
  property var victim
  property string pid: ""
  Component.onCompleted: Qt.callLater(function() {
    var component = Qt.createComponent("ui/BoundedProcess.qml")
    victim = component.createObject(root, {
      persistent: true, stdoutLimit: 32,
      command: ["/usr/bin/python3", "-I", "-S", "-c",
        "import os,signal,time; signal.signal(signal.SIGTERM,signal.SIG_IGN); print(os.getpid(),flush=True); time.sleep(30)"]
    })
    victim.start()
  })
  Timer {
    interval: 50; repeat: true; running: true
    onTriggered: if (root.victim && /^\d+\n$/.test(root.victim.output)) {
      root.pid = root.victim.output.trim()
      root.victim.destroy()
      root.victim = null
      settle.start()
      stop()
    }
  }
  Timer {
    id: settle
    interval: 150
    onTriggered: {
      observer.command = ["/usr/bin/python3", "-I", "-S", "-c",
        "import os,sys; raise SystemExit(1 if os.path.exists('/proc/'+sys.argv[1]) else 0)", root.pid]
      observer.start()
    }
  }
  BoundedProcess {
    id: observer
    onCompleted: function(output, success) {
      if (!success) { console.error("FAIL: unload left owned process alive"); Qt.exit(1); return }
      console.log("PASS: unload kills and reaps TERM-ignoring owned process")
      Qt.quit()
    }
  }
  Timer { interval: 5000; running: true; onTriggered: { console.error("FAIL: unload test timed out"); Qt.exit(1) } }
}
