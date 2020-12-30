#!/usr/bin/env python

# Copyright 2020 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""DialogFlow API Detect Intent Python sample with audio file.

Examples:
  python detect_intent_audio.py -h
  python detect_intent_audio.py --agent AGENT \
  --session-id SESSION_ID --audio-file-path resources/hello.wav
"""

import argparse
import uuid

from google.cloud.dialogflowcx_v3beta1.services.agents import AgentsClient
from google.cloud.dialogflowcx_v3beta1.services.sessions import SessionsClient
from google.cloud.dialogflowcx_v3beta1.types import audio_config
from google.cloud.dialogflowcx_v3beta1.types import session


# [START dialogflow_detect_intent_audio]
def run_sample():
    # TODO(developer): Replace these values when running the function
    project_id = "covis2"
    # For more information about regionalization see https://cloud.google.com/dialogflow/cx/docs/how/region
    location_id = "en-US"
    # For more info on agents see https://cloud.google.com/dialogflow/cx/docs/concept/agent
    agent_id = "covis2"
    agent = f"projects/{project_id}/locations/{location_id}/agents/{agent_id}"
    # For more information on sessions see https://cloud.google.com/dialogflow/cx/docs/concept/session
    session_id = str(uuid.uuid4())
    audio_file_path = "YOUR-AUDIO-FILE-PATH"
    # For more supported languages see https://cloud.google.com/dialogflow/es/docs/reference/language
    language_code = "en-us"

    detect_intent_audio(agent, session_id, audio_file_path, language_code)


def detect_intent_audio(agent, session_id, audio_file_path, language_code):
    """Returns the result of detect intent with an audio file as input.

    Using the same `session_id` between requests allows continuation
    of the conversation."""
    session_path = f"{agent}/sessions/{session_id}"
    print(f"Session path: {session_path}\n")
    client_options = None
    print(agent)
    agent_components = AgentsClient.parse_agent_path(agent)
    print(agent_components)
    location_id = agent_components["location"]
    if location_id != "global":
        api_endpoint = f"{location_id}-dialogflow.googleapis.com:443"
        print(f"API Endpoint: {api_endpoint}\n")
        client_options = {"api_endpoint": api_endpoint}
    session_client = SessionsClient(client_options=client_options)

    input_audio_config = audio_config.InputAudioConfig(
        audio_encoding=audio_config.AudioEncoding.AUDIO_ENCODING_LINEAR_16,
        sample_rate_hertz=44100,
    )

    with open(audio_file_path, "rb") as audio_file:
        input_audio = audio_file.read()

    audio_input = session.AudioInput(config=input_audio_config, audio=input_audio)
    query_input = session.QueryInput(audio=audio_input, language_code=language_code)
    request = session.DetectIntentRequest(session=session_path, query_input=query_input)
    response = session_client.detect_intent(request=request)

    print("=" * 20)
    print(f"Query text: {response.query_result.transcript}")
    response_messages = [
        " ".join(msg.text.text) for msg in response.query_result.response_messages
    ]
    print(f"Response text: {' '.join(response_messages)}\n")


# [END dialogflow_detect_intent_audio]

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--agent", help="Agent resource name.  Required.", required=True
    )
    parser.add_argument(
        "--session-id",
        help="Identifier of the DetectIntent session. " "Defaults to a random UUID.",
        default=str(uuid.uuid4()),
    )
    parser.add_argument(
        "--language-code",
        help='Language code of the query. Defaults to "en-US".',
        default="en-US",
    )
    parser.add_argument(
        "--audio-file-path", help="Path to the audio file.", required=True
    )

    args = parser.parse_args()

    detect_intent_audio(
        args.agent, args.session_id, args.audio_file_path, args.language_code
    )


# """Install the following requirements:
#     dialogflow        0.5.1
#     google-api-core   1.4.1
# """
# import os
# import dialogflow
# from google.api_core.exceptions import InvalidArgument
#
# os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = 'covis2-ed01cc28ce2e.json'
#
# DIALOGFLOW_PROJECT_ID = 'covis2'
# DIALOGFLOW_LANGUAGE_CODE = 'en-US'
# SESSION_ID = 'me'
#
# text_to_be_analyzed = "Do I have covid-19"
#
# session_client = dialogflow.SessionsClient()
# session = session_client.session_path(DIALOGFLOW_PROJECT_ID, SESSION_ID)
# text_input = dialogflow.types.TextInput(text=text_to_be_analyzed, language_code=DIALOGFLOW_LANGUAGE_CODE)
# query_input = dialogflow.types.QueryInput(text=text_input)
# try:
#     response = session_client.detect_intent(session=session, query_input=query_input)
# except InvalidArgument:
#     raise
#
#
# print("Query text:", response.query_result.query_text)
# print("Detected intent:", response.query_result.intent.display_name)
# print("Detected intent confidence:", response.query_result.intent_detection_confidence)
# print("Fulfillment text:", response.query_result.fulfillment_text)