import QtQuick
import QtTest
import "../ui"

TestCase {
  name: "MiseStatusIcon"
  when: windowShown
  width: 40
  height: 40
  StatusIcon { id: icon; width: 24; height: 24 }
  function test_logo_data() {
    return [
      {tag: "green", level: "green", asset: "green"},
      {tag: "yellow", level: "yellow", asset: "yellow"},
      {tag: "red", level: "red", asset: "red"},
      {tag: "unknown", level: "unknown", asset: "yellow"}
    ]
  }
  function test_logo(data) {
    icon.level = data.level
    tryCompare(icon, "status", Image.Ready)
    verify(icon.source.toString().endsWith("/assets/mise-" + data.asset + ".svg"))
    compare(icon.fillMode, Image.PreserveAspectFit)
    verify(icon.sourceSize.width >= 24)
  }
}
