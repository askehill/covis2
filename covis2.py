import concurrent
import json
import logging
import os
import sys
from pathlib import Path

import google.auth.transport.grpc
import google.auth.transport.requests
import google.oauth2.credentials
from google.assistant.embedded.v1alpha2 import embedded_assistant_pb2, embedded_assistant_pb2_grpc
from googlesamples.assistant.grpc import (audio_helpers, assistant_helpers, browser_helpers, device_helpers)

logging.basicConfig(level=logging.INFO)

ASSISTANT_API_ENDPOINT = 'embeddedassistant.googleapis.com'
END_OF_UTTERANCE = embedded_assistant_pb2.AssistResponse.END_OF_UTTERANCE
DIALOG_FOLLOW_ON = embedded_assistant_pb2.DialogStateOut.DIALOG_FOLLOW_ON
CLOSE_MICROPHONE = embedded_assistant_pb2.DialogStateOut.CLOSE_MICROPHONE
PLAYING = embedded_assistant_pb2.ScreenOutConfig.PLAYING
DEFAULT_GRPC_DEADLINE = 60 * 3 + 5


class CovisAssistant(object):

    def __init__(self, language_code, device_model_id, device_id,
                 conversation_stream, display,
                 channel, deadline_sec, device_handler):
        self.device_model_id = device_model_id
        self.language_code = language_code
        self.device_model_id = device_model_id
        self.device_id = device_id
        self.conversation_stream = conversation_stream
        self.display = display
        self.conversation_state = None
        self.is_new_conversation = True
        self.assistant = embedded_assistant_pb2_grpc.EmbeddedAssistantStub(
            channel
        )
        self.deadline = deadline_sec
        self.device_handler = device_handler

    def __enter__(self):
        return self

    def __exit__(self, etype, e, traceback):
        if e:
            return False
        self.conversation_stream.close()

    def assist(self):
        continue_conversation = False
        device_actions_futures = []
        self.conversation_stream.start_recording()
        logging.info('Recording Audio Request.')

        def iter_log_assist_requests():
            for c in self.gen_assist_requests():
                assistant_helpers.log_assist_request_without_audio(c)
                yield c
            logging.debug('Reached end of AssistRequest iteration.')

            # This generator yields AssistResponse proto messages
            # received from the gRPC Google Assistant API.

        for resp in self.assistant.Assist(iter_log_assist_requests(),
                                          self.deadline):
            assistant_helpers.log_assist_response_without_audio(resp)
            if resp.event_type == END_OF_UTTERANCE:
                logging.info('End of audio request detected.')
                logging.info('Stopping recording.')
                self.conversation_stream.stop_recording()
            if resp.speech_results:
                logging.info('Transcript of user request: "%s".',
                             ' '.join(r.transcript
                                      for r in resp.speech_results))
            if len(resp.audio_out.audio_data) > 0:
                if not self.conversation_stream.playing:
                    self.conversation_stream.stop_recording()
                    self.conversation_stream.start_playback()
                    logging.info('Playing assistant response.')
                self.conversation_stream.write(resp.audio_out.audio_data)
            if resp.dialog_state_out.conversation_state:
                conversation_state = resp.dialog_state_out.conversation_state
                logging.debug('Updating conversation state.')
                self.conversation_state = conversation_state
            if resp.dialog_state_out.volume_percentage != 0:
                volume_percentage = resp.dialog_state_out.volume_percentage
                logging.info('Setting volume to %s%%', volume_percentage)
                self.conversation_stream.volume_percentage = volume_percentage
            if resp.dialog_state_out.microphone_mode == DIALOG_FOLLOW_ON:
                continue_conversation = True
                logging.info('Expecting follow-on query from user.')
            elif resp.dialog_state_out.microphone_mode == CLOSE_MICROPHONE:
                continue_conversation = False
            if resp.device_action.device_request_json:
                device_request = json.loads(
                    resp.device_action.device_request_json
                )
                fs = self.device_handler(device_request)
                if fs:
                    device_actions_futures.extend(fs)
            if self.display and resp.screen_out.data:
                system_browser = browser_helpers.system_browser
                system_browser.display(resp.screen_out.data)

        if len(device_actions_futures):
            logging.info('Waiting for device executions to complete.')
            concurrent.futures.wait(device_actions_futures)

        logging.info('Finished playing assistant response.')
        self.conversation_stream.stop_playback()
        return continue_conversation

    def gen_assist_requests(self):
        """Yields: AssistRequest messages to send to the API."""

        config = embedded_assistant_pb2.AssistConfig(
            audio_in_config=embedded_assistant_pb2.AudioInConfig(
                encoding='LINEAR16',
                sample_rate_hertz=self.conversation_stream.sample_rate,
            ),
            audio_out_config=embedded_assistant_pb2.AudioOutConfig(
                encoding='LINEAR16',
                sample_rate_hertz=self.conversation_stream.sample_rate,
                volume_percentage=self.conversation_stream.volume_percentage,
            ),
            dialog_state_in=embedded_assistant_pb2.DialogStateIn(
                language_code=self.language_code,
                conversation_state=self.conversation_state,
                is_new_conversation=self.is_new_conversation,
            ),
            device_config=embedded_assistant_pb2.DeviceConfig(
                device_id=self.device_id,
                device_model_id=self.device_model_id,
            )
        )

        if self.display:
            config.screen_out_config.screen_mode = PLAYING
        # Continue current conversation with later requests.
        self.is_new_conversation = False
        # The first AssistRequest must contain the AssistConfig
        # and no audio data.
        yield embedded_assistant_pb2.AssistRequest(config=config)
        for data in self.conversation_stream:
            # Subsequent requests need audio data, but not config.
            yield embedded_assistant_pb2.AssistRequest(audio_in=data)

    def get_body_temperature(self):
        print(self.display)

