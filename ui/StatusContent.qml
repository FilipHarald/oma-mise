import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "../Presentation.js" as Presentation

Column {
  id: root
  property var status: ({summary: "Checking dotfiles…", level: "yellow", details: []})
  readonly property var safeStatus: Presentation.validStatus(status) ? status : Presentation.decode("")
  property bool refreshing: false
  property string watcherState: "unknown"
  property bool watcherCanControl: false
  property bool watcherBusy: false
  property string watcherError: ""
  property bool bootstrapBusy: false
  property string bootstrapError: ""
  property bool panelActive: false
  property int remainingSeconds: 30
  property color foreground: "#ffffff"
  property string fontFamily: "monospace"
  property int bodySize: 14
  property int captionSize: 12
  property real unit: 1
  readonly property string reviewKind: {
    var reasons = (root.safeStatus.details || []).join("\n")
    if (reasons.indexOf("Pending dotfiles changes need review") !== -1) return "changes"
    if (reasons.indexOf("Sync conflicts need review") !== -1) return "conflicts"
    return root.safeStatus.level === "yellow" || root.safeStatus.level === "red" ? "status" : ""
  }
  readonly property bool canBootstrap: (root.safeStatus.actions || []).indexOf("bootstrap") !== -1
  property bool bootstrapArmed: false
  property bool bootstrapConfirmationReady: false
  property bool filesExpanded: false
  property bool checkpointsExpanded: false
  property double clock: Date.now()
  readonly property var counts: {
    var lines = root.safeStatus.details || []
    for (var i = 0; i < lines.length; i++) {
      var match = /^Files: (\d+|unknown) \| Checkpoints: (\d+|unknown)$/.exec(lines[i])
      if (match) return match
    }
    return null
  }
  signal refreshRequested()
  signal watcherToggleRequested()
  signal bootstrapRequested()
  readonly property string reviewCommand: Presentation.reviewCommand(reviewKind)
  signal copyRequested(string command)
  onCanBootstrapChanged: if (!canBootstrap) {
    bootstrapArmed = false
    bootstrapConfirmationReady = false
  }
  onPanelActiveChanged: if (panelActive) clock = Date.now()
  spacing: 12 * unit
  Timer {
    interval: 1000
    repeat: true
    running: root.panelActive
    onTriggered: root.clock = Date.now()
  }

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
    Row {
      width: parent.width
      spacing: 6 * root.unit
      Text {
        objectName: "statusHeading"
        anchors.verticalCenter: parent.verticalCenter
        width: Math.min(implicitWidth, parent.width - (copyButton.visible ? copyButton.width + parent.spacing : 0))
        text: root.safeStatus.summary
        textFormat: Text.PlainText
        elide: Text.ElideRight
        color: Presentation.colorFor(root.safeStatus.level)
        font.family: root.fontFamily
        font.pixelSize: root.bodySize
        font.bold: true
      }
      ToolButton {
        id: copyButton
        objectName: "copyCommandButton"
        width: 24 * root.unit
        height: 24 * root.unit
        visible: root.reviewCommand !== ""
        focusPolicy: Qt.NoFocus
        hoverEnabled: true
        Accessible.name: "Copy review command"
        ToolTip.visible: hovered
        ToolTip.delay: 500
        ToolTip.text: "Copy review command"
        contentItem: Text {
          textFormat: Text.PlainText
          text: "\uf0c5"
          horizontalAlignment: Text.AlignHCenter
          verticalAlignment: Text.AlignVCenter
          color: root.foreground
          opacity: 0.55
          font.family: root.fontFamily
          font.pixelSize: root.captionSize
        }
        onClicked: root.copyRequested(root.reviewCommand)
      }
    }
    Text {
      objectName: "statusReason"

      width: parent.width
      text: (root.safeStatus.details || []).filter(function(line) {
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
    Column {
      width: parent.width
      visible: root.canBootstrap || root.bootstrapBusy
      spacing: 5 * root.unit
      Text {
        width: parent.width
        text: root.bootstrapArmed
          ? "This runs the complete configured mise bootstrap, including hooks and tasks."
          : "The changed declarations can be applied with a complete mise bootstrap."
        textFormat: Text.PlainText
        wrapMode: Text.Wrap
        color: root.foreground
        opacity: 0.7
        font.family: root.fontFamily
        font.pixelSize: root.captionSize
      }
      Button {
        id: bootstrapButton
        objectName: "bootstrapButton"
        enabled: !root.bootstrapBusy && !root.refreshing
          && (!root.bootstrapArmed || root.bootstrapConfirmationReady)
        focusPolicy: Qt.NoFocus
        hoverEnabled: true
        text: root.bootstrapBusy ? "Running bootstrap…"
          : root.bootstrapArmed ? "Confirm complete bootstrap" : "Apply declarations"
        Accessible.name: text
        ToolTip.visible: hovered
        ToolTip.delay: 500
        ToolTip.text: root.bootstrapArmed ? "Run mise bootstrap without --yes" : "Review and confirm"
        contentItem: Text {
          text: bootstrapButton.text
          textFormat: Text.PlainText
          horizontalAlignment: Text.AlignHCenter
          verticalAlignment: Text.AlignVCenter
          color: root.foreground
          opacity: bootstrapButton.enabled ? 0.9 : 0.4
          font.family: root.fontFamily
          font.pixelSize: root.captionSize
        }
        onClicked: {
          if (!root.bootstrapArmed) {
            root.bootstrapArmed = true
            root.bootstrapConfirmationReady = false
            confirmationDelay.restart()
            confirmTimeout.restart()
          } else {
            root.bootstrapArmed = false
            confirmTimeout.stop()
            root.bootstrapRequested()
          }
        }
      }
      Timer {
        id: confirmationDelay
        interval: 600
        onTriggered: root.bootstrapConfirmationReady = true
      }
      Timer {
        id: confirmTimeout
        interval: 8000
        onTriggered: {
          root.bootstrapArmed = false
          root.bootstrapConfirmationReady = false
        }
      }
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
    Text {
      visible: root.bootstrapError !== ""
      width: parent.width
      text: root.bootstrapError
      textFormat: Text.PlainText
      wrapMode: Text.Wrap
      color: Presentation.colorFor("red")
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
      textFormat: Text.PlainText
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
      enabled: root.watcherCanControl && !root.watcherBusy && (root.watcherState === "running" || root.watcherState === "stopped")
      focusPolicy: Qt.NoFocus
      hoverEnabled: true
      Accessible.name: root.watcherState === "running" ? "Pause watcher" : "Resume watcher"
      ToolTip.visible: watcherHover.hovered
      ToolTip.text: root.watcherState === "running" ? "Pause automatic saving and syncing" : "Resume automatic saving and syncing"
      contentItem: Text {
        textFormat: Text.PlainText
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
  RowLayout {
    width: parent.width
    spacing: 40 * root.unit
    Repeater {
      model: (root.safeStatus.details || []).filter(function(line) { return /^Last (publish|fetch|apply): /.test(line) })
      delegate: RowLayout {
        id: detail
        required property string modelData
        readonly property var match: /^(Last (publish|fetch|apply)): (.*)$/.exec(modelData)

        objectName: "activity-" + match[2]
        Layout.fillWidth: true
        Layout.preferredWidth: 1
        spacing: 4 * root.unit
        Text {
          objectName: "activityIcon"
          text: detail.match[2] === "publish" ? "\uf093" : detail.match[2] === "fetch" ? "\uf019" : "\uf00c"
          textFormat: Text.PlainText
          color: root.foreground
          font.family: root.fontFamily
          font.pixelSize: root.captionSize
        }
        Text {
          objectName: "activityLabel"
          text: detail.match[2].charAt(0).toUpperCase() + detail.match[2].slice(1)
          textFormat: Text.PlainText
          color: root.foreground
          font.family: root.fontFamily
          font.pixelSize: root.captionSize
        }
        Text {
          id: activityDate
          objectName: "activityDate"
          HoverHandler { id: dateHover }
          ToolTip.visible: dateHover.hovered
          ToolTip.text: Presentation.fullDate(root.safeStatus.timestamps ? root.safeStatus.timestamps[detail.match[2]] : null)
          Layout.fillWidth: true
          horizontalAlignment: Text.AlignRight
          text: Presentation.age(root.safeStatus.timestamps ? root.safeStatus.timestamps[detail.match[2]] : null, root.clock).replace(/ ago$/, "")
          textFormat: Text.PlainText
          elide: Text.ElideRight
          color: root.foreground
          opacity: 0.55
          font.family: root.fontFamily
          font.pixelSize: root.captionSize
        }
      }
    }
  }
  Column {
    id: filesSection
    objectName: "filesSection"
    width: parent.width
    spacing: 5 * root.unit
    Item {
      id: filesHeader
      objectName: "filesHeader"
      width: parent.width
      implicitHeight: filesHeaderRow.implicitHeight
      activeFocusOnTab: true
      Accessible.role: Accessible.Button
      Accessible.name: (root.filesExpanded ? "Collapse" : "Expand") + " recent files"
      Accessible.onPressAction: root.filesExpanded = !root.filesExpanded
      Keys.onReturnPressed: root.filesExpanded = !root.filesExpanded
      Keys.onEnterPressed: root.filesExpanded = !root.filesExpanded
      Keys.onSpacePressed: root.filesExpanded = !root.filesExpanded
      Rectangle {
        anchors.fill: parent
        color: root.foreground
        opacity: parent.activeFocus ? 0.08 : 0
        radius: 3 * root.unit
      }
      RowLayout {
        id: filesHeaderRow
        width: parent.width
        spacing: 8 * root.unit
        Text {
          objectName: "filesIcon"
          text: "\uf0c5"
          textFormat: Text.PlainText
          color: root.foreground
          font.family: root.fontFamily
          font.pixelSize: root.captionSize
          Layout.preferredWidth: 16 * root.unit
          horizontalAlignment: Text.AlignHCenter
        }
        Text {
          text: "Files"
          textFormat: Text.PlainText
          color: root.foreground
          font.family: root.fontFamily
          font.pixelSize: root.captionSize
          Layout.fillWidth: true
        }
        Text {
          text: root.counts ? root.counts[1] : "unknown"
          textFormat: Text.PlainText
          color: root.foreground
          opacity: 0.55
          font.family: root.fontFamily
          font.pixelSize: root.captionSize
        }
        Text {
          objectName: "filesChevron"
          text: root.filesExpanded ? "\uf078" : "\uf054"
          textFormat: Text.PlainText
          color: root.foreground
          opacity: 0.55
          font.family: root.fontFamily
          font.pixelSize: root.captionSize
          Layout.preferredWidth: 16 * root.unit
          horizontalAlignment: Text.AlignHCenter
        }
      }
      HoverHandler { cursorShape: Qt.PointingHandCursor }
      TapHandler {
        onTapped: {
          filesHeader.forceActiveFocus()
          root.filesExpanded = !root.filesExpanded
        }
      }
    }
    Repeater {
      model: root.filesExpanded ? (root.safeStatus.recent_files || []) : []
      delegate: RowLayout {
        required property var modelData
        width: filesSection.width
        spacing: 8 * root.unit
        Text {
          objectName: "filePath"
          text: modelData.path
          textFormat: Text.PlainText
          elide: Text.ElideMiddle
          color: root.foreground
          opacity: 0.8
          font.family: root.fontFamily
          font.pixelSize: root.captionSize
          Layout.fillWidth: true
        }
        Text {
          id: fileAge
          objectName: "fileAge"
          text: Presentation.age(modelData.at, root.clock)
          textFormat: Text.PlainText
          color: root.foreground
          opacity: 0.55
          font.family: root.fontFamily
          font.pixelSize: root.captionSize
          HoverHandler { id: fileAgeHover }
          ToolTip.visible: fileAgeHover.hovered
          ToolTip.text: Presentation.fullDate(modelData.at)
        }
      }
    }
    Text {
      visible: root.filesExpanded && !(root.safeStatus.recent_files || []).length
      width: parent.width
      text: root.safeStatus.history_available ? "No recent file changes" : "Recent history unavailable"
      textFormat: Text.PlainText
      color: root.foreground
      opacity: 0.55
      font.family: root.fontFamily
      font.pixelSize: root.captionSize
    }
  }
  Column {
    id: checkpointsSection
    objectName: "checkpointsSection"
    width: parent.width
    spacing: 5 * root.unit
    Item {
      id: checkpointsHeader
      objectName: "checkpointsHeader"
      width: parent.width
      implicitHeight: checkpointsHeaderRow.implicitHeight
      activeFocusOnTab: true
      Accessible.role: Accessible.Button
      Accessible.name: (root.checkpointsExpanded ? "Collapse" : "Expand") + " recent checkpoints"
      Accessible.onPressAction: root.checkpointsExpanded = !root.checkpointsExpanded
      Keys.onReturnPressed: root.checkpointsExpanded = !root.checkpointsExpanded
      Keys.onEnterPressed: root.checkpointsExpanded = !root.checkpointsExpanded
      Keys.onSpacePressed: root.checkpointsExpanded = !root.checkpointsExpanded
      Rectangle {
        anchors.fill: parent
        color: root.foreground
        opacity: parent.activeFocus ? 0.08 : 0
        radius: 3 * root.unit
      }
      RowLayout {
        id: checkpointsHeaderRow
        width: parent.width
        spacing: 8 * root.unit
        Text {
          objectName: "checkpointsIcon"
          text: "\uf1da"
          textFormat: Text.PlainText
          color: root.foreground
          font.family: root.fontFamily
          font.pixelSize: root.captionSize
          Layout.preferredWidth: 16 * root.unit
          horizontalAlignment: Text.AlignHCenter
        }
        Text {
          text: "Checkpoints"
          textFormat: Text.PlainText
          color: root.foreground
          font.family: root.fontFamily
          font.pixelSize: root.captionSize
          Layout.fillWidth: true
        }
        Text {
          text: root.counts ? root.counts[2] : "unknown"
          textFormat: Text.PlainText
          color: root.foreground
          opacity: 0.55
          font.family: root.fontFamily
          font.pixelSize: root.captionSize
        }
        Text {
          objectName: "checkpointsChevron"
          text: root.checkpointsExpanded ? "\uf078" : "\uf054"
          textFormat: Text.PlainText
          color: root.foreground
          opacity: 0.55
          font.family: root.fontFamily
          font.pixelSize: root.captionSize
          Layout.preferredWidth: 16 * root.unit
          horizontalAlignment: Text.AlignHCenter
        }
      }
      HoverHandler { cursorShape: Qt.PointingHandCursor }
      TapHandler {
        onTapped: {
          checkpointsHeader.forceActiveFocus()
          root.checkpointsExpanded = !root.checkpointsExpanded
        }
      }
    }
    Repeater {
      model: root.checkpointsExpanded ? (root.safeStatus.checkpoints || []) : []
      delegate: RowLayout {
        required property var modelData
        width: checkpointsSection.width
        spacing: 8 * root.unit
        Text {
          objectName: "checkpointMessage"
          text: modelData.message
          textFormat: Text.PlainText
          elide: Text.ElideRight
          color: root.foreground
          opacity: 0.8
          font.family: root.fontFamily
          font.pixelSize: root.captionSize
          Layout.fillWidth: true
        }
        Text {
          id: checkpointAge
          objectName: "checkpointAge"
          text: Presentation.age(modelData.at, root.clock)
          textFormat: Text.PlainText
          color: root.foreground
          opacity: 0.55
          font.family: root.fontFamily
          font.pixelSize: root.captionSize
          HoverHandler { id: checkpointAgeHover }
          ToolTip.visible: checkpointAgeHover.hovered
          ToolTip.text: Presentation.fullDate(modelData.at)
        }
      }
    }
    Text {
      visible: root.checkpointsExpanded && !(root.safeStatus.checkpoints || []).length
      width: parent.width
      text: root.safeStatus.history_available ? "No checkpoints yet" : "Recent history unavailable"
      textFormat: Text.PlainText
      color: root.foreground
      opacity: 0.55
      font.family: root.fontFamily
      font.pixelSize: root.captionSize
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
        text: root.bootstrapBusy ? "Running bootstrap…" : root.refreshing ? "Checking…" : "Next check in " + Presentation.duration(root.remainingSeconds)
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
        enabled: !root.refreshing && !root.bootstrapBusy
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
