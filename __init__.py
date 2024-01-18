import os
import re
import subprocess
import sys
import time
from os.path import join

from adapt.intent import IntentBuilder

from core.audio import wait_while_speaking
from core.llm import dialog_prompt, main_persona_prompt, status_report_prompt
from core.messagebus.message import Message
from core.skills import Skill, intent_handler

SECONDS = 5


class CoreSkill(Skill):
    def __init__(self):
        super(CoreSkill, self).__init__(name="CoreSkill")

    def initialize(self):
        core_path = os.path.join(os.path.dirname(sys.modules["core"].__file__), "..")
        self.core_path = os.path.abspath(core_path)
        self.interrupted_utterance = None
        self.playback_altered = False
        # self.add_event("core.wakeword", self.handle_wakeword)
        self.add_event("core.shutdown", self.handle_core_shutdown)
        self.add_event("core.reboot", self.handle_core_reboot)
        self.add_event("recognizer_loop:utterance", self.set_response_latency_callback)
        self.add_event("speak", self.cancel_response_latency_callback)
        # self.add_event(
        #     "recognizer_loop:audio_output_start",
        #     self.cancel_interrupted_utterance_callback,
        # )
        # self.add_event(
        #     "recognizer_loop:audio_output_end", self.set_interruption_handler
        # )
        self.add_event("recognizer_loop:audio_output_end", self.restore_playback_volume)
        # self.add_event("core.interrupted_utterance", self.set_interrupted_utterance)
        # self.add_event("core.wakeword", self.reduce_playback_volume)
        self.add_event("core.mic.listen", self.reduce_playback_volume)

    def reduce_playback_volume(self):
        self.playback_altered = True
        self.log.info("REDUCING SPOTIFY VOLUME")
        subprocess.run(
            [
                "osascript",
                "-e",
                (
                    'tell application "Spotify" to set sound volume to'
                    '(sound volume of application "Spotify") - 20'
                ),
            ]
        )

    def restore_playback_volume(self):
        if self.playback_altered:
            self.log.info("INCREASING SPOTIFY VOLUME")
            subprocess.run(
                [
                    "osascript",
                    "-e",
                    (
                        'tell application "Spotify" to set sound volume to'
                        '(sound volume of application "Spotify") + 20'
                    ),
                ]
            )
            self.playback_altered = False

    # def handle_wakeword(self, message):
    #     """handler for stop core when a new wakeword is called"""
    #     self.bus.emit(Message("core.audio.speech.stop"))

    # if after n seconds there's an interrupted utterance event, handle it
    # NOTE: the processing time of the conversation might cause this to be handled while
    # the new conversation is still ongoing
    def set_interruption_handler(self, event):
        self.schedule_event(
            self.handle_interrupted_utterance,
            when=7,
            name="handle_interrupted_utterance",
        )

    def cancel_interrupted_utterance_callback(self):
        self.cancel_scheduled_event("handle_interrupted_utterance")

    def set_interrupted_utterance(self, message):
        self.interrupted_utterance = message.data.get("utterance")

    def handle_interrupted_utterance(self):
        if self.interrupted_utterance:
            if "?" in self.interrupted_utterance:
                self.log.info(
                    f"Resuming interrupted utterance: {self.interrupted_utterance}"
                )
                context = (
                    "You were interrupted while saying the following utterance given in "
                    "the query. What you want to do is complete the interrupted utterance. "
                    "An example, 'Sir like I was saying, ...' or"
                    "'As I was saying before we were interrupted, ...' or"
                    "'Sir, Where was I? ...' "
                )
                interrupted_response = self.llm.llm_response(
                    prompt=dialog_prompt,
                    context=context,
                    query=self.interrupted_utterance,
                )
                wait_while_speaking()
                # listen if dialog ends with question mark
                # if_question_mark = interrupted_response.endswith("?")
                # self.speak(interrupted_response, expect_response=if_question_mark)
                # tts.store_interrupted_utterance(None)  # set interrupted_utterance None
                self.cancel_scheduled_event("handle_interrupted_utterance")
                self.bus.emit(Message("core.handled.interrupted_utterance"))
            self.interrupted_utterance = None

    # change yes to a a Vocabulary for flexibility
    @intent_handler(IntentBuilder("").require("Reboot"))
    def handle_reboot_request(self, message):
        self.users_word = message.data["Reboot"]
        # NOTE: uncomment if preference for confirmation
        # if self.ask_yesno("confirm.reboot", {'users_word': self.users_word}) == "yes":
        #     self.bus.emit(Message("core.reboot"))
        # else:
        #     self.speak_dialog('dismissal.reboot', {'users_word': ''.join([self.users_word, 'ing'])})
        self.bus.emit(Message("core.reboot"))

    @intent_handler(IntentBuilder("").require("Shutdown").require("System"))
    def handle_shutdown_request(self, message):
        self.users_word = message.data["Shutdown"]
        if self.ask_yesno("confirm.shutdown", {"users_word": self.users_word}) == "yes":
            self.bus.emit(Message("core.shutdown"))
        else:
            self.speak_dialog("dismissal.shutdown")

    @intent_handler(IntentBuilder("").require("Mute").optionally("Microphone"))
    def handle_microphone_mute(self, message):
        self.bus.emit(Message("core.mic.mute"))

    def set_response_latency_callback(self, message):
        """Schedule notification to tell user that processing is longer than usual"""
        self.schedule_event(
            self.trigger_latency_dialog, when=SECONDS, name="GiveMeAMinute"
        )

    def trigger_latency_dialog(self, event):
        self.cancel_scheduled_event("GiveMeAMinute")
        self.bus.emit(Message("intent.service.response.latency"))

    # TODO: add handle_output function here
    # NOTE: might need to handle case where system is listening
    def cancel_response_latency_callback(self, event):
        self.cancel_scheduled_event("GiveMeAMinute")

    def handle_core_shutdown(self, message):
        """
        Shuts down core modules not the OS
        """
        self.speak_dialog("shutdown.core")
        time.sleep(2)
        path = join(self.core_path, "stop-core.sh")
        os.system(path)

    # TODO: make component only reboot
    def handle_core_reboot(self, message):
        """
        Restart core modules not the OS
        """
        self.speak_dialog(
            "restart.core",
            {"users_word": "".join([self.users_word, "ing"])},
            send_to_ui=True,
        )

        wait_while_speaking()
        path = join(self.core_path, "start-core.sh all restart")
        os.system(path)

    @intent_handler(IntentBuilder("").require("Reboot").require("Voice"))
    def handle_voice_reboot(self, message):
        """
        Restart voice component
        """
        utterance = message.data.get("utterance")
        context = "asking to restart your voice component"
        self.llm.llm_response(
            prompt=status_report_prompt, query=utterance, context=context
        )
        path = join(self.core_path, "start-core.sh")
        subprocess.call([path, "restart", "voice"])

    @intent_handler(IntentBuilder("").require("Reboot").require("Skills"))
    def handle_reboot_skills(self, message):
        """
        Restart skills component
        """
        utterance = message.data.get("utterance")
        context = "asking to restart your skills component"
        response = self.llm.llm_response(
            prompt=status_report_prompt, query=utterance, context=context
        )
        self.speak(response, wait=True)
        path = join(self.core_path, "start-core.sh")
        subprocess.call([path, "restart", "skills"])

    def handle_system_reboot(self, _):
        self.speak_dialog("rebooting", wait=True)
        wait_while_speaking()
        subprocess.call(["/usr/bin/systemctl", "reboot"])

    def handle_system_shutdown(self, _):
        subprocess.call(["/usr/bin/systemctl", "poweroff"])

    # TODO: Make this only work when "say" is the first word used in utterance

    # @intent_handler(IntentBuilder("").require("Speak").require("Words"))
    def speak_back(self, message):
        """
        Repeat the utterance back to the user.

        TODO: The method is very english centric and will need
              localization.
        """
        # Remove everything up to the speak keyword and repeat that
        utterance = message.data.get("utterance")
        repeat = re.sub("^.*?" + message.data["Speak"], "", utterance)
        self.speak(repeat.strip())

    # NOTE: this could just be handled as a normal conversation except ending.
    # so would it be possible to just use the main_persona prompt?
    # @intent_handler(IntentBuilder("dismiss.core").require("StopPhrase"))
    # def handle_dismiss_intent(self, message):
    #     utterance = message.data.get("utterance")
    #     self.interrupted_utterance = None
    #     self.cancel_scheduled_event("handle_interrupted_utterance")
    #     if self.settings.get("verbal_feedback_enabled", True):
    #         # self.speak_dialog('dismissed')
    #         self.llm.llm_response(
    #             prompt=main_persona_prompt, query=utterance
    #         )
    #         # self.speak(response)
    #
    #     self.log.info("USER DISMISSED SYSTEM.")

    def shutdown(self):
        self.remove_event("core.shutdown", self.handle_core_shutdown)
        self.remove_event("core.reboot", self.handle_core_reboot)


def create_skill():
    return CoreSkill()
