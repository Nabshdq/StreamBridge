import QtQuick
import QtQuick.Controls
import ".."

// A normal-sized, quiet button for everything except Start / Stop.
Button {
    id: root

    property string iconName: ""

    implicitHeight: Theme.touchTarget
    implicitWidth: row.implicitWidth + Theme.space3
    focusPolicy: Qt.StrongFocus

    contentItem: Item {
        Row {
            id: row
            spacing: Theme.space1
            anchors.centerIn: parent

            SvgIcon {
                anchors.verticalCenter: parent.verticalCenter
                name: root.iconName
                size: 20
                visible: root.iconName !== ""
            }
            Text {
                anchors.verticalCenter: parent.verticalCenter
                text: root.text
                font.family: Theme.fontFamily
                font.pixelSize: Theme.bodySize
                color: Theme.text
            }
        }
    }

    background: Rectangle {
        radius: Theme.radiusSmall
        color: root.hovered ? Theme.raised : Theme.surface
        border.width: root.activeFocus ? Theme.focusWidth : 1
        border.color: root.activeFocus ? Theme.text : Theme.borderStrong
    }
}
