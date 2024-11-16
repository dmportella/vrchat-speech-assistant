import re

from PySide6 import QtWidgets

from vrchat_speech_assistant import _config, providers, utils


class ConfigDialog(QtWidgets.QDialog):
    """A dialog that allows the user to configure the VRC Speech Assistant application.

    Parameters
    ----------
    parent : VRCSpeechAssistantWindow
        The main VRC Speech Assistant application.

    Attributes
    ----------
    DEFAULT_WIDTH: int
        The default window width.
    DEFAULT_HEIGHT: int
        The default window height.
    polly: providers.Polly
        The Amazon Polly provider object.
    """

    DEFAULT_WIDTH = 200
    DEFAULT_HEIGHT = 265

    def __init__(self, parent):
        super().__init__(parent=parent)
        self.parent = parent
        self._init_ui()

    def _init_ui(self):
        self.setWindowTitle("Edit configuration")
        self.setFixedSize(self.DEFAULT_WIDTH, self.DEFAULT_HEIGHT)
        ######### Main layout #########
        main_layout = QtWidgets.QVBoxLayout(self)
        main_layout.setSpacing(10)
        main_layout.setContentsMargins(30, 30, 30, 30)
        ######### Deepl widget #########
        deepl_api_key_label = QtWidgets.QLabel("DeepL API Key", self)
        self.deepl_api_key_line_edit = QtWidgets.QLineEdit(self)
        self.deepl_api_key_line_edit.setEchoMode(QtWidgets.QLineEdit.Password)
        self.deepl_api_key_line_edit.setText(self.parent.config["API"]["deepl_api_key"])
        ######### Amazon AWS widget #########
        aws_access_key_id_label = QtWidgets.QLabel("Amazon AWS access key ID", self)
        self.aws_access_key_line_edit = QtWidgets.QLineEdit(self)
        self.aws_access_key_line_edit.setEchoMode(QtWidgets.QLineEdit.Password)
        self.aws_access_key_line_edit.setText(self.parent.config["API"].get("aws_access_key"))
        aws_secret_access_key_label = QtWidgets.QLabel("Amazon AWS secret key", self)
        self.aws_secret_key_line_edit = QtWidgets.QLineEdit(self)
        self.aws_secret_key_line_edit.setEchoMode(QtWidgets.QLineEdit.Password)
        self.aws_secret_key_line_edit.setText(self.parent.config["API"].get("aws_secret_key"))
        ######### Button box #########
        ok_button = QtWidgets.QPushButton("Ok")
        ok_button.clicked.connect(self._accept)
        ######### Add widgets to main layout #########
        main_layout.addWidget(deepl_api_key_label)
        main_layout.addWidget(self.deepl_api_key_line_edit)
        main_layout.addWidget(aws_access_key_id_label)
        main_layout.addWidget(self.aws_access_key_line_edit)
        main_layout.addWidget(aws_secret_access_key_label)
        main_layout.addWidget(self.aws_secret_key_line_edit)
        main_layout.addWidget(ok_button)

    def _accept(self):
        if self._check_deepl_and_aws():
            # Close the dialog
            self.close()

    def _check_deepl_and_aws(self):
        deepl_key = re.sub(r"\s+", "", self.deepl_api_key_line_edit.text())
        aws_access_key = re.sub(r"\s+", "", self.aws_access_key_line_edit.text())
        aws_secret_key = re.sub(r"\s+", "", self.aws_secret_key_line_edit.text())
        self.parent.config["API"]["deepl_api_key"] = deepl_key
        self.parent.config["API"]["aws_access_key"] = aws_access_key
        self.parent.config["API"]["aws_secret_key"] = aws_secret_key
        self.parent.save_config()
        if deepl_key:
            translator = utils.test_deepl(deepl_key)
        else:
            translator = utils.test_deepl(_config.DEEPL_API_KEY)
        if translator:
            self._activate_translator(translator)
        else:
            self._disable_translator()
            return False
        if aws_access_key or aws_secret_key:
            polly = providers.Polly(aws_access_key, aws_secret_key, "us-west-2")
        else:
            polly = providers.Polly(_config.AWS_ACCESS_KEY, _config.AWS_SECRET_KEY, "us-west-2")
        if polly.test():
            self._activate_aws()
        else:
            self._disable_aws()
            return False
        return True

    def _activate_translator(self, translator):
        self.parent.clear_log()
        self.parent.translator = translator
        self.parent.target_language_combo.setEnabled(True)
        self.deepl_api_key_line_edit.setStyleSheet("")

    def _disable_translator(self):
        self.deepl_api_key_line_edit.setStyleSheet("background-color: #cd3131")
        self.parent.log_error("DeepL API key is invalid or account usage limit reached.")
        self.parent.translator = None
        self.parent.target_language_combo.setEnabled(False)
        self.parent.target_language_combo.setCurrentText(self.parent.source_language_combo.currentText())
        self.parent.config["SPEECH"]["target_language"] = self.parent.source_language_combo.currentText()
        self.parent.save_config()

    def _activate_aws(self):
        self.parent.clear_log()
        self.parent.toggle_activate_button.setEnabled(True)
        self.aws_access_key_line_edit.setStyleSheet("")
        self.aws_secret_key_line_edit.setStyleSheet("")

    def _disable_aws(self):
        self.aws_access_key_line_edit.setStyleSheet("background-color: red")
        self.aws_secret_key_line_edit.setStyleSheet("background-color: red")
        self.parent.log_line_edit.setText("Amazon AWS credentials are invalid.")
        self.parent.toggle_activate_button.setEnabled(False)
