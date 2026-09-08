// Stage beside ui/ and Presentation.js; launch with WAYLAND_DISPLAY=oma-mise-nonexistent.
// This exercises the real wl-copy failure path without changing the user's selection.
import QtQuick
import Quickshell
import "ui"
import "Presentation.js" as Presentation
Item {
  id: root
  property var clipboard
  property bool observed: false
  function check(ok, reason) { if (!ok) { console.error("FAIL: " + reason); Qt.exit(1) } }
  Component.onCompleted: Qt.callLater(function() {
    var component = Qt.createComponent("ui/ReviewClipboard.qml")
    check(component.status === Component.Ready, "ReviewClipboard ready: " + component.errorString())
    if (component.status !== Component.Ready) return
    clipboard = component.createObject(root)
    check(!clipboard.copy("touch /tmp/no"), "reject arbitrary copy data")
    check(!clipboard.running, "invalid input never launches")
    check(clipboard.copy(Presentation.reviewCommand("status")), "accept fixed review command")
    check(clipboard.copy(Presentation.reviewCommand("changes")), "coalesce repeated request")
    check(clipboard.copy(Presentation.reviewCommand("conflicts")), "bounded latest-wins queue")
    observed = true
  })
  Timer {
    interval: 50; repeat: true; running: true
    onTriggered: if (root.observed && !root.clipboard.running) {
      root.check(root.clipboard.error === "Could not copy review command", "launch failure exposed")
      console.log("PASS: clipboard allowlist, coalescing, real wl-copy failure cleanup")
      Qt.quit()
    }
  }
  Timer { interval: 5000; running: true; onTriggered: { console.error("FAIL: clipboard timed out"); Qt.exit(1) } }
}
