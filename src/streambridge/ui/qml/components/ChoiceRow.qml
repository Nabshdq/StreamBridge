import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import ".."

// Pick one of a few options (for example Auto / English / Indonesian).
// The chosen option has a check icon and bold text, not just a different colour.
ColumnLayout {
    id: root

    property string label: ""
    property var options: []      // [{ value: "auto", label: "Auto" }, ...]
    property string current: ""
    signal picked(string value)

    Layout.fillWidth: true
    spacing: Theme.space1

    Text {
        text: root.label
        font.family: Theme.fontFamily
        font.pixelSize: Theme.bodySize
        color: Theme.text
    }

    Flow {
        Layout.fillWidth: true
        spacing: Theme.space1

        Repeater {
            model: root.options
            delegate: Button {
                id: option
                required property var modelData
                readonly property bool selected: modelData.value === root.current
                focusPolicy: Qt.StrongFocus
                implicitHeight: Theme.touchTarget
                implicitWidth: optionRow.implicitWidth + Theme.space3
                onClicked: root.picked(modelData.value)

                contentItem: Row {
                    id: optionRow
                    spacing: Theme.space1
                    anchors.centerIn: parent
                    SvgIcon {
                        anchors.verticalCenter: parent.verticalCenter
                        name: "circle-check"
                        size: 20
                        visible: option.selected
                    }
                    Text {
                        anchors.verticalCenter: parent.verticalCenter
                        text: option.modelData.label
                        font.family: Theme.fontFamily
                        font.pixelSize: Theme.bodySize
                        font.weight: option.selected ? Theme.weightSemiBold : Theme.weightRegular
                        color: Theme.text
                    }
                }
                background: Rectangle {
                    radius: Theme.radiusSmall
                    color: option.selected ? Theme.raised : Theme.surface
                    border.width: option.activeFocus ? Theme.focusWidth : 1
                    border.color: option.activeFocus ? Theme.text
                                  : (option.selected ? Theme.text : Theme.borderStrong)
                }
            }
        }
    }
}
