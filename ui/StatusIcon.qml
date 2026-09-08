import QtQuick
import QtQuick.Effects

Item {
  id: root
  property string level: "yellow"
  property color foreground: "#ffffff"
  readonly property color displayColor: level === "red" ? "#ee7373"
    : level === "yellow" ? "#e5bf69" : foreground

  Image {
    id: logoSource
    objectName: "logoSource"
    anchors.fill: parent
    source: Qt.resolvedUrl("../assets/mise-green.svg")
    fillMode: Image.PreserveAspectFit
    sourceSize.width: Math.ceil(width * Screen.devicePixelRatio)
    sourceSize.height: Math.ceil(height * Screen.devicePixelRatio)
    smooth: true
    visible: false
    layer.enabled: true
  }

  MultiEffect {
    anchors.fill: logoSource
    source: logoSource
    colorization: 1.0
    colorizationColor: root.displayColor
  }
}
