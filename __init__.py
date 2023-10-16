import os
import re
import subprocess
import sys
import time
from os.path import join

from adapt.intent import IntentBuilder
from core.messagebus.message import Message
from core.audio import wait_while_speaking
from core.llm import LLM, stat_report_prompt, dialog_prompt
from core.skills import Skill, intent_handler

SECONDS = 6


class CoreSkill(Skill):
    def __init__(self):
        super(CoreSkill, self).__init__(name="CoreSkill")

    def initialize(self):
        core_path = os.path.join(os.path.dirname(sys.modules["core"].__file__), "..")
        self.core_path = os.path.abspath(core_path)
        self.interrupted_utterance = None
        self.add_event("core.skills.initialized", self.handle_boot_finished)
        self.add_event("core.shutdown", self.handle_core_shutdown)
        self.add_event("core.reboot", self.handle_core_reboot)
        self.add_event("question:query", self.handle_response)
        self.add_event("question:action", self.handle_audio_output_start)
        self.add_event(
            "recognizer_loop:audio_output_start", self.handle_audio_output_start
        )
        self.add_event(
            "recognizer_loop:audio_output_start", self.handle_audio_output_start
        )
        self.add_event("recognizer_loop:audio_output_end", self.handle_audio_output_end)
        self.add_event("core.interrupted_utterance", self.set_interrupted_utterance)

    # if after 5 seconds there's an interrupted utterance event, handle it
    def handle_audio_output_end(self, event):
        self.schedule_event(
            self.handle_interrupted_utterance,
            when=6,
            name="handle_interrupted_utterance",
        )

    # TODO: add handle_output function here
    # NOTE: might need to handle case where system is listening
    def handle_audio_output_start(self, event):
        self.cancel_scheduled_event("GiveMeAMinute")
        self.cancel_scheduled_event("handle_interrupted_utterance")

    def set_interrupted_utterance(self, message):
        self.interrupted_utterance = message.data.get("utterance")

    def handle_interrupted_utterance(self):
        if self.interrupted_utterance:
            self.log.debug(
                f"Resuming interrupted utterance: {self.interrupted_utterance}"
            )
            context = (
                "You were interrupted while saying the following utterance given in "
                "the query. What you want to do complete the interrupted utterance. "
                "An example, 'Sir like I was saying, ...' or"
                "'As I was saying before we were interrupted, ...' or"
                "'Where was I? Let me continue with what I was saying earlier...' "
            )
            interrupted_response = LLM.use_llm(
                prompt=dialog_prompt, context=context, query=self.interrupted_utterance
            )
            wait_while_speaking()
            # listen if dialog ends with question mark
            if_question_mark = interrupted_response.endswith("?")
            self.speak(interrupted_response, expect_response=if_question_mark)
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
        self.speak_dialog("microphone.muted")

    def handle_response(self, message):
        """Send notification to user that processing is longer than usual"""
        self.schedule_event(self.taking_too_long, when=SECONDS, name="GiveMeAMinute")

    def taking_too_long(self, event):
        self.bus.emit(Message("recognizer_loop:audio_output_timeout"))
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
            "restart.core", {"users_word": "".join([self.users_word, "ing"])}
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
        response = LLM.use_llm(
            prompt=stat_report_prompt, query=utterance, context=context
        )
        self.speak(response, wait=True)
        # self.speak_dialog("rebooting", wait=True)
        path = join(self.core_path, "start-core.sh")
        subprocess.call([path, "restart", "voice"])

    @intent_handler(IntentBuilder("").require("Reboot").require("Skills"))
    def handle_reboot_skills(self, message):
        """
        Restart skills component
        """
        utterance = message.data.get("utterance")
        context = "asking to restart your skills component"
        response = LLM.use_llm(
            prompt=stat_report_prompt, query=utterance, context=context
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

    @intent_handler(IntentBuilder("dismiss.core").require("StopPhrase"))
    def handle_dismiss_intent(self, message):
        self.interrupted_utterance = None
        self.cancel_scheduled_event("handle_interrupted_utterance")
        if self.settings.get("verbal_feedback_enabled", True):
            # self.speak_dialog('dismissed')
            utterance = message.data.get("utterance")
            context = (
                "your goal is to intelligently conclude a conversation based on "
                "the user's utterance. Your aim is to provide a satisfactory response "
                "that effectively ends the dialogue. You should strive to craft a "
                "response that is concise and clear, such as 'Alright' or 'Okay' "
                "without initiating any new questions or topics. The purpose of your "
                "response is to bring closure to the conversation without leaving any "
                "loose ends."
            )
            response = LLM.use_llm(
                prompt=dialog_prompt, context=context, utterance=utterance
            )
            self.speak(response)
        self.log.info("User dismissed System.")

    def handle_boot_finished(self):
        self.speak_dialog("finished.booting")
        self.log.debug("finished booting")

    # # HACK: hack to stop conversation from going on forever, a more efficient code required
    # @intent_handler(IntentBuilder("").require("Stop"))
    # def handle_stop(self, event):
    #     self.bus.emit(Message("core.stop"))
    #     self.speak_dialog('dismissed')

    def shutdown(self):
        self.remove_event("core.shutdown", self.handle_core_shutdown)
        self.remove_event("core.reboot", self.handle_core_reboot)


def create_skill():
    return CoreSkill()
