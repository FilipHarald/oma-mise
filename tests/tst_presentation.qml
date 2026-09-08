import QtQuick
import QtTest
import "../Presentation.js" as Presentation

TestCase {
  name: "StatusPresentation"
  function test_age() {
    var now = Date.parse("2026-09-08T14:00:00Z")
    compare(Presentation.age("2026-09-08T12:58:57Z", now), "1h ago")
    for (var entry of [[0, "0s"], [59, "59s"], [60, "1m"], [3599, "59m"], [3600, "1h"], [86399, "23h"], [86400, "1d"], [259261, "3d"]]) {
      compare(Presentation.age(new Date(now - entry[0] * 1000).toISOString(), now), entry[1] + " ago")
    }
    compare(Presentation.age("2026-09-08T13:59:55Z", now), "5s ago")
    compare(Presentation.age("2026-09-08T14:00:05Z", now), "in 5s")
    compare(Presentation.age(null, now), "Time unavailable")
    compare(Presentation.age("invalid", now), "Time unavailable")
  }
  function test_duration() {
    compare(Presentation.duration(30), "30s")
    compare(Presentation.duration(65), "1m 5s")
    compare(Presentation.duration(3661), "1h 1m 1s")
    compare(Presentation.duration(0), "0s")
  }
  function test_watcher_payload() {
    compare(Presentation.watcher('{"state":"running","can_control":true,"error":""}').state, "running")
    compare(Presentation.watcher('bad').can_control, false)
    compare(Presentation.watcher('{"state":"running"}').can_control, false)
  }
  function test_decode() {
    compare(Presentation.decode('{"level":"green","summary":"Synced","details":[]}').level, "green")
    compare(Presentation.decode('broken').level, "yellow")
    compare(Presentation.decode('{"level":"green"}').level, "yellow")
    compare(Presentation.decode('{"level":"blue","summary":"Stopped","details":[]}').level, "blue")
    compare(Presentation.decode('{"level":"invalid","summary":"Oops","details":[]}').level, "yellow")
  }
  function test_colors() {
    compare(Presentation.colorFor("green"), "#72c78b")
    compare(Presentation.colorFor("yellow"), "#e5bf69")
    compare(Presentation.colorFor("red"), "#ee7373")
    compare(Presentation.colorFor("blue"), "#7aa2f7")
    compare(Presentation.colorFor("unknown"), "#e5bf69")
  }
  function test_reject_malformed_model() {
    for (var details of [[null], [{}], [42], new Array(33).fill("x"), ["x".repeat(1025)]]) {
      compare(Presentation.decode(JSON.stringify({level: "green", summary: "Synced", details: details})).summary, "Status unavailable")
    }
    compare(Presentation.decode("null").summary, "Status unavailable")
  }
  function test_host_tooltip() {
    compare(typeof Presentation.hostTooltip, "function")
    var text = Presentation.hostTooltip("<img>&\u0000\u202e" + "x".repeat(10000))
    verify(text.length <= 256)
    verify(!/[<>&\u0000\u202e]/.test(text))
  }
  function test_clipboard_allowlist() {
    compare(typeof Presentation.isReviewCommand, "function")
    var base = 'mise -C "$HOME" bootstrap dotfiles '
    verify(Presentation.isReviewCommand(base + "status"))
    verify(Presentation.isReviewCommand(base + "status; " + base + "pull --dry-run"))
    verify(Presentation.isReviewCommand(base + "status; " + base + "history diff; " + base + "pull --dry-run"))
    for (var text of ["", "rm -rf ~", base + "pull", base + "status; touch /tmp/no", "--help", null])
      verify(!Presentation.isReviewCommand(text))
  }
  function test_strict_schema() {
    var base = {level: "green", summary: "Synced", details: []}
    for (var extra of [{summary: "x".repeat(257)}, {summary: "bad\u202e"},
        {checked_at: 12}, {checked_at: "2026-02-30T12:00:00Z"},
        {checked_at: "2026-09-08T12:00:00"}, {checked_label: null},
        {timestamps: null}, {timestamps: {publish: [], fetch: null, apply: null}},
        {timestamps: {publish: null, fetch: null, apply: null, other: 1}},
        {extra: {nested: []}}, {details: ["Files: 999999999999999999 | Checkpoints: 1"]}]) {
      compare(Presentation.decode(JSON.stringify(Object.assign({}, base, extra))).summary, "Status unavailable")
    }
    var valid = Object.assign({}, base, {checked_at: "2026-09-08T12:00:00.123456+02:00",
      timestamps: {publish: null, fetch: "2026-09-08T12:00:00Z", apply: null}})
    compare(Presentation.decode(JSON.stringify(valid)).summary, "Synced")
    for (var data of [{state: "unknown", can_control: true, error: ""},
        {state: "running", can_control: "true", error: ""},
        {state: "running", can_control: true, error: "x".repeat(513)},
        {state: "stopped", can_control: true, error: "", extra: 1}]) {
      compare(Presentation.watcher(JSON.stringify(data)).can_control, false)
    }
  }
  function test_duplicate_keys_and_parse_depth() {
    compare(Presentation.watcher('{"state":"running","can_control":false,"can_control":true,"error":""}').can_control, false)
    compare(Presentation.decode('{"level":"red","level":"green","summary":"Synced","details":[]}').summary, "Status unavailable")
    compare(typeof Presentation.parsePayload, "function")
    var refused = false
    try { Presentation.parsePayload('{"details":[[[[]]]]}', 65536) } catch (e) { refused = true }
    verify(refused)
    compare(Presentation.decode('{"level":"green","summary":"brackets [] {} and \\"quotes\\"","details":[]}').level, "green")
  }
}
