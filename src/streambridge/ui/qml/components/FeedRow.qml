import QtQuick
import ".."

// One line of the live feed. A refused message shows an icon plus its reason.
Item {
    id: root

    property string timeText: ""
    property string destinationName: ""
    property string message: ""
    property string rowStatus: "sent"
    property string reasonText: ""

    readonly property bool refused: rowStatus === "rejected"

    width: ListView.view ? ListView.view.width : 400
    implicitHeight: Math.max(Theme.touchTarget, content.implicitHeight + Theme.space1 * 2)
    height: implicitHeight

    Row {
        id: content
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.verticalCenter: parent.verticalCenter
        spacing: Theme.space2

        Text {
            id: timeLabel
            width: 72
            text: root.timeText
            font.family: Theme.fontFamily
            font.pixelSize: Theme.captionSize
            color: Theme.textSecondary
        }
        Text {
            id: destinationLabel
            width: 96
            text: root.destinationName
            elide: Text.ElideRight
            font.family: Theme.fontFamily
            font.pixelSize: Theme.labelSize
            font.weight: Theme.weightMedium
            color: Theme.textSecondary
        }
        Column {
            width: parent.width - timeLabel.width - destinationLabel.width - Theme.space2 * 2
            Text {
                width: parent.width
                text: root.message
                wrapMode: Text.Wrap
                font.family: Theme.fontFamily
                font.pixelSize: Theme.bodySize
                color: Theme.text
            }
            Row {
                visible: root.refused
                spacing: Theme.space1
                SvgIcon {
                    size: 16
                    name: "triangle-alert"
                    color: Theme.attention
                }
                Text {
                    text: qsTr("Not sent: %1").arg(root.reasonText)
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.labelSize
                    color: Theme.attention
                }
            }
        }
    }
}
