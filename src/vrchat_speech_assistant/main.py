"""The VRChat Speech Assistant allows you to easily use a speech to speech, with automatic translation.

And / or speech to text with the VRChat chatbox using OSC protocol. """

import configparser
import contextlib
import sys
import webbrowser
import winsound
from os import getenv
from pathlib import Path
from threading import Thread

import speech_recognition
from chatbox_osc import FONTS, write_chatbox
from logger import Logger
from pyaudio_devices.devices import get_devices
from PySide6 import QtGui, QtWidgets
from PySide6.QtCore import Qt
from pythonosc.dispatcher import Dispatcher
from pythonosc.osc_server import BlockingOSCUDPServer
from pythonosc.udp_client import SimpleUDPClient

from vrchat_speech_assistant import _config, darkstyle, icons
from vrchat_speech_assistant.languages import DEEPL, GOOGLE, VOICES
from vrchat_speech_assistant.providers import Polly
from vrchat_speech_assistant.utils import test_deepl
from vrchat_speech_assistant.widgets import ConfigDialog

CONFIG_FILE = Path(getenv("APPDATA")) / "VRChat Speech Assistant" / "config.ini"
RESOURCES_PATH = Path(__file__).parent / "resources"

logger = Logger("VRChat Speech Assistant :: Main")
dispatcher = Dispatcher()


