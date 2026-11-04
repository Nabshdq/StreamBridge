import QtQuick
import QtQuick.Controls
import ".."

// The one big Start / Stop button. It is the most dominant element on screen.
// Start uses the accent colour (the only place it appears); Stop is quiet.
Button {
    id: root

    property string iconName: ""
    property bool accented: true

    implicitHeight: Theme.touchTarget + Theme.space2
    implicitWidth: 192
    focusPolicy: Qt.StrongFocus

    contentItem: Item {
        Row {
            spacing: Theme.space1
            anchors.centerIn: parent

            SvgIcon {
                anchors.verticalCenter: parent.verticalCenter
                name: root.iconName
                color: root.accented ? Theme.textOnAccent : Theme.text
                visible: root.iconName !== ""
            }
            Text {
                anchors.verticalCenter: parent.verticalCenter
                text: root.text
                font.family: Theme.fontFamily
                font.pixelSize: Theme.headingSize
                font.weight: Theme.weightSemiBold
                // A button that cannot be pressed also looks dimmer (and the screen says why).
                color: !root.enabled ? Theme.textSecondary
                       : root.accented ? Theme.textOnAccent : Theme.text
            }
        }
    }

    background: Rectangle {
        radius: Theme.radiusMedium
        color: !root.enabled ? Theme.raised
             : root.accented ? (root.hovered ? Theme.accentHover : Theme.accent)
             : (root.hovered ? Theme.raised : Theme.surface)
        border.width: root.activeFocus ? Theme.focusWidth : (root.accented ? 0 : 1)
        border.color: root.activeFocus ? Theme.text : Theme.borderStrong
    }
}