def main():
    creds = os.path.join(Path.home(), 'covis2', 'credentials.json')
    api_endpoint = 'embeddedassistant.googleapis.com'
    device_config = 'device_config.json'

    # Load OAuth 2.0 credentials.
    try:
        with open(creds, 'r') as f:
            credentials = google.oauth2.credentials.Credentials(token=None,
                                                                **json.load(f))
            http_request = google.auth.transport.requests.Request()
            credentials.refresh(http_request)
    except Exception as e:
        logging.error('Error loading credentials: %s', e)
        logging.error('Run google-oauthlib-tool to initialize '
                      'new OAuth 2.0 credentials.')
        sys.exit(-1)

    # Create an authorized gRPC channel.
    grpc_channel = google.auth.transport.grpc.secure_authorized_channel(
        credentials, http_request, api_endpoint)
    logging.info('Connecting to %s', api_endpoint)

    audio_device = None
    audio_source = audio_device = (
            audio_device or audio_helpers.SoundDeviceStream(
        sample_rate=audio_helpers.DEFAULT_AUDIO_SAMPLE_RATE,
        sample_width=audio_helpers.DEFAULT_AUDIO_SAMPLE_WIDTH,
        block_size=audio_helpers.DEFAULT_AUDIO_DEVICE_BLOCK_SIZE,
        flush_size=audio_helpers.DEFAULT_AUDIO_DEVICE_FLUSH_SIZE
    )
    )
    audio_sink = audio_device = (
            audio_device or audio_helpers.SoundDeviceStream(
        sample_rate=audio_helpers.DEFAULT_AUDIO_SAMPLE_RATE,
        sample_width=audio_helpers.DEFAULT_AUDIO_SAMPLE_WIDTH,
        block_size=audio_helpers.DEFAULT_AUDIO_DEVICE_BLOCK_SIZE,
        flush_size=audio_helpers.DEFAULT_AUDIO_DEVICE_FLUSH_SIZE
    )
    )

    conversation_stream = audio_helpers.ConversationStream(
        source=audio_source,
        sink=audio_sink,
        iter_size=audio_helpers.DEFAULT_AUDIO_ITER_SIZE,
        sample_width=audio_helpers.DEFAULT_AUDIO_SAMPLE_WIDTH,
    )

    try:
        with open(device_config) as f:
            device = json.load(f)
            device_id = device['id']
            device_model_id = device['model_id']
    except Exception as e:
        logging.warning('Device config not found: %s' % e)
        sys.exit(-1)

    device_handler = device_helpers.DeviceRequestHandler(device_id)

    logging.info('Getting ready to hand off to Google')

    with CovisAssistant('en-GB', device_model_id, device_id, conversation_stream, True,
                        grpc_channel, DEFAULT_GRPC_DEADLINE, device_handler) as assistant:

        while True:
            continue_conversation = assistant.assist()
            if not continue_conversation:
                break
    logging.info('Exiting now...')


if __name__ == '__main__':
    main()
