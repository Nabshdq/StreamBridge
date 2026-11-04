import QtQuick
import QtQuick.Layouts
import ".."
import "../components"

// The dashboard: one big Start / Stop button, a status card per connection,
// the counters and the live feed of relayed messages.
Item {
    id: root

    required property var bridge

    function cardTitle(id) {
        if (id === "source") return "TikTok"
        if (id.indexOf("youtube") === 0) return "YouTube" + id.substring(7)
        return id.charAt(0).toUpperCase() + id.slice(1)
    }

    // 2340 -> "2,340" (English) or "2.340" (Indonesian): the separator is a
    // translated text, so it follows the app language, not the Windows locale.
    function groupDigits(number) {
        const separator = i18n.strings["ui.number.group_separator"]
        return String(number).replace(/\B(?=(\d{3})+(?!\d))/g, separator)
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: Theme.space4
        spacing: Theme.space3

        RowLayout {
            Layout.fillWidth: true
            spacing: Theme.space3

            Text {
                Layout.fillWidth: true
                text: i18n.strings["ui.dashboard.title"]
                font.family: Theme.fontFamily
                font.pixelSize: Theme.titleSize
                font.weight: Theme.weightSemiBold
                color: Theme.text
            }

            PrimaryButton {
                text: root.bridge.running ? i18n.strings["ui.stop"] : i18n.strings["ui.start"]
                iconName: root.bridge.running ? "square" : "play"
                accented: !root.bridge.running
                enabled: !root.bridge.stopping
                onClicked: root.bridge.running ? root.bridge.stop() : root.bridge.start()
            }
        }

        // Explains why Start did nothing (missing username, destination not set up...).
        Rectangle {
            Layout.fillWidth: true
            visible: root.bridge.lastError !== ""
            implicitHeight: errorRow.implicitHeight + Theme.space2 * 2
            radius: Theme.radiusMedium
            color: Theme.surface
            border.width: 1
            border.color: Theme.attention

            Row {
                id: errorRow
                anchors.fill: parent
                anchors.margins: Theme.space2
                spacing: Theme.space1
                SvgIcon {
                    name: "triangle-alert"
                    color: Theme.attention
                }
                Text {
                    width: parent.width - Theme.iconSize - Theme.space1
                    text: root.bridge.lastError
                    wrapMode: Text.Wrap
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.bodySize
                    color: Theme.text
                }
            }
        }

        Flow {
            Layout.fillWidth: true
            spacing: Theme.space2
            Repeater {
                model: root.bridge.connections
                StatusCard {
                    required property var modelData
                    title: root.cardTitle(modelData.id)
                    status: modelData.status
                    detail: modelData.detail
                }
            }
        }

        // A Flow, so the counters wrap onto a second line on a narrow window.
        Flow {
            Layout.fillWidth: true
            spacing: Theme.space2
            Counter { label: i18n.strings["ui.counter.sent"]; valueText: root.groupDigits(root.bridge.sentCount) }
            Counter { label: i18n.strings["ui.counter.waiting"]; valueText: root.groupDigits(root.bridge.waitingCount) }
            Counter { label: i18n.strings["ui.counter.filtered"]; valueText: root.groupDigits(root.bridge.filteredCount) }
            Counter { label: i18n.strings["ui.counter.dropped"]; valueText: root.groupDigits(root.bridge.droppedCount) }
            // Only while YouTube is in use and the engine has reported its quota.
            Counter {
                visible: root.bridge.quotaBudget > 0
                label: i18n.strings["ui.counter.youtube_quota"]
                valueText: root.groupDigits(root.bridge.quotaUsed)
                           + " / " + root.groupDigits(root.bridge.quotaBudget)
            }
        }

        Rectangle {
            Layout.fillWidth: true
            Layout.fillHeight: true
            radius: Theme.radiusMedium
            color: Theme.surface

            ListView {
                id: feed
                anchors.fill: parent
                anchors.margins: Theme.space2
                clip: true
                model: root.bridge.feed
                boundsBehavior: Flickable.StopAtBounds
                // The newest message sits at the bottom; follow it unless the user scrolled up.
                onCountChanged: if (atYEnd || count <= 1) Qt.callLater(positionViewAtEnd)

                delegate: FeedRow {
                    required property string time
                    required property string destination
                    required property string text
                    required property string status
                    required property string reason
                    timeText: time
                    destinationName: destination
                    message: text
                    rowStatus: status
                    reasonText: reason
                }

                Text {
                    anchors.centerIn: parent
                    visible: feed.count === 0
                    text: root.bridge.running
                          ? i18n.strings["ui.feed.empty_running"]
                          : i18n.strings["ui.feed.empty_idle"]
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.bodySize
                    color: Theme.textSecondary
                }
            }
        }
    }
}
