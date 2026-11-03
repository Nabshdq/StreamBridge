import QtQuick
import ".."

// A Lucide icon in any colour. Python's "icons" image provider draws it
// (see ui/icons.py), so no shader effects are needed.
Item {
    id: root

    property string name: ""
    property color color: Theme.text
    property int size: Theme.iconSize

    implicitWidth: size
    implicitHeight: size

    Image {
        anchors.fill: parent
        // String(color) is "#rrggbb"; the provider wants it without the "#".
        source: root.name === ""
                ? "" : "image://icons/" + root.name + "/" + String(root.color).substring(1)
        sourceSize: Qt.size(root.size * 2, root.size * 2)
        smooth: true
    }
}
