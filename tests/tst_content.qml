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
  SignalSpy { id: bootstrapSpy; target: content; signalName: "bootstrapRequested" }
  SignalSpy { id: copySpy; target: content; signalName: "copyRequested" }
  function test_copy_commands_not_text_clicks() {
    var original = content.status
    var base = 'mise -C "$HOME" bootstrap dotfiles '
    for (var sample of [["Watcher health needs review", base + "status"],
        ["Sync conflicts need review", base + "status; " + base + "pull --dry-run"],
        ["Pending dotfiles changes need review", base + "status; " + base + "history diff; " + base + "pull --dry-run"],
        ["Sync conflicts need review\nPending dotfiles changes need review", base + "status; " + base + "history diff; " + base + "pull --dry-run"]]) {
      content.status = {summary: "Dotfiles need attention", level: "yellow", details: [sample[0]]}
      var button = findChild(content, "copyCommandButton")
      verify(button !== null)
      waitForRendering(button)
      copySpy.clear()
      mouseClick(findChild(content, "statusHeading"))
      mouseClick(findChild(content, "statusReason"))
      compare(copySpy.count, 0)
      mouseClick(button)
      compare(copySpy.count, 1)
      compare(copySpy.signalArguments[0][0], sample[1])
    }
    content.status = {summary: "Dotfiles synced", level: "green", details: []}
    compare(findChild(content, "copyCommandButton").visible, false)
    content.status = original
  }
  function test_hostile_model_and_plain_text() {
    var original = content.status
    for (var bad of [null, {level: "green", summary: "bad", details: [null]},
        {level: "green", summary: "bad", details: new Array(10000).fill("Last fetch: x")}]) {
      content.status = bad
      compare(findChild(content, "statusHeading").text, "Status unavailable")
    }
    content.status = {level: "yellow", summary: "<img src='file:///missing'>", details: []}
    compare(findChild(content, "statusHeading").text, content.status.summary)
    function check(item) {
      if (item.textFormat !== undefined) compare(item.textFormat, Text.PlainText)
      for (var child of item.children || []) check(child)
    }
    check(content)
    content.status = original
    waitForRendering(content)
  }
  function test_unknown_never_controllable() {
    content.watcherState = "unknown"
    content.watcherCanControl = true
    compare(findChild(content, "watcherButton").enabled, false)
    content.watcherCanControl = false
  }
  function test_date_hover() {
    var original = content.status
    var times = {}
    for (var field of ["publish", "fetch", "apply"]) times[field] = new Date(Date.now() - 5000).toISOString()
    content.status = Object.assign({}, content.status, {timestamps: times})
    for (var field of ["publish", "fetch", "apply"]) {
      var date = findChild(findChild(content, "activity-" + field), "activityDate")
      waitForRendering(date)
      mouseMove(date, date.width - 2, date.height / 2)
      tryVerify(function() { return date.ToolTip.visible })
      verify(/^\d+s$/.test(date.text))
      compare(date.opacity, 0.55)
      verify(/^\d{1,2} [A-Z][a-z]{2} \d{4}, \d{2}:\d{2}$/.test(date.ToolTip.text))
      mouseMove(content, 0, 0)
      tryVerify(function() { return !date.ToolTip.visible })
    }
    content.status = original
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
    compare(findChild(publish, "activityDate").text, "Time unavailable")
    compare(findChild(fetch, "activityDate").text, "Time unavailable")
    compare(findChild(apply, "activityDate").text, "Time unavailable")
    compare(findChild(publish, "activityDate").horizontalAlignment, Text.AlignRight)
    verify(findChild(publish, "activityIcon").text !== findChild(fetch, "activityIcon").text)
    var publishPoint = publish.mapToItem(content, 0, 0)
    var fetchPoint = fetch.mapToItem(content, 0, 0)
    var applyPoint = apply.mapToItem(content, 0, 0)
    compare(Math.round(publishPoint.y), Math.round(fetchPoint.y))
    compare(Math.round(fetchPoint.y), Math.round(applyPoint.y))
    verify(publishPoint.x < fetchPoint.x && fetchPoint.x < applyPoint.x)
    compare(findChild(content, "keyboardHint"), null)
    verify(findChild(content, "filesIcon").text !== "")
    verify(findChild(content, "checkpointsIcon").text !== "")
    verify(findChild(content, "checksSeparator").y < findChild(content, "checksRow").y)
    var files = findChild(content, "filesSection")
    var checkpoints = findChild(content, "checkpointsSection")
    var heading = findChild(content, "statusHeading")
    verify(files.y > apply.y)
    verify(checkpoints.y > files.y)
    verify(files.y >= heading.mapToItem(content, 0, heading.height).y)
    compare(findChild(content, "filesIcon").color, content.foreground)
    var countdown = findChild(content, "countdown")
    var watcher = findChild(content, "watcherLabel")
    var refresh = findChild(content, "refreshButton")
    var watcherPoint = watcher.mapToItem(content, 0, 0)
    var countdownPoint = countdown.mapToItem(content, 0, 0)
    compare(Math.round(watcherPoint.y), Math.round(countdownPoint.y))
    verify(watcherPoint.x > refresh.mapToItem(content, refresh.width, 0).x)
  }
  function test_history_sections_expand_and_collapse() {
    var original = content.status
    var at = new Date(Date.now() - 60000).toISOString()
    content.status = {summary: "Dotfiles synced", level: "green",
      details: ["Files: 7 | Checkpoints: 28"], history_available: true,
      recent_files: [{path: "~/.bashrc", at: at}],
      checkpoints: [{message: "updated shell", at: at}]}
    content.filesExpanded = false
    content.checkpointsExpanded = false
    mouseClick(findChild(content, "filesHeader"))
    verify(content.filesExpanded)
    tryCompare(findChild(content, "filePath"), "text", "~/.bashrc")
    verify(/ ago$/.test(findChild(content, "fileAge").text))
    mouseClick(findChild(content, "checkpointsHeader"))
    verify(content.checkpointsExpanded)
    tryCompare(findChild(content, "checkpointMessage"), "text", "updated shell")
    verify(/ ago$/.test(findChild(content, "checkpointAge").text))
    mouseClick(findChild(content, "filesChevron"))
    mouseClick(findChild(content, "checkpointsChevron"))
    verify(!content.filesExpanded && !content.checkpointsExpanded)
    var filesHeader = findChild(content, "filesHeader")
    filesHeader.forceActiveFocus()
    keyClick(Qt.Key_Return)
    verify(content.filesExpanded)
    keyClick(Qt.Key_Space)
    verify(!content.filesExpanded)
    keyClick(Qt.Key_Enter)
    verify(content.filesExpanded)
    content.clock = 0
    content.panelActive = true
    verify(content.clock > 0)
    content.panelActive = false
    content.status = original
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
  function test_bootstrap_requires_confirmation() {
    var original = content.status
    content.status = {summary: "Dotfiles need attention", level: "yellow",
      details: ["Changed bootstrap declarations need applying"], actions: ["bootstrap"]}
    var button = findChild(content, "bootstrapButton")
    verify(button !== null)
    verify(button.visible)
    waitForRendering(button)
    bootstrapSpy.clear()
    mouseClick(button)
    compare(bootstrapSpy.count, 0)
    verify(content.bootstrapArmed)
    compare(button.text, "Confirm complete bootstrap")
    compare(button.enabled, false)
    mouseClick(button)
    compare(bootstrapSpy.count, 0)
    tryVerify(function() { return button.enabled }, 1000)
    mouseClick(button)
    compare(bootstrapSpy.count, 1)
    verify(!content.bootstrapArmed)
    content.bootstrapBusy = true
    compare(button.enabled, false)
    content.bootstrapBusy = false
    content.status = original
  }
  function test_status_color() {
    content.status = {summary: "Dotfiles error", level: "red", details: []}
    compare(findChild(content, "statusHeading").color, "#ee7373")
  }
  function test_reasons_before_counts() {
    var original = content.status
    content.status = {summary: "Dotfiles error", level: "red", details: ["Files: 7 | Checkpoints: 28", "Last publish: today 13:52", "Sync conflicts need review"]}
    waitForRendering(content)
    var reason = findChild(content, "statusReason")
    verify(reason !== null)
    var files = findChild(content, "filesSection")
    verify(reason.mapToItem(content, 0, reason.height).y < files.y)
    verify(reason.mapToItem(content, 0, 0).y > findChild(content, "statusHeading").mapToItem(content, 0, 0).y)
    content.status = original
  }
  function test_stopped_color() {
    content.watcherState = "stopped"
    compare(findChild(content, "watcherLabel").color, "#7aa2f7")
    compare(findChild(content, "watcherLabel").opacity, 0.55)
    content.status = {summary: "Dotfiles watcher stopped", level: "blue", details: []}
    compare(findChild(content, "statusHeading").color, "#7aa2f7")
  }
}
