import QtQuick
import "../Presentation.js" as Presentation

// Exactly one foreground Wayland selection owner, plus one bounded replacement.
// It is not a helper: ownership must outlive the initial copy and no review
// command is executed. Removing the plugin terminates its selection owner.
Item {
  id: root
  readonly property bool running: owner.running || pending !== ""
  property string pending: ""
  property string error: ""
  function copy(command) {
    if (!Presentation.isReviewCommand(command)) return false
    pending = command
    error = ""
    if (owner.running) owner.stop()
    else launchPending()
    return true
  }
  function launchPending() {
    if (owner.running || pending === "") return
    var text = pending
    pending = ""
    // Explicit MIME avoids wl-copy spawning `file` for MIME detection.
    owner.command = ["/usr/bin/wl-copy", "--foreground", "--type", "text/plain", "--", text]
    owner.start()
  }
  BoundedProcess {
    id: owner
    persistent: true
    timeoutMs: 3000
    stdoutLimit: 4096
    stderrLimit: 4096
    onCompleted: function(output, success) {
      if (!success && root.pending === "") root.error = "Could not copy review command"
      Qt.callLater(root.launchPending)
    }
  }
  Component.onDestruction: pending = ""
}
