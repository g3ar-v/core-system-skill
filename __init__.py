import os
import re
import subprocess
import sys
import time
from os.path import join

from langchain.prompts import PromptTemplate
from adapt.intent import IntentBuilder
from core.messagebus.message import Message
from core.audio import wait_while_speaking
from core.llm import LLM
from core.skills import Skill, intent_handler

SECONDS = 6
template = """
You're a personal assistant; you're a witty, insightful and knowledgeable
companion. Your persona is a blend of Alan Watts, JARVIS from Iron Man
meaning. Your responses are clever and thoughtful with brevity. Often you
provide responses in a style reminiscent of Alan Watts. You address me as
"Sir" in a formal tone, throughout our interactions. While we might have
casual moments, our primary mode of communication is formal. {context}
##(respond with the sentence only)
query: {query}
"""

prompt = PromptTemplate(input_variables=["context", "query"], template=template)


class CoreSkill(Skill):
    def __init__(self):
        super(CoreSkill, self).__init__(name="CoreSkill")

    def initialize(self):
        core_path = os.path.join(os.path.dirname(sys.modules["core"].__file__), "..")
        self.core_path = os.path.abspath(core_path)
        self.add_event("core.skills.initialized", self.handle_boot_finished)
        self.add_event("core.shutdown", self.handle_core_shutdown)
        self.add_event("core.reboot", self.handle_core_reboot)
        self.add_event("question:query", self.handle_response)
        self.add_event("question:action", self.handle_output)
        self.add_event("recognizer_loop:audio_output_start", self.handle_output)

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

    def handle_output(self):
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
        response = LLM.use_llm(prompt=prompt, query=utterance, context=context)
        self.speak(response, wait=True)
        # self.speak_dialog("rebooting", wait=True)
        path = join(self.core_path, "start-core.sh")
        subprocess.call([path, "restart", "voice"])

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
        if self.settings.get("verbal_feedback_enabled", True):
            # self.speak_dialog('dismissed')
            utterance = message.data.get("utterance")
            context = (
                "Do not ask any question just give a remark to end the "
                "conversation. Your reply should be ending the conversation, "
                "'alright', 'okay' or something similar would do.the responses "
                "should not include the prefix 'response: <phrase>' just "
                "'<phrase>' "
            )
            response = LLM.use_llm(prompt=prompt, context=context, utterance=utterance)
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
