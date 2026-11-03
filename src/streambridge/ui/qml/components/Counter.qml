import QtQuick
import ".."

// A number with a label under it, for the counters row.
Column {
    id: root

    property string label: ""
    property int value: 0

    spacing: 0

    Text {
        text: root.value
        font.family: Theme.fontFamily
        font.pixelSize: Theme.titleSize
        font.weight: Theme.weightSemiBold
        color: Theme.text
    }
    Text {
        text: root.label
        font.family: Theme.fontFamily
        font.pixelSize: Theme.labelSize
        color: Theme.textSecondary
    }
}
