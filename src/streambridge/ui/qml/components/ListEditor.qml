import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import ".."

// An editable list of words or phrases: each one is a chip with a remove button,
// and a box below adds a new one.
ColumnLayout {
    id: root

    property string label: ""
    property string hint: ""
    property var items: []
    signal added(string word)
    signal removed(string word)

    Layout.fillWidth: true
    spacing: Theme.space1

    Text {
        text: root.label
        font.family: Theme.fontFamily
        font.pixelSize: Theme.bodySize
        color: Theme.text
    }

    Text {
        Layout.fillWidth: true
        visible: root.hint !== ""
        text: root.hint
        wrapMode: Text.Wrap
        font.family: Theme.fontFamily
        font.pixelSize: Theme.labelSize
        color: Theme.textSecondary
    }

    Flow {
        Layout.fillWidth: true
        spacing: Theme.space1

        Repeater {
            model: root.items
            delegate: Rectangle {
                id: chip
                required property string modelData
                height: Theme.touchTarget
                width: chipRow.implicitWidth + Theme.space1
                radius: Theme.radiusSmall
                color: Theme.raised

                Row {
                    id: chipRow
                    anchors.verticalCenter: parent.verticalCenter
                    leftPadding: Theme.space2
                    spacing: 0
                    Text {
                        anchors.verticalCenter: parent.verticalCenter
                        text: chip.modelData
                        font.family: Theme.fontFamily
                        font.pixelSize: Theme.bodySize
                        color: Theme.text
                    }
                    Button {
                        id: removeButton
                        width: Theme.touchTarget
                        height: Theme.touchTarget
                        focusPolicy: Qt.StrongFocus
                        onClicked: root.removed(chip.modelData)
                        Accessible.name: i18n.strings["ui.remove"] + " " + chip.modelData
                        contentItem: SvgIcon {
                            name: "x"
                            size: 20
                            color: Theme.textSecondary
                        }
                        background: Rectangle {
                            radius: Theme.radiusSmall
                            color: "transparent"
                            border.width: removeButton.activeFocus ? Theme.focusWidth : 0
                            border.color: Theme.text
                        }
                    }
                }
            }
        }
    }

    RowLayout {
        Layout.fillWidth: true
        spacing: Theme.space1

        TextField {
            id: input
            Layout.fillWidth: true
            Layout.preferredHeight: Theme.touchTarget
            placeholderText: i18n.strings["ui.add_placeholder"]
            placeholderTextColor: Theme.textSecondary
            selectByMouse: true
            leftPadding: Theme.space2
            font.family: Theme.fontFamily
            font.pixelSize: Theme.bodySize
            color: Theme.text
            onAccepted: addButton.clicked()
            background: Rectangle {
                radius: Theme.radiusSmall
                color: Theme.raised
                border.width: input.activeFocus ? Theme.focusWidth : 1
                border.color: input.activeFocus ? Theme.text : Theme.borderStrong
            }
        }

        SecondaryButton {
            id: addButton
            text: i18n.strings["ui.add"]
            iconName: "plus"
            onClicked: {
                if (input.text.trim() !== "") {
                    root.added(input.text)
                    input.text = ""
                }
            }
        }
    }
}
