import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import ".."

// A label with an on/off switch. The state is also written as text ("On" / "Off"),
// so it never depends on colour alone.
RowLayout {
    id: root

    property string label: ""
    property bool checked: false
    signal toggled(bool value)

    Layout.fillWidth: true
    spacing: Theme.space2

    Text {
        Layout.fillWidth: true
        text: root.label
        wrapMode: Text.Wrap
        font.family: Theme.fontFamily
        font.pixelSize: Theme.bodySize
        color: Theme.text
    }

    Text {
        text: root.checked ? i18n.strings["ui.on"] : i18n.strings["ui.off"]
        font.family: Theme.fontFamily
        font.pixelSize: Theme.labelSize
        color: Theme.textSecondary
    }

    Switch {
        id: control
        checked: root.checked
        focusPolicy: Qt.StrongFocus
        implicitHeight: Theme.touchTarget
        implicitWidth: 56
        // Qt breaks the binding when the user toggles; restore it so the value follows the settings.
        onToggled: {
            root.toggled(checked)
            checked = Qt.binding(() => root.checked)
        }

        indicator: Rectangle {
            x: control.leftPadding
            y: (control.height - height) / 2
            implicitWidth: 48
            implicitHeight: 28
            radius: 14
            color: control.checked ? Theme.text : Theme.raised
            border.width: control.activeFocus ? Theme.focusWidth : 1
            border.color: control.activeFocus ? Theme.text : Theme.borderStrong

            Rectangle {
                x: control.checked ? parent.width - width - 4 : 4
                y: 4
                width: 20
                height: 20
                radius: 10
                color: control.checked ? Theme.canvas : Theme.textSecondary
            }
        }
        contentItem: Item {}
    }
}
