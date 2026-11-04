import QtQuick
import QtQuick.Layouts
import ".."
import "../components"

// The first-run wizard. It covers the whole window; one question per step.
// Which steps exist (and whether Next works) is decided in ui/wizard.py.
Rectangle {
    id: root

    required property var controller
    required property var settings

    readonly property var languageOptions: [
        { value: "auto", label: i18n.strings["ui.lang.auto"] },
        { value: "en", label: "English" },
        { value: "id", label: "Bahasa Indonesia" }
    ]

    color: Theme.canvas

    // Place-holder step text for a destination whose login is not built yet.
    component LoginLater: Row {
        spacing: Theme.space1
        SvgIcon {
            name: "clock"
            color: Theme.attention
        }
        Text {
            width: parent.width - Theme.iconSize - Theme.space1
            text: i18n.strings["ui.wizard.login_later"]
            wrapMode: Text.Wrap
            font.family: Theme.fontFamily
            font.pixelSize: Theme.bodySize
            color: Theme.text
        }
    }

    component Body: Text {
        Layout.fillWidth: true
        wrapMode: Text.Wrap
        font.family: Theme.fontFamily
        font.pixelSize: Theme.bodySize
        color: Theme.textSecondary
    }

    component Title: Text {
        Layout.fillWidth: true
        wrapMode: Text.Wrap
        font.family: Theme.fontFamily
        font.pixelSize: Theme.titleSize
        font.weight: Theme.weightSemiBold
        color: Theme.text
    }

    ColumnLayout {
        x: (root.width - width) / 2
        y: Theme.space6
        width: Math.min(root.width - Theme.space4 * 2, Theme.contentWidth)
        spacing: Theme.space3

        Text {
            text: i18n.strings["ui.wizard.step"]
                      .replace("%1", () => root.controller.stepNumber)
                      .replace("%2", () => root.controller.stepCount)
            font.family: Theme.fontFamily
            font.pixelSize: Theme.labelSize
            color: Theme.textSecondary
        }

        // ---- 1. Welcome ----
        ColumnLayout {
            Layout.fillWidth: true
            visible: root.controller.step === "welcome"
            spacing: Theme.space3
            Title { text: i18n.strings["ui.wizard.welcome.title"] }
            Body { text: i18n.strings["ui.wizard.welcome.body"] }
            ChoiceRow {
                label: i18n.strings["ui.settings.ui_language"]
                options: root.languageOptions
                current: root.settings.uiLanguage
                onPicked: (value) => root.settings.setUiLanguage(value)
            }
        }

        // ---- 2. TikTok username ----
        ColumnLayout {
            Layout.fillWidth: true
            visible: root.controller.step === "tiktok"
            spacing: Theme.space3
            Title { text: i18n.strings["ui.wizard.tiktok.title"] }
            Body { text: i18n.strings["ui.wizard.tiktok.body"] }
            LabeledField {
                label: i18n.strings["ui.settings.username"]
                hint: i18n.strings["ui.settings.username_hint"]
                placeholder: "username"
                text: root.controller.usernameDraft
                onEdited: (value) => root.controller.setUsernameDraft(value)
                onCommitted: (value) => root.controller.setUsernameDraft(value)
            }
        }

        // ---- 3. Destinations ----
        ColumnLayout {
            Layout.fillWidth: true
            visible: root.controller.step === "destinations"
            spacing: Theme.space3
            Title { text: i18n.strings["ui.wizard.destinations.title"] }
            Body { text: i18n.strings["ui.wizard.destinations.body"] }
            CheckRow {
                id: twitchCheck
                text: "Twitch"
                checked: root.settings.twitchEnabled
                onToggled: {
                    root.settings.setTwitchEnabled(checked)
                    checked = Qt.binding(() => root.settings.twitchEnabled)
                }
            }
            CheckRow {
                id: youtubeCheck
                text: "YouTube"
                checked: root.settings.youtubeEnabled
                onToggled: {
                    root.settings.setYoutubeEnabled(checked)
                    checked = Qt.binding(() => root.settings.youtubeEnabled)
                }
            }
            Row {
                Layout.fillWidth: true
                visible: !root.controller.canGoNext
                spacing: Theme.space1
                SvgIcon {
                    name: "info"
                    color: Theme.textSecondary
                }
                Text {
                    text: i18n.strings["ui.wizard.destinations.need_one"]
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.labelSize
                    color: Theme.textSecondary
                }
            }
        }

        // ---- 4. Twitch (login arrives in a later update) ----
        ColumnLayout {
            Layout.fillWidth: true
            visible: root.controller.step === "twitch"
            spacing: Theme.space3
            Title { text: i18n.strings["ui.wizard.twitch.title"] }
            LoginLater { Layout.fillWidth: true }
        }

        // ---- 5. YouTube (login arrives in a later update) ----
        ColumnLayout {
            Layout.fillWidth: true
            visible: root.controller.step === "youtube"
            spacing: Theme.space3
            Title { text: i18n.strings["ui.wizard.youtube.title"] }
            LoginLater { Layout.fillWidth: true }
        }

        // ---- 6. Done ----
        ColumnLayout {
            Layout.fillWidth: true
            visible: root.controller.step === "done"
            spacing: Theme.space3
            Title { text: i18n.strings["ui.wizard.done.title"] }
            Body {
                color: Theme.text
                text: i18n.strings["ui.wizard.done.tiktok"]
                          .replace("%1", () => root.settings.tiktokUsername)
            }
            Body {
                color: Theme.text
                text: i18n.strings["ui.wizard.done.destinations"].replace("%1", () => {
                    const names = []
                    if (root.settings.twitchEnabled) names.push("Twitch")
                    if (root.settings.youtubeEnabled) names.push("YouTube")
                    return names.join(", ")
                })
            }
            Body { text: i18n.strings["ui.wizard.done.note"] }
        }

        // ---- Buttons ----
        RowLayout {
            Layout.fillWidth: true
            Layout.topMargin: Theme.space3
            spacing: Theme.space2

            SecondaryButton {
                visible: root.controller.canGoBack
                text: i18n.strings["ui.wizard.back"]
                onClicked: root.controller.back()
            }
            Item { Layout.fillWidth: true }
            SecondaryButton {
                visible: root.controller.canClose
                text: i18n.strings["ui.wizard.close"]
                iconName: "x"
                onClicked: root.controller.close()
            }
            PrimaryButton {
                accented: false
                enabled: root.controller.canGoNext
                text: root.controller.step === "done"
                      ? i18n.strings["ui.wizard.finish"] : i18n.strings["ui.wizard.next"]
                onClicked: root.controller.step === "done"
                           ? root.controller.finish() : root.controller.next()
            }
        }
    }
}
