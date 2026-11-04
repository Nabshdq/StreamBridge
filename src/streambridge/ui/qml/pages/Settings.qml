import QtQuick
import QtQuick.Layouts
import ".."
import "../components"

// Every setting in one scrolling page. Each change is saved immediately and is
// used the next time Start is pressed.
Item {
    id: root

    required property var settings
    required property var wizard

    // 1.5 -> "1.5" (English) or "1,5" (Indonesian): display only, typing either works.
    function decimalText(number) {
        return String(number).replace(".", i18n.strings["ui.number.decimal_separator"])
    }

    readonly property var eventKinds: ["chat", "gift", "follow", "like", "share", "repost"]
    readonly property var languageOptions: [
        { value: "auto", label: i18n.strings["ui.lang.auto"] },
        { value: "en", label: "English" },
        { value: "id", label: "Bahasa Indonesia" }
    ]

    Flickable {
        id: scroller
        anchors.fill: parent
        contentWidth: width
        contentHeight: page.implicitHeight + Theme.space4 * 2
        clip: true
        boundsBehavior: Flickable.StopAtBounds

        ColumnLayout {
            id: page
            x: Theme.space4
            y: Theme.space4
            width: Math.min(scroller.width - Theme.space4 * 2, Theme.contentWidth)
            spacing: Theme.space3

            Text {
                text: i18n.strings["ui.settings.title"]
                font.family: Theme.fontFamily
                font.pixelSize: Theme.titleSize
                font.weight: Theme.weightSemiBold
                color: Theme.text
            }

            Text {
                Layout.fillWidth: true
                text: i18n.strings["ui.settings.applies_next_start"]
                wrapMode: Text.Wrap
                font.family: Theme.fontFamily
                font.pixelSize: Theme.labelSize
                color: Theme.textSecondary
            }

            // Shown only when a change could not be written to disk.
            Rectangle {
                Layout.fillWidth: true
                visible: root.settings.saveError !== ""
                implicitHeight: saveErrorRow.implicitHeight + Theme.space2 * 2
                radius: Theme.radiusMedium
                color: Theme.surface
                border.width: 1
                border.color: Theme.attention

                Row {
                    id: saveErrorRow
                    x: Theme.space2
                    y: Theme.space2
                    width: parent.width - Theme.space2 * 2
                    spacing: Theme.space1
                    SvgIcon {
                        name: "triangle-alert"
                        color: Theme.attention
                    }
                    Text {
                        width: parent.width - Theme.iconSize - Theme.space1
                        text: i18n.strings["ui.settings.save_failed"].replace(
                                  "%1", () => root.settings.saveError)
                        wrapMode: Text.Wrap
                        font.family: Theme.fontFamily
                        font.pixelSize: Theme.bodySize
                        color: Theme.text
                    }
                }
            }

            SectionCard {
                title: i18n.strings["ui.settings.tiktok"]
                LabeledField {
                    label: i18n.strings["ui.settings.username"]
                    hint: i18n.strings["ui.settings.username_hint"]
                    placeholder: "username"
                    text: root.settings.tiktokUsername
                    onCommitted: (value) => root.settings.setTiktokUsername(value)
                }
            }

            SectionCard {
                title: i18n.strings["ui.settings.destinations"]
                SwitchRow {
                    label: "Twitch"
                    checked: root.settings.twitchEnabled
                    onToggled: (value) => root.settings.setTwitchEnabled(value)
                }
                SwitchRow {
                    label: "YouTube"
                    checked: root.settings.youtubeEnabled
                    onToggled: (value) => root.settings.setYoutubeEnabled(value)
                }
            }

            SectionCard {
                visible: root.settings.twitchEnabled
                title: i18n.strings["ui.settings.events_twitch"]
                Repeater {
                    model: root.eventKinds
                    delegate: SwitchRow {
                        required property string modelData
                        label: i18n.strings["ui.event." + modelData]
                        checked: root.settings.eventToggles["twitch"][modelData]
                        onToggled: (value) => root.settings.setEvent("twitch", modelData, value)
                    }
                }
            }

            SectionCard {
                visible: root.settings.youtubeEnabled
                title: i18n.strings["ui.settings.events_youtube"]
                Text {
                    Layout.fillWidth: true
                    text: i18n.strings["ui.settings.youtube_quota_hint"]
                    wrapMode: Text.Wrap
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.labelSize
                    color: Theme.textSecondary
                }
                Repeater {
                    model: root.eventKinds
                    delegate: SwitchRow {
                        required property string modelData
                        label: i18n.strings["ui.event." + modelData]
                        checked: root.settings.eventToggles["youtube"][modelData]
                        onToggled: (value) => root.settings.setEvent("youtube", modelData, value)
                    }
                }
                SwitchRow {
                    label: i18n.strings["ui.settings.compact"]
                    checked: root.settings.compactMode
                    onToggled: (value) => root.settings.setCompactMode(value)
                }
                LabeledField {
                    label: i18n.strings["ui.settings.live_hours"]
                    hint: i18n.strings["ui.settings.live_hours_hint"]
                    text: root.decimalText(root.settings.liveHours)
                    onCommitted: (value) => {
                        const hours = parseFloat(value.replace(",", "."))
                        if (!isNaN(hours)) root.settings.setLiveHours(hours)
                    }
                }
            }

            SectionCard {
                title: i18n.strings["ui.settings.messages"]
                LabeledField {
                    label: i18n.strings["ui.settings.gift_delay"]
                    hint: i18n.strings["ui.settings.gift_delay_hint"]
                    text: root.decimalText(root.settings.giftDelay)
                    onCommitted: (value) => {
                        const seconds = parseFloat(value.replace(",", "."))
                        if (!isNaN(seconds)) root.settings.setGiftDelay(seconds)
                    }
                }
            }

            SectionCard {
                title: i18n.strings["ui.settings.filters"]
                ListEditor {
                    label: i18n.strings["ui.settings.spam"]
                    hint: i18n.strings["ui.settings.spam_hint"]
                    items: root.settings.spamPhrases
                    onAdded: (word) => root.settings.addWord("spam", word)
                    onRemoved: (word) => root.settings.removeWord("spam", word)
                }
                ListEditor {
                    label: i18n.strings["ui.settings.rude"]
                    hint: i18n.strings["ui.settings.rude_hint"]
                    items: root.settings.rudeWords
                    onAdded: (word) => root.settings.addWord("rude", word)
                    onRemoved: (word) => root.settings.removeWord("rude", word)
                }
                ListEditor {
                    label: i18n.strings["ui.settings.allowed"]
                    hint: i18n.strings["ui.settings.allowed_hint"]
                    items: root.settings.allowedWords
                    onAdded: (word) => root.settings.addWord("allowed", word)
                    onRemoved: (word) => root.settings.removeWord("allowed", word)
                }
            }

            SectionCard {
                title: i18n.strings["ui.settings.language"]
                ChoiceRow {
                    label: i18n.strings["ui.settings.ui_language"]
                    options: root.languageOptions
                    current: root.settings.uiLanguage
                    onPicked: (value) => root.settings.setUiLanguage(value)
                }
                ChoiceRow {
                    label: i18n.strings["ui.settings.relay_language"]
                    options: root.languageOptions
                    current: root.settings.relayLanguage
                    onPicked: (value) => root.settings.setRelayLanguage(value)
                }
            }

            SectionCard {
                title: i18n.strings["ui.settings.advanced"]
                LabeledField {
                    label: i18n.strings["ui.settings.euler_key"]
                    hint: root.settings.hasEulerKey
                          ? i18n.strings["ui.settings.euler_saved"]
                          : i18n.strings["ui.settings.euler_hint"]
                    secret: true
                    text: ""
                    onCommitted: (value) => {
                        if (value !== "") root.settings.setEulerKey(value)
                    }
                }
                SecondaryButton {
                    visible: root.settings.hasEulerKey
                    text: i18n.strings["ui.settings.euler_remove"]
                    iconName: "x"
                    onClicked: root.settings.setEulerKey("")
                }
            }

            SectionCard {
                title: i18n.strings["ui.settings.setup"]
                Text {
                    Layout.fillWidth: true
                    text: i18n.strings["ui.settings.setup_hint"]
                    wrapMode: Text.Wrap
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.labelSize
                    color: Theme.textSecondary
                }
                SecondaryButton {
                    text: i18n.strings["ui.settings.setup_run"]
                    onClicked: root.wizard.restart()
                }
            }
        }
    }
}
