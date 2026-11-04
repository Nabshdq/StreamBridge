import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import ".."

// A text box with a label above it and an optional hint below it.
// ``committed`` fires when the user presses Enter or leaves the box.
ColumnLayout {
    id: root

    property string label: ""
    property string hint: ""
    property string text: ""
    property string placeholder: ""
    property bool secret: false
    property var validator: null
    signal committed(string value)
    signal edited(string value)   // fires on every keystroke

    Layout.fillWidth: true
    spacing: Theme.space1

    Text {
        text: root.label
        font.family: Theme.fontFamily
        font.pixelSize: Theme.bodySize
        color: Theme.text
    }

    TextField {
        id: field
        Layout.fillWidth: true
        Layout.preferredHeight: Theme.touchTarget
        text: root.text
        placeholderText: root.placeholder
        placeholderTextColor: Theme.textSecondary
        echoMode: root.secret ? TextInput.Password : TextInput.Normal
        validator: root.validator
        selectByMouse: true
        leftPadding: Theme.space2
        font.family: Theme.fontFamily
        font.pixelSize: Theme.bodySize
        color: Theme.text
        onTextEdited: root.edited(text)
        onEditingFinished: {
            root.committed(text)
            // Show the cleaned-up value (for example without a leading @).
            text = Qt.binding(() => root.text)
        }
        background: Rectangle {
            radius: Theme.radiusSmall
            color: Theme.raised
            border.width: field.activeFocus ? Theme.focusWidth : 1
            border.color: field.activeFocus ? Theme.text : Theme.borderStrong
        }
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
}
