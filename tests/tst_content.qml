import QtQuick
import QtQuick.Controls
import QtTest
import "../ui"

TestCase {
  name: "StatusContent"
  when: windowShown
  visible: true
  width: 480
  height: 600
  StatusContent {
    id: content
    width: 420
    status: ({summary: "Dotfiles synced", level: "green", checked_label: "today 14:00", details: ["Files: 7 | Checkpoints: 28", "Watcher: running", "Last publish: today 13:52", "Last fetch: yesterday 09:00", "Last apply: 4 sep 08:03"]})
  }
  SignalSpy { id: refreshSpy; target: content; signalName: "refreshRequested" }
  SignalSpy { id: watcherSpy; target: content; signalName: "watcherToggleRequested" }
  function test_date_hover() {
    var times = {}
    for (var field of ["publish", "fetch", "apply"]) times[field] = new Date(Date.now() - 5000).toISOString()
    content.status = Object.assign({}, content.status, {timestamps: times})
    for (var field of ["publish", "fetch", "apply"]) {
      var date = findChild(findChild(content, "activity-" + field), "activityDate")
      waitForRendering(date)
      mouseMove(date, date.width - 2, date.height / 2)
      tryVerify(function() { return date.ToolTip.visible })
      verify(/^\d+s ago$/.test(date.ToolTip.text))
      var first = date.ToolTip.text
      tryVerify(function() { return date.ToolTip.text !== first }, 2000)
      mouseMove(content, 0, 0)
      tryVerify(function() { return !date.ToolTip.visible })
    }
  }
  function test_footer_hover() {
    content.watcherState = "running"
    content.watcherCanControl = true
    var watcher = findChild(content, "watcherLabel")
    var countdown = findChild(content, "countdown")
    compare(watcher.color, countdown.color)
    compare(watcher.opacity, countdown.opacity)
    for (var pair of [[countdown, "refreshButton"], [watcher, "watcherButton"]]) {
      waitForRendering(pair[0])
      mouseMove(pair[0], 2, pair[0].height / 2)
      var button = findChild(content, pair[1])
      tryVerify(function() { return button.ToolTip.visible })
      mouseMove(content, 0, 0)
      tryVerify(function() { return !button.ToolTip.visible })
    }
  }
  function test_watcher_toggle() {
    content.watcherState = "running"
    content.watcherCanControl = true
    var button = findChild(content, "watcherButton")
    compare(button.text, "\uf04c")
    compare(findChild(content, "watcherLabel").text, "Watcher running")
    waitForRendering(button)
    watcherSpy.clear()
    mouseClick(button)
    compare(watcherSpy.count, 1)
    mouseClick(findChild(content, "watcherLabel"))
    compare(watcherSpy.count, 2)
    content.watcherState = "stopped"
    compare(button.text, "\uf04b")
    content.watcherBusy = true
    compare(button.enabled, false)
    content.watcherBusy = false
    content.watcherCanControl = false
    compare(button.enabled, false)
    mouseClick(findChild(content, "watcherLabel"))
    compare(watcherSpy.count, 2)
  }
  function test_layout() {
    compare(findChild(content, "title").text, "Mise status")
    compare(findChild(content, "statusHeading").text, "Dotfiles synced")
    compare(findChild(content, "title").font.pixelSize, findChild(content, "countdown").font.pixelSize)
    compare(findChild(content, "title").opacity, findChild(content, "countdown").opacity)
    var publish = findChild(content, "activity-publish")
    var fetch = findChild(content, "activity-fetch")
    var apply = findChild(content, "activity-apply")
    verify(publish !== null && fetch !== null && apply !== null)
    compare(findChild(publish, "activityDate").text, "today 13:52")
    compare(findChild(fetch, "activityDate").text, "yesterday 09:00")
    compare(findChild(apply, "activityDate").text, "4 sep 08:03")
    compare(findChild(publish, "activityDate").horizontalAlignment, Text.AlignRight)
    verify(findChild(publish, "activityIcon").text !== findChild(fetch, "activityIcon").text)
    compare(findChild(content, "keyboardHint"), null)
    verify(findChild(content, "filesIcon").text !== "")
    verify(findChild(content, "checkpointsIcon").text !== "")
    verify(findChild(content, "checksSeparator").y < findChild(content, "checksRow").y)
    var counts = findChild(content, "filesIcon").parent
    var heading = findChild(content, "statusHeading")
    verify(counts.mapToItem(content, 0, 0).y >= heading.mapToItem(content, 0, heading.height).y)
    verify(counts.mapToItem(content, 0, counts.height).y <= publish.y)
    compare(findChild(content, "filesIcon").color, content.foreground)
    var countdown = findChild(content, "countdown")
    var watcher = findChild(content, "watcherLabel")
    var refresh = findChild(content, "refreshButton")
    var watcherPoint = watcher.mapToItem(content, 0, 0)
    var countdownPoint = countdown.mapToItem(content, 0, 0)
    compare(Math.round(watcherPoint.y), Math.round(countdownPoint.y))
    verify(watcherPoint.x > refresh.mapToItem(content, refresh.width, 0).x)
  }
  function test_refresh() {
    refreshSpy.clear()
    var button = findChild(content, "refreshButton")
    waitForRendering(button)
    mouseClick(button)
    compare(refreshSpy.count, 1)
    mouseClick(findChild(content, "countdown"))
    compare(refreshSpy.count, 2)
    content.refreshing = true
    compare(button.enabled, false)
    mouseClick(findChild(content, "countdown"))
    compare(refreshSpy.count, 2)
    content.refreshing = false
  }
  function test_status_color() {
    content.status = {summary: "Dotfiles error", level: "red", details: []}
    compare(findChild(content, "statusHeading").color, "#ee7373")
  }
}
