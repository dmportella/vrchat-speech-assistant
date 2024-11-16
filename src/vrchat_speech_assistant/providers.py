"""Providers classes that can be used as speech_provider attribute for the VRCSpeechAssistant class."""

import contextlib
import re
import threading
from os import getenv
from pathlib import Path

import boto3
import botocore
import botocore.exceptions
import pygame
import pygame.mixer
from botocore.config import Config
from logger import Logger

VOICES_PATH = Path(getenv("APPDATA")) / "VRChat Speech Assistant" / "voices"

logger = Logger("VRChat Speech Assistant :: Providers")


class Polly:
    """Use Amazon Polly API to synthesize a speech.

    This class can be used as speech_provider attribute for the VRCSpeechAssistant class.

    Parameters
    ----------
    aws_access_key_id : str
        The AWS access key ID used to authenticate with the Amazon Polly API.
    aws_secret_access_key : str
        The AWS secret access key used to authenticate with the Amazon Polly API.
    region_name : str
        The region name where the Amazon Polly service is located.
    """

    def __init__(self, aws_access_key_id: str, aws_secret_access_key: str, region_name: str):
        my_config = Config(region_name=region_name)
        self.client = boto3.client(
            "polly",
            aws_access_key_id=aws_access_key_id,
            aws_secret_access_key=aws_secret_access_key,
            config=my_config,
        )

    def speech(self, text: str, voice_id: str, output_device_name: str, extra_tags: dict = None):
        """Convert a text into a speech and then play it to the given output_device.

        Parameters
        ----------
        text : str
            The text to be converted to speech.
        voice_id : str
            The voice id of the voice you want to use.
        output_device_name : str
            The output device name.
        extra_tags : dict
            A dict of extra tags.
        """

        def convert_to_ssml(input_text):
            # https://docs.aws.amazon.com/polly/latest/dg/supportedtags.html
            ssml_tags = (
                '<amazon:auto-breaths frequency="low" volume="soft" duration="x-short">'
                + input_text
                + "</amazon:auto-breaths>"
            )
            if extra_tags:
                if extra_tags.get("whispered", False) is True:
                    ssml_tags = f'<amazon:effect name="whispered">{ssml_tags}</amazon:effect>'
                if extra_tags.get("pitch"):
                    ssml_tags = f'<prosody pitch="{extra_tags["pitch"]}%">{ssml_tags}</prosody>'
            return f"<speak>{ssml_tags}</speak>"

        # Remove special characters from the text for the file destination
        filename = re.sub("[#<$+%>!`&*'|{?\"=/}:@]", "", text)
        if extra_tags:
            if extra_tags.get("whispered", False) is True:
                filename += "w_"
            if extra_tags.get("pitch"):
                filename += f"p{extra_tags['pitch']}_"
        filepath = VOICES_PATH / voice_id / f"{filename}.ogg"
        filepath.parent.mkdir(parents=True, exist_ok=True)
        # Create the answer from Amazon Polly if the file does not exist
        if not filepath.exists():
            try:
                response = self.client.synthesize_speech(
                    Text=convert_to_ssml(text),
                    VoiceId=voice_id.split(" ")[0],
                    OutputFormat="ogg_vorbis",
                    TextType="ssml",
                )
                with filepath.open("wb") as file:
                    file.write(response["AudioStream"].read())
            except botocore.exceptions.ClientError as err:
                logger.error(err)
                return
        read_ogg_file(str(filepath), output_device_name)

    def test(self) -> bool:
        """Test Amazon Polly credentials.

        Returns
        -------
        bool
            The test result.
        """
        with contextlib.suppress(botocore.exceptions.ClientError):
            self.client.synthesize_speech(Text="test", VoiceId="Justin", OutputFormat="ogg_vorbis")
            return True
        return False


def read_ogg_file(filepath: str, output_device_name: str):
    """Reads an .ogg audio file and plays it using a specified output device.

    Parameters
    ----------
    filepath : str
        The path to the .ogg audio file.
    output_device_name : str
        The name of the output device to use for audio playback.
    """

    def stream_thread():
        pygame.mixer.music.load(filepath)
        pygame.mixer.music.play()
        # Wait until the audio finishes playing
        while pygame.mixer.music.get_busy():
            continue
        pygame.mixer.quit()

    pygame.mixer.pre_init(devicename=output_device_name)
    pygame.mixer.init()
    thread = threading.Thread(target=stream_thread)
    thread.start()
