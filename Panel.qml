import QtQuick
import QtQuick.Controls
import Quickshell
import qs.Commons
import qs.Ui
import "ui"
import "Presentation.js" as Presentation

Panel {
  id: root
  moduleName: "filipharald.oma-mise"
  ipcTarget: "filipharald.oma-mise"
  readonly property string fontFamily: bar ? bar.fontFamily : Style.font.family
  readonly property int barSlot: Style.bar.iconFont + Style.space(10)
  readonly property real openPanelIndicatorWidth: Style.bar.iconFont
  readonly property real openPanelIndicatorHeight: Style.bar.iconFont
  implicitWidth: bar && bar.vertical ? bar.barSize : barSlot
  implicitHeight: bar && bar.vertical ? barSlot : (bar ? bar.barSize : Style.bar.sizeHorizontal)
  onOpenedChanged: if (opened) StatusStore.refresh()

  ReviewClipboard { id: clipboard }

  BarIconButton {
    id: button
    anchors.fill: parent
    bar: root.bar
    slotSize: root.barSlot
    tooltipText: Presentation.hostTooltip(StatusStore.status.summary)
    iconComponent: Component {
      Item {
        StatusIcon {
          anchors.centerIn: parent
          width: Style.bar.iconFont
          height: width
          level: StatusStore.status.level
        }
      }
    }
    onPressed: function(buttonCode) {
      if (buttonCode === Qt.RightButton) StatusStore.refresh()
      else root.toggle()
    }
  }

  KeyboardPanel {
    id: popup
    anchorItem: button
    owner: root
    bar: root.bar
    open: root.opened
    focusTarget: keys
    contentWidth: Math.min(Style.space(360), availableCardWidth > 0 ? availableCardWidth : Style.space(420))
    contentHeight: fittedContentHeight(content.implicitHeight, Style.space(520))

    FocusScope {
      id: keys
      anchors.fill: parent
      Keys.onEscapePressed: function(event) { root.close(); event.accepted = true }
      Flickable {
        id: scroll
        anchors.fill: parent
        contentWidth: width
        contentHeight: content.implicitHeight
        clip: true
        boundsBehavior: Flickable.StopAtBounds
        ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }
        StatusContent {
          id: content
          width: scroll.width
          status: StatusStore.status
          refreshing: StatusStore.refreshing
          remainingSeconds: StatusStore.remainingSeconds
          watcherState: StatusStore.watcher.state
          watcherCanControl: StatusStore.watcher.can_control
          watcherBusy: StatusStore.watcherBusy
          watcherError: StatusStore.controlError || StatusStore.watcher.error
          foreground: Color.foreground
          fontFamily: root.fontFamily
          bodySize: Style.font.body
          captionSize: Style.font.caption
          unit: Style.space(1)
          onRefreshRequested: StatusStore.refresh()
          onWatcherToggleRequested: StatusStore.toggleWatcher()
          onCopyRequested: function(command) {
            clipboard.copy(command)
          }
        }
      }
    }
  }
}
