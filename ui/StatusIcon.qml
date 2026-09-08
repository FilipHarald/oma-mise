import QtQuick

Image {
  property string level: "yellow"
  source: Qt.resolvedUrl("../assets/mise-" + (["green", "yellow", "red", "blue"].indexOf(level) >= 0 ? level : "yellow") + ".svg")
  fillMode: Image.PreserveAspectFit
  sourceSize.width: Math.ceil(width * Screen.devicePixelRatio)
  sourceSize.height: Math.ceil(height * Screen.devicePixelRatio)
  smooth: true
}