class VRCSpeechAssistantWindow(QtWidgets.QWidget):
    """The main window of the VRC Speech Assistant application.

    Using the parameters chosen by the user, this application allows you to use a
    speech to speech, or speech to text, or both, with your chosen provider.
    You can also use a translator to auto translate your sentence using DeepL.

    Note
    ----
        - The recognizer uses Google services, no configuration needed.
        - Amazon Polly need an API key, but a default one is provided.
        - DeepL translator need an API key, but a default one is provided.

    Attributes
    ----------
    DEFAULT_WIDTH: int
        The default window width.
    DEFAULT_HEIGHT: int
        The default window height.
    SPEECH_GROUPBOX_HEIGHT: int
        The speech groupbox widget height size.
    CHATBOX_GROUPBOX_HEIGHT: int
        The chatbox groupbox widget height size.
    CONFIG: dict
        The default configuration dictionary for the application.
    speech_provider: object
        The selected speech provider for the speech engine.
    extra_tags: dict
        Optional extra tags to be provided to the speech provider object.
    osc_client: SimpleUDPClient
        The OSC client for VRChat on port 9000.
    osc_server: BlockingOSCUDPServer
        The OSC server that allows the user to interact with the app trough OSC
        on port 7001.
    listener: speech_recognition.Recognizer.listen_in_background
        The listener object when the listener thread is running.
    is_listener_running: bool
        The state of the listener thread.
    input_devices: list
        A list of input sounddevice dict.
    output_devices: list
        A list of input sounddevice dict.
    config: configparser.ConfigParser
        The configuration file parser.
    """

    DEFAULT_WIDTH = 320
    DEFAULT_HEIGHT = 650
    SPEECH_GROUPBOX_HEIGHT = 271
    CHATBOX_GROUPBOX_HEIGHT = 100
    CONFIG = {
        "APP": {
            "beep": True,
            "input_device": None,
        },
        "API": {
            "deepl_api_key": "",
            "aws_access_key": "",
            "aws_secret_key": "",
            "aws_region": "us-west-2",
        },
        "TRANSLATOR": {
            "split_sentences": 1,
            "formality": "Default",
        },
        "SPEECH": {
            "enabled": True,
            "show more settings": False,
            "source_language": "English",
            "target_language": "English",
            "provider": "Amazon Polly",
            "voice": "Justin",
            "output_device": None,
        },
        "CHATBOX": {
            "enabled": True,
            "show more settings": False,
            "font": "Normal",
            "animation": True,
        },
    }

    def __init__(self):
        super().__init__()
        self.speech_provider = None
        self.extra_tags = {}
        self.osc_client = SimpleUDPClient("127.0.0.1", 9000)
        self.osc_server = BlockingOSCUDPServer(("127.0.0.1", 7001), dispatcher)
        self.listener = None
        self.is_listener_running = False
        self.input_devices = get_devices(device_type="input")
        self.output_devices = get_devices(device_type="output")
        self.config = configparser.ConfigParser(allow_no_value=True)
        self._init_config()
        self._init_ui()
        self._init_translator()
        self._init_server()

    def _init_config(self):
        self._load_base_config()
        if CONFIG_FILE.exists():
            self.config.read(CONFIG_FILE, encoding="utf8")
        self.save_config()

    def _load_base_config(self):
        for section, options in self.CONFIG.items():
            self.config[section] = options
        if self.input_devices:
            self.config["APP"]["input_device"] = self.input_devices[0]["name"]
        if self.output_devices:
            self.config["SPEECH"]["output_device"] = self.output_devices[0]["name"]

    def _init_ui(self):
        self.setWindowFlag(Qt.Window)
        self.setWindowTitle("VRChat Speech Assistant")
        self.setWindowIcon(QtGui.QIcon(str(RESOURCES_PATH / "logo.png")))
        self.setFixedSize(self.DEFAULT_WIDTH, self.DEFAULT_HEIGHT)
        ######### Menubar #########
        menu_bar = QtWidgets.QMenuBar(self)
        file_menu = menu_bar.addMenu("File")
        file_open_config_folder = file_menu.addAction("Open config folder", self.open_config_folder)
        file_open_config_folder.setIcon(QtGui.QIcon(str(RESOURCES_PATH / "folder.png")))
        edit_menu = menu_bar.addMenu("Edit")
        edit_configuration_action = edit_menu.addAction("Configuration", self.edit_config)
        edit_configuration_action.setIcon(QtGui.QIcon(str(RESOURCES_PATH / "edit.png")))
        more_menu = menu_bar.addMenu("More")
        open_web_action = more_menu.addAction("Open Gitlab Repository", self.open_repository)
        open_web_action.setIcon(QtGui.QIcon(str(RESOURCES_PATH / "web.png")))
        ######### Main layout #########
        main_layout = QtWidgets.QVBoxLayout(self)
        ######### Banner #########
        banner = QtWidgets.QLabel(self)
        banner.setPixmap(QtGui.QPixmap(str(RESOURCES_PATH / "banner.png")))
        banner.setAlignment(Qt.AlignCenter)
        tips_label = QtWidgets.QLabel("Speak clearly and avoid any source of background noise.")
        ######### Speech input widget #########
        input_device_label = QtWidgets.QLabel("Input device:")
        self.input_device_combo = QtWidgets.QComboBox()
        input_device_names = [item["name"] for item in self.input_devices]
        self.input_device_combo.addItems(input_device_names)
        saved_input_device = self.config["APP"].get("input_device")
        if saved_input_device and saved_input_device in input_device_names:
            self.input_device_combo.setCurrentText(saved_input_device)
        self.input_device_combo.currentTextChanged.connect(self._on_input_device_clicked)
        ############ Source language widget #########
        source_language_label = QtWidgets.QLabel("Source language:")
        self.source_language_combo = QtWidgets.QComboBox()
        self.source_language_combo.addItems(GOOGLE.keys())
        self.source_language_combo.setCurrentText(self.config["SPEECH"].get("source_language"))
        self.source_language_combo.currentTextChanged.connect(self._on_source_language_combo_clicked)
        ######### Target language widget #########
        target_language_label = QtWidgets.QLabel("Target language:")
        self.target_language_combo = QtWidgets.QComboBox()
        self.target_language_combo.addItems(DEEPL.keys())
        self.target_language_combo.setCurrentText(self.config["SPEECH"].get("target_language"))
        self.target_language_combo.currentTextChanged.connect(self._on_target_language_combo_clicked)
        ######### Formality widget #########
        formality_label = QtWidgets.QLabel("Formality (if available):")
        self.formality_combo = QtWidgets.QComboBox()
        self.formality_combo.addItems(["Default", "Formal", "Informal"])
        self.formality_combo.setCurrentText(self.config["TRANSLATOR"].get("formality"))
        self.formality_combo.currentTextChanged.connect(self._on_formality_combo_clicked)
        ######### Progressbar #########
        self.progressbar = QtWidgets.QProgressBar(self)
        self.progressbar.setStyleSheet("border-style: none")
        ######### Speech groupbox widget #########
        self.speech_status_checkbox = QtWidgets.QCheckBox("Speech")
        self.speech_status_checkbox.setChecked(self.config["SPEECH"].getboolean("enabled"))
        self.speech_status_checkbox.stateChanged.connect(self._on_speech_status_checkbox_clicked)
        self.speech_groupbox = QtWidgets.QGroupBox(self)
        self.speech_groupbox.setEnabled(self.config["SPEECH"].getboolean("enabled"))
        saved_speech_settings_shown = self.config["SPEECH"].getboolean("show more settings")
        self.speech_groupbox.setVisible(saved_speech_settings_shown)
        speech_groupbox_layout = QtWidgets.QVBoxLayout(self.speech_groupbox)
        ######### Speech groupbox more options #########
        speech_more_options_checkbox = QtWidgets.QCheckBox("Show Speech settings")
        speech_more_options_checkbox.setStyleSheet(
            "QCheckBox::indicator:unchecked {image:url(:/icons/right-arrow.png);}"
            "QCheckBox::indicator:checked {image:url(:/icons/down-arrow.png);}"
        )
        speech_more_options_checkbox.stateChanged.connect(self._on_speech_show_more_options_clicked)
        speech_more_options_checkbox.setChecked(saved_speech_settings_shown)
        ######### Speech provider widget #########
        speech_provider_label = QtWidgets.QLabel("Speech provider:")
        self.speech_provider_combo = QtWidgets.QComboBox()
        self.speech_provider_combo.addItems(["Amazon Polly"])
        self.speech_provider_combo.setCurrentText(self.config["SPEECH"].get("provider"))
        self.speech_provider_combo.currentTextChanged.connect(self._on_speech_provider_combo_clicked)
        ######### Extra tags widgets #########
        extra_tags_label = QtWidgets.QLabel("Extra tags:")
        self.extra_tags_combo = QtWidgets.QComboBox()
        self.extra_tags_combo.addItems(["None", "Whispered"])
        self.extra_tags_combo.currentTextChanged.connect(self._on_extra_tags_combo_clicked)
        ######### Speech voices widget #########
        speech_voice_label = QtWidgets.QLabel("Voice:")
        self.speech_voice_combo = QtWidgets.QComboBox()
        ######### Speech pitch widget #########
        speech_pitch_label = QtWidgets.QLabel("Voice pitch:")
        self.speech_pitch_slider = QtWidgets.QSlider(Qt.Horizontal)
        self.speech_pitch_slider.setRange(-50, 50)
        self.speech_pitch_slider.setValue(0)
        self.speech_pitch_slider.valueChanged.connect(self._on_speech_pitch_value_changed)
        ######### Speech output widget #########
        output_device_label = QtWidgets.QLabel("Output device:")
        self.output_device_combo = QtWidgets.QComboBox()
        output_device_names = [item["name"] for item in self.output_devices]
        self.output_device_combo.addItems(output_device_names)
        saved_output_device = self.config["SPEECH"].get("output_device")
        if saved_output_device and saved_output_device in output_device_names:
            self.output_device_combo.setCurrentText(saved_output_device)
        self.output_device_combo.currentTextChanged.connect(self._on_output_device_clicked)
        ######### Add widgets to speech groupbox widget #########
        speech_groupbox_layout.addWidget(speech_provider_label)
        speech_groupbox_layout.addWidget(self.speech_provider_combo)
        speech_groupbox_layout.addWidget(extra_tags_label)
        speech_groupbox_layout.addWidget(self.extra_tags_combo)
        speech_groupbox_layout.addWidget(speech_voice_label)
        speech_groupbox_layout.addWidget(self.speech_voice_combo)
        speech_groupbox_layout.addWidget(speech_pitch_label)
        speech_groupbox_layout.addWidget(self.speech_pitch_slider)
        speech_groupbox_layout.addWidget(output_device_label)
        speech_groupbox_layout.addWidget(self.output_device_combo)
        ######### Chatbox groupbox widget #########
        self.chatbox_status_checkbox = QtWidgets.QCheckBox("VRChat Chatbox")
        self.chatbox_status_checkbox.setChecked(self.config["CHATBOX"].getboolean("enabled"))
        self.chatbox_status_checkbox.stateChanged.connect(self._on_chatbox_status_clicked)
        self.chatbox_groupbox = QtWidgets.QGroupBox(self)
        self.chatbox_groupbox.setEnabled(self.config["CHATBOX"].getboolean("enabled"))
        saved_chatbox_settings_shown = self.config["CHATBOX"].getboolean("show more settings")
        self.chatbox_groupbox.setVisible(saved_chatbox_settings_shown)
        chatbox_groupbox_layout = QtWidgets.QVBoxLayout(self.chatbox_groupbox)
        ######### Chatbox groupbox more options #########
        chatbox_more_options_checkbox = QtWidgets.QCheckBox("Show Chatbox settings")
        chatbox_more_options_checkbox.setStyleSheet(
            "QCheckBox::indicator:unchecked {image:url(:/icons/right-arrow.png);}"
            "QCheckBox::indicator:checked {image:url(:/icons/down-arrow.png);}"
        )
        chatbox_more_options_checkbox.stateChanged.connect(self._on_chatbox_show_more_options_clicked)
        chatbox_more_options_checkbox.setChecked(saved_chatbox_settings_shown)
        ######### Font widget #########
        font_label = QtWidgets.QLabel("Font")
        self.font_combo = QtWidgets.QComboBox()
        self.font_combo.addItems(FONTS)
        self.font_combo.setCurrentText(self.config["CHATBOX"].get("font"))
        self.font_combo.currentTextChanged.connect(self._on_font_combo_clicked)
        ######### Chatbox animation widget #########
        self.chatbox_animation = QtWidgets.QCheckBox("Chatbox writing animation")
        self.chatbox_animation.setChecked(self.config["CHATBOX"].getboolean("animation"))
        self.chatbox_animation.stateChanged.connect(self._on_chatbox_animation_clicked)
        ######### Add widgets to chatbox groupbox widget #########
        chatbox_groupbox_layout.addWidget(font_label)
        chatbox_groupbox_layout.addWidget(self.font_combo)
        chatbox_groupbox_layout.addWidget(self.chatbox_animation)
        ######### Beep option widget #########
        self.beep_status_checkbox = QtWidgets.QCheckBox("Beep while recognizing")
        self.beep_status_checkbox.setChecked(self.config["APP"].getboolean("beep"))
        self.beep_status_checkbox.stateChanged.connect(self._on_beep_option_clicked)
        ######### Activate button #########
        self.toggle_activate_button = QtWidgets.QPushButton(self)
        self.toggle_activate_button.setFixedSize(self.DEFAULT_WIDTH - 22, 50)
        self._update_activate_button()
        self.toggle_activate_button.clicked.connect(self._update_activate_button)
        self.toggle_activate_button.clicked.connect(self.toggle_thread)
        ######### Delete Chatbox button #########
        chatbox_delete_button = QtWidgets.QPushButton(self, text="Clear Chatbox text")
        chatbox_delete_button.setStyleSheet("font-weight: bold")
        chatbox_delete_button.clicked.connect(self._on_chatbox_delete_button_clicked)
        ######### Log widget #########
        self.log_line_edit = QtWidgets.QLabel(self)
        ######### Progressbar geometry #########
        progressbar_height = self.DEFAULT_HEIGHT - 10
        if saved_speech_settings_shown:
            progressbar_height += self.SPEECH_GROUPBOX_HEIGHT
        if saved_chatbox_settings_shown:
            progressbar_height += self.CHATBOX_GROUPBOX_HEIGHT
        self.progressbar.setGeometry(0, progressbar_height, 320, 10)
        ######### Add widgets to main layout #########
        main_layout.setMenuBar(menu_bar)
        main_layout.addWidget(banner)
        main_layout.addWidget(tips_label)
        main_layout.addWidget(input_device_label)
        main_layout.addWidget(self.input_device_combo)
        main_layout.addWidget(source_language_label)
        main_layout.addWidget(self.source_language_combo)
        main_layout.addWidget(target_language_label)
        main_layout.addWidget(self.target_language_combo)
        main_layout.addWidget(formality_label)
        main_layout.addWidget(self.formality_combo)
        main_layout.addWidget(self.speech_status_checkbox)
        main_layout.addWidget(speech_more_options_checkbox)
        main_layout.addWidget(self.speech_groupbox)
        main_layout.addWidget(self.chatbox_status_checkbox)
        main_layout.addWidget(chatbox_more_options_checkbox)
        main_layout.addWidget(self.chatbox_groupbox)
        main_layout.addWidget(self.beep_status_checkbox)
        main_layout.addWidget(self.toggle_activate_button)
        main_layout.addWidget(chatbox_delete_button)
        main_layout.addWidget(self.log_line_edit)
        ######### Append voices for the current provider #########
        self._append_voices_for_selected_provider()
        self.speech_voice_combo.setCurrentText(self.config["SPEECH"].get("voice"))
        self.speech_voice_combo.currentTextChanged.connect(self._on_voice_combo_clicked)
        ######### Checking which speech provider to use #########
        if self.config["SPEECH"].getboolean("enabled"):
            self._check_selected_speech_provider()
        self.toggle_activate_button.setFocus()

    def _init_translator(self):
        api_key = self.config["API"].get("deepl_api_key") or _config.DEEPL_API_KEY
        self.translator = test_deepl(api_key)
        if not self.translator:
            self._disable_target_language_combo()

    def _init_server(self):
        def thread_server():
            with contextlib.suppress(OSError):
                self.osc_server.serve_forever()

        dispatcher.map("/port", self._server_update_client_port)
        dispatcher.map("/source_language", self._server_change_source_language)
        dispatcher.map("/target_language", self._server_change_target_language)
        dispatcher.map("/formality", self._server_change_formality)
        dispatcher.map("/speech", self._server_toggle_speech)
        dispatcher.map("/speech_provider", self._server_change_speech_provider)
        dispatcher.map("/tag", self._server_change_extra_tags)
        dispatcher.map("/voice", self._server_change_voice)
        dispatcher.map("/pitch", self._server_change_voice_pitch)
        dispatcher.map("/input", self._server_change_input_device)
        dispatcher.map("/output", self._server_change_output_device)
        dispatcher.map("/chatbox", self._server_toggle_chatbox)
        dispatcher.map("/animation", self._server_toggle_chatbox_animation)
        dispatcher.map("/font", self._server_change_font)
        dispatcher.map("/beep", self._server_toggle_recognizer_beep)
        dispatcher.map("/enabled", self._server_toggle_thread)
        thread = Thread(target=thread_server)
        thread.start()

    def _on_source_language_combo_clicked(self, current_text: str):
        self.config["SPEECH"]["source_language"] = current_text
        self.save_config()
        # Disable target language combo if translator attribute is None
        if not self.translator:
            self._disable_target_language_combo()

    def _on_target_language_combo_clicked(self, current_text: str):
        self.config["SPEECH"]["target_language"] = current_text
        self.save_config()
        # Append voices for the current provider
        self._append_voices_for_selected_provider()

    def _on_formality_combo_clicked(self, current_text: str):
        self.config["TRANSLATOR"]["formality"] = current_text
        self.save_config()

    def _on_speech_status_checkbox_clicked(self, checked: int):
        if checked == 2:
            self.speech_groupbox.setEnabled(True)
            self.config["SPEECH"]["enabled"] = "True"
            # Checking which speech provider to use
            self._check_selected_speech_provider()
        else:
            self.speech_groupbox.setEnabled(False)
            if self.chatbox_status_checkbox.checkState() == Qt.CheckState.Unchecked:
                self.toggle_activate_button.setEnabled(False)
            self.speech_provider = None
            self.config["SPEECH"]["enabled"] = "False"
        self.save_config()

    def _on_speech_show_more_options_clicked(self, checked: int):
        progressbar_height = self.height() - 10
        if checked == 2:
            self.speech_groupbox.setVisible(True)
            self.config["SPEECH"]["show more settings"] = "True"
            self.setFixedSize(self.DEFAULT_WIDTH, self.height() + self.SPEECH_GROUPBOX_HEIGHT)
            progressbar_height += self.SPEECH_GROUPBOX_HEIGHT
            self.progressbar.setGeometry(0, progressbar_height, 320, 10)
        else:
            self.speech_groupbox.setVisible(False)
            self.config["SPEECH"]["show more settings"] = "False"
            self.setFixedSize(self.DEFAULT_WIDTH, self.height() - self.SPEECH_GROUPBOX_HEIGHT)
            progressbar_height -= self.SPEECH_GROUPBOX_HEIGHT
            self.progressbar.setGeometry(0, progressbar_height, 320, 10)
        self.save_config()

    def _on_chatbox_show_more_options_clicked(self, checked: int):
        progressbar_height = self.height() - 10
        if checked == 2:
            self.chatbox_groupbox.setVisible(True)
            self.config["CHATBOX"]["show more settings"] = "True"
            self.setFixedSize(self.DEFAULT_WIDTH, self.height() + self.CHATBOX_GROUPBOX_HEIGHT)
            progressbar_height += self.CHATBOX_GROUPBOX_HEIGHT
            self.progressbar.setGeometry(0, progressbar_height, 320, 10)
        else:
            self.chatbox_groupbox.setVisible(False)
            self.config["CHATBOX"]["show more settings"] = "False"
            self.setFixedSize(self.DEFAULT_WIDTH, self.height() - self.CHATBOX_GROUPBOX_HEIGHT)
            progressbar_height -= self.CHATBOX_GROUPBOX_HEIGHT
            self.progressbar.setGeometry(0, progressbar_height, 320, 10)
        self.save_config()

    def _on_speech_provider_combo_clicked(self, current_text: str):
        self.config["SPEECH"]["provider"] = current_text
        self.save_config()
        # Checking which speech provider to use
        self._check_selected_speech_provider()

    def _on_extra_tags_combo_clicked(self, current_text: str):
        self.extra_tags["whispered"] = current_text == "Whispered"

    def _on_speech_pitch_value_changed(self, current_value: int):
        self.log_line_edit.setText(f"Voice pitch: {str(current_value)}%")
        # Config extra tags
        if current_value != 0:
            self.extra_tags["pitch"] = current_value
        elif current_value == 0 and self.extra_tags.get("pitch"):
            del self.extra_tags["pitch"]

    def _on_input_device_clicked(self, current_text: str):
        self.config["APP"]["input_device"] = current_text
        self.save_config()

    def _on_output_device_clicked(self, current_text: str):
        self.config["SPEECH"]["output_device"] = current_text
        self.save_config()

    def _on_chatbox_status_clicked(self, checked: int):
        if checked == 2:
            self.chatbox_groupbox.setEnabled(True)
            self.clear_log()
            self.config["CHATBOX"]["enabled"] = "True"
            self.toggle_activate_button.setEnabled(True)
            # Checking which speech provider to use
            if self.config["SPEECH"].getboolean("enabled"):
                self._check_selected_speech_provider()
        else:
            self.chatbox_groupbox.setEnabled(False)
            self.config["CHATBOX"]["enabled"] = "False"
            # Disable the toggle activate button if the speech status checkbox is unchecked
            if self.speech_status_checkbox.checkState() == Qt.CheckState.Unchecked:
                self.toggle_activate_button.setEnabled(False)
        self.save_config()

    def _on_font_combo_clicked(self, current_text: str):
        self.config["CHATBOX"]["font"] = current_text
        self.save_config()

    def _on_chatbox_animation_clicked(self, checked: int):
        self.config["CHATBOX"]["animation"] = "True" if checked == 2 else "False"
        self.save_config()

    def _on_beep_option_clicked(self, checked: int):
        self.config["APP"]["beep"] = "True" if checked == 2 else "False"
        self.save_config()

    def _on_voice_combo_clicked(self, current_text: str):
        self.config["SPEECH"]["voice"] = current_text
        self.save_config()

    def _on_chatbox_delete_button_clicked(self):
        write_chatbox(self.osc_client, None)

    def _server_update_client_port(self, _, port):
        self.osc_client._port = port

    def _server_change_source_language(self, _, language):
        self.source_language_combo.setCurrentText(language)

    def _server_change_target_language(self, _, language):
        self.target_language_combo.setCurrentText(language)

    def _server_change_formality(self, _, formality):
        self.formality_combo.setCurrentText(formality)

    def _server_toggle_speech(self, _, option):
        if option == 0:
            self.speech_status_checkbox.setChecked(False)
            return
        self.speech_status_checkbox.setChecked(True)

    def _server_change_speech_provider(self, _, provider):
        for item in range(self.speech_provider_combo.count()):
            item_text = self.speech_provider_combo.itemText(item)
            if item_text.startswith(provider):
                self.speech_provider_combo.setCurrentText(item_text)
                return

    def _server_change_extra_tags(self, _, tag):
        self.extra_tags_combo.setCurrentText(tag)

    def _server_change_voice(self, _, voice):
        for item in range(self.speech_voice_combo.count()):
            item_text = self.speech_voice_combo.itemText(item)
            if item_text.startswith(voice):
                self.speech_voice_combo.setCurrentText(item_text)
                return

    def _server_change_voice_pitch(self, _, pitch):
        self.speech_pitch_slider.setValue(pitch)

    def _server_change_input_device(self, _, input_device):
        for item in range(self.input_device_combo.count()):
            item_text = self.input_device_combo.itemText(item)
            if item_text.startswith(input_device):
                self.input_device_combo.setCurrentText(item_text)
                return

    def _server_change_output_device(self, _, output_device):
        for item in range(self.output_device_combo.count()):
            item_text = self.output_device_combo.itemText(item)
            if item_text.startswith(output_device):
                self.output_device_combo.setCurrentText(item_text)
                return

    def _server_toggle_chatbox(self, _, option):
        if option == 0:
            self.chatbox_status_checkbox.setChecked(False)
            return
        self.chatbox_status_checkbox.setChecked(True)

    def _server_toggle_chatbox_animation(self, _, option):
        if option == 0:
            self.chatbox_animation.setChecked(False)
            return
        self.chatbox_animation.setChecked(True)

    def _server_change_font(self, _, font):
        for item in range(self.font_combo.count()):
            item_text = self.font_combo.itemText(item)
            if item_text.startswith(font):
                self.font_combo.setCurrentText(item_text)
                return

    def _server_toggle_recognizer_beep(self, _, option):
        if option == 0:
            self.beep_status_checkbox.setChecked(False)
            return
        self.beep_status_checkbox.setChecked(True)

    def _server_toggle_thread(self, _, option):
        if option == 0 and self.is_listener_running:
            self.toggle_thread()
        elif option == 1 and not self.is_listener_running:
            self.toggle_thread()

    def _update_activate_button(self):
        if not self.is_listener_running:
            self.toggle_activate_button.setText("START LISTENING")
            self.toggle_activate_button.setStyleSheet("font-weight: bold")
        else:
            self.toggle_activate_button.setText("STOP LISTENING")
            self.toggle_activate_button.setStyleSheet(
                "background-color: red; color: black; font-weight: bold;"
            )

    def _disable_target_language_combo(self):
        self.log_error("DeepL API key is invalid or account usage limit reached.")
        self.target_language_combo.setEnabled(False)
        # Setting the target language to the same as the source language
        self.target_language_combo.setCurrentText(self.source_language_combo.currentText())
        self.config["SPEECH"]["target_language"] = self.source_language_combo.currentText()
        self.save_config()

    def _append_voices_for_selected_provider(self):
        self.speech_voice_combo.clear()
        # Amazon Polly
        if self.config["SPEECH"].get("provider") == "Amazon Polly":
            selected_voice = self.target_language_combo.currentText()
            if not (voices := VOICES["polly"].get(selected_voice)):
                self.speech_voice_combo.addItem("None")
            else:
                self.speech_voice_combo.addItems(voices)

    def _check_selected_speech_provider(self):
        # Amazon Polly
        if self.config["SPEECH"].get("provider") == "Amazon Polly":
            aws_access_key = self.config["API"].get("aws_access_key") or _config.AWS_ACCESS_KEY
            aws_secret_key = self.config["API"].get("aws_secret_key") or _config.AWS_SECRET_KEY
            region = self.config["API"].get("aws_region")
            self.speech_provider = Polly(aws_access_key, aws_secret_key, region)
            if not self.speech_provider.test():
                self.speech_provider = None
                self.toggle_activate_button.setEnabled(False)
                self.log_error("Amazon AWS credentials are invalid or missing.")
            else:
                self.toggle_activate_button.setEnabled(True)
                self.clear_log()

    def _get_input_device_index(self, input_device_name):
        input_devices = {item["name"]: item["index"] for item in self.input_devices}
        return input_devices.get(input_device_name)

    def _voice_activity(self, activity: bool):
        chatbox_enabled = self.config["CHATBOX"].getboolean("enabled")
        self.progressbar.setMaximum(0 if activity else 100)
        if chatbox_enabled:
            self.osc_client.send_message("/chatbox/typing", bool(activity))

    @staticmethod
    def open_config_folder():
        """Open the configuration folder."""
        config_folder = CONFIG_FILE.parent
        config_folder.mkdir(parents=True, exist_ok=True)
        webbrowser.open(str(config_folder))

    @staticmethod
    def open_repository():
        """Open the repository of the current script in your default web browser."""
        webbrowser.open("https://gitlab.com/ameliend/vrchat-speech-assistant")

    def edit_config(self):
        """Open the configuration dialog."""
        config_dialog = ConfigDialog(self)
        config_dialog.exec()

    def save_config(self):
        """Save configuration changes to the configuration file."""
        CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with CONFIG_FILE.open("w", encoding="utf-8") as config_file:
            self.config.write(config_file)

    def toggle_thread(self):
        """Start or stop the listener thread."""
        if not self.is_listener_running:
            self.start_listener()
        else:
            self.stop_listener()
        self._update_activate_button()

    def start_listener(self):
        """Start the listener thread."""
        input_device_name = self.config["APP"].get("input_device")
        if not (input_device_index := self._get_input_device_index(input_device_name)):
            return
        microphone = speech_recognition.Microphone(device_index=input_device_index)
        recognizer = speech_recognition.Recognizer()
        recognizer.pause_threshold = 0.5
        recognizer.non_speaking_duration = 0.5
        recognizer.dynamic_energy_threshold = False
        winsound.PlaySound("resources\\on.wav", winsound.SND_ASYNC)
        self.listener = recognizer.listen_in_background(microphone, self.recognize)
        self.is_listener_running = True
        self.log_info("Listening...")

    def stop_listener(self):
        """Stop the listener thread."""
        winsound.PlaySound("resources\\off.wav", winsound.SND_ASYNC)
        self.listener(wait_for_stop=False)  # Stop the listener
        self.is_listener_running = False
        self.log_info("Listener stopped.")

    def recognize(self, recognizer: speech_recognition.Recognizer, audio: speech_recognition.Microphone):
        """Use Google's Speech Recognition API to recognize an audio file into a text string.

        Translate and speech the text if the attributes translator and / or speech_provider
        are not None.

        Note
        ----
        This method is intended to be used as an argument for the
        speech_recognition.Recognizer().listen_in_background function.

        Parameters
        ----------
        recognizer : `speech_recognition.Recognizer`
            A `Recognizer` instance from `speech_recognition` module used to perform speech recognition.
        audio : `speech_recognition.Microphone`
            A `Microphone` instance from `speech_recognition` module as the source of audio input.
        """
        self._voice_activity(True)
        source_language = self.config["SPEECH"].get("source_language")
        target_language = self.config["SPEECH"].get("target_language")
        if beep := self.config["APP"].getboolean("beep"):
            winsound.PlaySound("resources\\recognizing.wav", winsound.SND_ASYNC)
        try:
            text = recognizer.recognize_google(audio, language=GOOGLE[source_language])
        except speech_recognition.UnknownValueError:
            self.log_warning("The voice recognition did not understand.")
            if beep:
                winsound.PlaySound("resources\\warn.wav", winsound.SND_ASYNC)
            self._voice_activity(False)
            return
        except speech_recognition.RequestError:
            self.log_error("Could not request results from Google Speech Recognition service.")
            if beep:
                winsound.PlaySound("resources\\warn.wav", winsound.SND_ASYNC)
            self._voice_activity(False)
            return
        if text.lower() in ("stop", "stoppe", "staff"):
            self.log_warning(f'Word "{text}" was ignored.')
            if beep:
                winsound.PlaySound("resources\\warn.wav", winsound.SND_ASYNC)
            self._voice_activity(False)
            return
        self.log_info(f"Recognized: {text}")
        if beep:
            winsound.PlaySound("resources\\recognized.wav", winsound.SND_ASYNC)
        # Translating the text if the attribute translator is not None,
        # and if the source language is different from the target language
        if self.translator and source_language != target_language:
            text = self.translate(text)
        # Speech the text with the attribute function speech_provider.speech,
        # if there is a provider, and if there is a voice available to speech
        voice = self.config["SPEECH"].get("voice")
        output_device_name = self.config["SPEECH"]["output_device"]
        if self.speech_provider and voice != "None":
            self.speech_provider.speech(text, voice, output_device_name, self.extra_tags)
        if self.config["CHATBOX"].getboolean("enabled"):
            font = self.config["CHATBOX"].get("font")
            chunk_length = 25 if self.config["CHATBOX"].getboolean("animation") is True else 0
            write_chatbox(self.osc_client, text.capitalize(), chunk_length=chunk_length, font=font)
        if beep and self.is_listener_running:
            winsound.PlaySound("resources\\on.wav", winsound.SND_ASYNC)
        self._voice_activity(False)

    def translate(self, text: str) -> str:
        """Use DeepL's API to translate a text.

        Parameters
        ----------
        text : str
            The text to be translated.

        Returns
        -------
        str
            The translated text.
        """
        source_language = DEEPL[self.config["SPEECH"].get("source_language")].split("-")[0]
        target_language = DEEPL[self.config["SPEECH"].get("target_language")]
        split_sentences = self.config["TRANSLATOR"].getint("split_sentences")
        formality = self.config["TRANSLATOR"].get("formality")
        formality_mapping = {"Default": "default", "Formal": "prefer_more", "Informal": "prefer_less"}
        translated_text = self.translator.translate_text(
            text,
            split_sentences=split_sentences,
            formality=formality_mapping[formality],
            source_lang=source_language,
            target_lang=target_language,
        ).text
        self.log_info(f"Translated: {translated_text}")
        return translated_text

    def log_info(self, text: str):
        """Logs informational messages.

        Clears the current log and resets the progress bar color.

        Parameters
        ----------
        text : str
            The message to be logged.
        """
        logger.info(text)
        self.clear_log()

    def log_warning(self, text: str):
        """Logs warning messages.

        Set the progress bar color to "orange".

        Parameters
        ----------
        text : str
            The message to be logged.
        """
        logger.warn(text)
        self.clear_log()
        self.log_line_edit.setStyleSheet("color: orange")
        self.log_line_edit.setText(text)
        self.progressbar.setStyleSheet("border-style: none; background-color: orange")

    def log_error(self, text: str):
        """Logs error messages.

        Set the progress bar color to "red".

        Parameters
        ----------
        text : str
            The message to be logged.
        """
        logger.error(text)
        self.clear_log()
        self.log_line_edit.setStyleSheet("color: #cd3131")
        self.log_line_edit.setText(text)
        self.progressbar.setStyleSheet("border-style: none; background-color: #cd3131")

    def clear_log(self):
        """Clears the current log and resets the progress bar color."""
        self.log_line_edit.clear()
        self.progressbar.setStyleSheet("border-style: none")

    # pylint: disable=invalid-name, missing-function-docstring
    def closeEvent(self, event):
        self.osc_server.server_close()
        event.accept()  # Let the window close


if __name__ == "__main__":
    app = QtWidgets.QApplication()
    darkstyle.apply(app)
    vrc_speech_assistant_window = VRCSpeechAssistantWindow()
    vrc_speech_assistant_window.show()
    sys.exit(app.exec())
