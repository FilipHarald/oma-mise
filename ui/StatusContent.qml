import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "../Presentation.js" as Presentation

Column {
  id: root
  property var status: ({summary: "Checking dotfiles…", level: "yellow", details: []})
  property bool refreshing: false
  property string watcherState: "unknown"
  property bool watcherCanControl: false
  property bool watcherBusy: false
  property string watcherError: ""
  property int remainingSeconds: 30
  property color foreground: "#ffffff"
  property string fontFamily: "monospace"
  property int bodySize: 14
  property int captionSize: 12
  property real unit: 1
  readonly property var counts: {
    var lines = root.status.details || []
    for (var i = 0; i < lines.length; i++) {
      var match = /^Files: (\d+|unknown) \| Checkpoints: (\d+|unknown)$/.exec(lines[i])
      if (match) return match
    }
    return null
  }
  signal refreshRequested()
  signal watcherToggleRequested()
  spacing: 12 * unit

  Text {
    objectName: "title"
    text: "Mise status"
    textFormat: Text.PlainText
    color: root.foreground
    opacity: 0.55
    font.family: root.fontFamily
    font.pixelSize: root.captionSize
  }
  Column {
    width: parent.width
    spacing: 5 * root.unit
    Text {
      objectName: "statusHeading"
      width: parent.width
      text: root.status.summary
      textFormat: Text.PlainText
      elide: Text.ElideRight
      color: Presentation.colorFor(root.status.level)
      font.family: root.fontFamily
      font.pixelSize: root.bodySize
      font.bold: true
    }
    Text {
      objectName: "statusReason"
      width: parent.width
      text: (root.status.details || []).filter(function(line) {
        return line.indexOf("Watcher: ") !== 0
          && !/^Files: (\d+|unknown) \| Checkpoints: (\d+|unknown)$/.test(line)
          && !/^Last (publish|fetch|apply): /.test(line)
      }).join("\n")
      visible: text !== ""
      textFormat: Text.PlainText
      wrapMode: Text.Wrap
      color: root.foreground
      font.family: root.fontFamily
      font.pixelSize: root.captionSize
    }
    Text {
      visible: root.watcherError !== ""
      width: parent.width
      text: root.watcherError
      textFormat: Text.PlainText
      wrapMode: Text.Wrap
      color: Presentation.colorFor("red")
      font.family: root.fontFamily
      font.pixelSize: root.captionSize
    }
  }
    Row {
      anchors.horizontalCenter: parent.horizontalCenter
      visible: root.counts !== null
      spacing: 8 * root.unit
      Text {
        objectName: "filesIcon"
        text: "\uf0c5"
        color: root.foreground
        font.family: root.fontFamily
        font.pixelSize: root.captionSize
      }
      Text {
        text: root.counts ? "Files: " + root.counts[1] : ""
        color: root.foreground
        font.family: root.fontFamily
        font.pixelSize: root.captionSize
      }
      Text {
        objectName: "checkpointsIcon"
        text: "\uf1da"
        leftPadding: 8 * root.unit
        color: root.foreground
        font.family: root.fontFamily
        font.pixelSize: root.captionSize
      }
      Text {
        text: root.counts ? "Checkpoints: " + root.counts[2] : ""
        color: root.foreground
        font.family: root.fontFamily
        font.pixelSize: root.captionSize
      }
    }
  Row {
    id: watcherControls
    HoverHandler { id: watcherHover }
    parent: footer
    anchors.right: parent.right
    anchors.verticalCenter: parent.verticalCenter
    spacing: 6 * root.unit
    Text {
      objectName: "watcherLabel"
      anchors.verticalCenter: parent.verticalCenter
      text: "Watcher " + root.watcherState
      color: root.watcherState === "stopped" ? Presentation.colorFor("blue") : root.foreground
      opacity: 0.55
      font.family: root.fontFamily
      font.pixelSize: root.captionSize
      MouseArea {
        anchors.fill: parent
        enabled: watcherButton.enabled
        cursorShape: Qt.PointingHandCursor
        onClicked: root.watcherToggleRequested()
      }
    }
    ToolButton {
      id: watcherButton
      objectName: "watcherButton"
      width: 24 * root.unit
      height: 24 * root.unit
      text: root.watcherState === "running" ? "\uf04c" : "\uf04b"
      enabled: root.watcherCanControl && !root.watcherBusy
      focusPolicy: Qt.NoFocus
      hoverEnabled: true
      Accessible.name: root.watcherState === "running" ? "Pause watcher" : "Resume watcher"
      ToolTip.visible: watcherHover.hovered
      ToolTip.text: root.watcherState === "running" ? "Pause automatic saving and syncing" : "Resume automatic saving and syncing"
      contentItem: Text {
        text: watcherButton.text
        horizontalAlignment: Text.AlignHCenter
        verticalAlignment: Text.AlignVCenter
        color: root.watcherState === "stopped" ? Presentation.colorFor("blue") : root.foreground
        opacity: watcherButton.enabled ? 0.8 : 0.35
        font.family: root.fontFamily
        font.pixelSize: root.captionSize
      }
      onClicked: root.watcherToggleRequested()
    }
  }
  Repeater {
    model: (root.status.details || []).filter(function(line) { return /^Last (publish|fetch|apply): /.test(line) })
    delegate: Item {
      id: detail
      required property string modelData
      readonly property var match: /^(Last (publish|fetch|apply)): (.*)$/.exec(modelData)
      readonly property bool activity: match !== null

      objectName: activity ? "activity-" + match[2] : "detail"
      width: root.width
      implicitHeight: activity ? activityRow.implicitHeight : plain.implicitHeight
      Text {
        id: plain
        visible: !detail.activity
        width: parent.width
        text: detail.activity ? "" : detail.modelData
        textFormat: Text.PlainText
        wrapMode: Text.Wrap
        color: root.foreground
        font.family: root.fontFamily
        font.pixelSize: root.captionSize
      }

      RowLayout {
        id: activityRow
        visible: detail.activity
        width: parent.width
        spacing: 8 * root.unit
        Text {
          objectName: "activityIcon"
          text: !detail.activity ? "" : detail.match[2] === "publish" ? "\uf093" : detail.match[2] === "fetch" ? "\uf019" : "\uf00c"
          textFormat: Text.PlainText
          color: root.foreground
          font.family: root.fontFamily
          font.pixelSize: root.captionSize
          Layout.preferredWidth: 16 * root.unit
          horizontalAlignment: Text.AlignHCenter
        }
        Text {
          text: detail.activity ? detail.match[2].charAt(0).toUpperCase() + detail.match[2].slice(1) : ""
          textFormat: Text.PlainText
          color: root.foreground
          font.family: root.fontFamily
          font.pixelSize: root.captionSize
        }
        Text {
          id: activityDate
          objectName: "activityDate"
          property double hoverTime: Date.now()
          HoverHandler {
            id: dateHover
            onHoveredChanged: if (hovered) activityDate.hoverTime = Date.now()
          }
          Timer {
            interval: 1000
            repeat: true
            running: dateHover.hovered
            onTriggered: activityDate.hoverTime = Date.now()
          }
          ToolTip.visible: dateHover.hovered
          ToolTip.text: Presentation.age(detail.activity && root.status.timestamps ? root.status.timestamps[detail.match[2]] : null, hoverTime)
          Layout.fillWidth: true
          horizontalAlignment: Text.AlignRight
          text: detail.activity ? detail.match[3] : ""
          textFormat: Text.PlainText
          elide: Text.ElideRight
          color: root.foreground
          font.family: root.fontFamily
          font.pixelSize: root.captionSize
        }
      }
    }
  }
  Rectangle { objectName: "checksSeparator"; width: parent.width; height: 1; color: root.foreground; opacity: 0.15 }
  Item {
    id: footer
    objectName: "checksRow"
    width: parent.width
    implicitHeight: Math.max(checkControls.implicitHeight, watcherControls.implicitHeight)
    Row {
      id: checkControls
      HoverHandler { id: checkHover }
      anchors.verticalCenter: parent.verticalCenter
      spacing: 6 * root.unit
      Text {
        objectName: "countdown"
        anchors.verticalCenter: parent.verticalCenter
        text: root.refreshing ? "Checking…" : "Next check in " + Presentation.duration(root.remainingSeconds)
        textFormat: Text.PlainText
        color: root.foreground
        opacity: 0.55
        font.family: root.fontFamily
        font.pixelSize: root.captionSize
        MouseArea {
          anchors.fill: parent
          enabled: refreshButton.enabled
          cursorShape: Qt.PointingHandCursor
          onClicked: root.refreshRequested()
        }
      }
      ToolButton {
        id: refreshButton
        objectName: "refreshButton"
        width: 24 * root.unit
        height: 24 * root.unit
        enabled: !root.refreshing
        focusPolicy: Qt.NoFocus
        hoverEnabled: true
        Accessible.name: "Refresh status"
        ToolTip.visible: checkHover.hovered
        ToolTip.text: root.refreshing ? "Checking…" : "Refresh status"
        contentItem: Text {
          text: "\uf021"
          textFormat: Text.PlainText
          horizontalAlignment: Text.AlignHCenter
          verticalAlignment: Text.AlignVCenter
          color: root.foreground
          opacity: refreshButton.enabled ? 0.8 : 0.35
          font.family: root.fontFamily
          font.pixelSize: root.captionSize
        }
        onClicked: root.refreshRequested()
      }
    }
  }
}
