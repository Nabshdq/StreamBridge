import QtQuick
import ".."

// A number with a label under it, for the counters row.
// ``valueText`` replaces the number when the value is not a plain integer
// (for example "2,340 / 10,000").
Column {
    id: root

    property string label: ""
    property int value: 0
    property string valueText: ""

    spacing: 0

    Text {
        text: root.valueText !== "" ? root.valueText : root.value
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
