import QtQuick
import QtTest
import "../ui"

TestCase {
  name: "MiseStatusIcon"
  when: windowShown
  width: 40
  height: 40
  StatusIcon { id: icon; width: 24; height: 24; foreground: "#d8d8d8" }
  function test_logo_data() {
    return [
      {tag: "green", level: "green", color: "#d8d8d8"},
      {tag: "yellow", level: "yellow", color: "#e5bf69"},
      {tag: "red", level: "red", color: "#ee7373"},
      {tag: "blue", level: "blue", color: "#d8d8d8"},
      {tag: "unknown", level: "unknown", color: "#d8d8d8"}
    ]
  }
  function test_logo(data) {
    icon.level = data.level
    var image = findChild(icon, "logoSource")
    tryCompare(image, "status", Image.Ready)
    verify(image.source.toString().endsWith("/assets/mise-green.svg"))
    compare(icon.displayColor.toString(), data.color)
    compare(image.fillMode, Image.PreserveAspectFit)
    verify(image.sourceSize.width >= 24)
  }
}
