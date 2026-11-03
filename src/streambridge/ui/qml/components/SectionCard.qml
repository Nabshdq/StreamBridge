import QtQuick
import QtQuick.Layouts
import ".."

// A titled group of settings. Grouping is done with space and a card, not divider lines.
Rectangle {
    id: root

    property string title: ""
    default property alias content: body.data

    Layout.fillWidth: true
    implicitHeight: column.implicitHeight + Theme.space3 * 2
    radius: Theme.radiusMedium
    color: Theme.surface

    ColumnLayout {
        id: column
        x: Theme.space3
        y: Theme.space3
        width: parent.width - Theme.space3 * 2
        spacing: Theme.space2

        Text {
            Layout.fillWidth: true
            text: root.title
            font.family: Theme.fontFamily
            font.pixelSize: Theme.headingSize
            font.weight: Theme.weightSemiBold
            color: Theme.text
        }

        ColumnLayout {
            id: body
            Layout.fillWidth: true
            spacing: Theme.space2
        }
    }
}
