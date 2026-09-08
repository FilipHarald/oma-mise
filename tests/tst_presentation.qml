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
}
