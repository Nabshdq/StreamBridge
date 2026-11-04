import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import ".."

// A real checkbox: a labelled box that shows a check mark when it is chosen.
// The mark is a shape, so the state never depends on colour alone.
CheckBox {
    id: root

    property string description: ""

    Layout.fillWidth: true
    implicitHeight: Math.max(Theme.touchTarget + Theme.space2, column.implicitHeight + Theme.space3)
    focusPolicy: Qt.StrongFocus
    // Qt breaks the checked binding when the user clicks; the owner of the
    // value restores it by re-binding after reacting to ``toggled``.

    indicator: Rectangle {
        x: Theme.space2
        y: (root.height - height) / 2
        implicitWidth: 24
        implicitHeight: 24
        radius: 4
        color: root.checked ? Theme.text : Theme.raised
        border.width: 1
        border.color: root.checked ? Theme.text : Theme.borderStrong

        SvgIcon {
            anchors.centerIn: parent
            visible: root.checked
            name: "check"
            size: 16
            color: Theme.canvas
        }
    }

    contentItem: Item {
        Column {
            id: column
            x: root.indicator.width + Theme.space2 * 2
            width: root.width - x - Theme.space2
            anchors.verticalCenter: parent.verticalCenter
            spacing: 0

            Text {
                width: parent.width
                text: root.text
                wrapMode: Text.Wrap
                font.family: Theme.fontFamily
                font.pixelSize: Theme.bodySize
                font.weight: root.checked ? Theme.weightSemiBold : Theme.weightRegular
                color: Theme.text
            }
            Text {
                width: parent.width
                visible: root.description !== ""
                text: root.description
                wrapMode: Text.Wrap
                font.family: Theme.fontFamily
                font.pixelSize: Theme.labelSize
                color: Theme.textSecondary
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
