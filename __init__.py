import os
import re
import subprocess
import sys
import time
from os.path import join

from adapt.intent import IntentBuilder
from core.messagebus.message import Message
from core.skills import Skill, intent_handler

SECONDS = 5


class CoreSkill(Skill):
    def __init__(self):
        super(CoreSkill, self).__init__(name="CoreSkill")

    def initialize(self):
        core_path = os.path.join(os.path.dirname(sys.modules['core'].__file__),
                                 '..')
        self.core_path = os.path.abspath(core_path)
        self.add_event("core.skills.initialized", self.handle_boot_finished)
        self.add_event('core.shutdown', self.handle_core_shutdown)
        self.add_event('core.reboot', self.handle_core_reboot)
        self.add_event('question:query', self.handle_response)
        self.add_event('question:action', self.handle_output)
        self.add_event('recognizer_loop:audio_output_start', self.handle_output)

    # change yes to a a Vocabulary for flexibility
    @intent_handler(IntentBuilder('').require('Reboot'))
    def handle_reboot_request(self, message):
        self.users_word = message.data["Reboot"]
        if self.ask_yesno("confirm.reboot", {'users_word': self.users_word}) == "yes":
            self.bus.emit(Message("core.reboot"))
        else:
            self.speak_dialog('dismissal.reboot', {'users_word': ''.join([self.users_word, 'ing'])})

    @intent_handler(IntentBuilder("").require("Shutdown").optionally("System"))
    def handle_shutdown_request(self, message):
        self.users_word = message.data["Shutdown"]
        if self.ask_yesno("confirm.shutdown", {'users_word': self.users_word}) == "yes":
            self.bus.emit(Message("core.shutdown"))
        else:
            self.speak_dialog('dismissal.shutdown')

    def handle_response(self, message):
        """ Send notification to user that processing is longer than usual"""
        self.schedule_event(self.taking_too_long, when=SECONDS,
                            name='GiveMeAMinute')

    def taking_too_long(self, event):
        self.bus.emit(Message('recognizer_loop:audio_output_timeout'))
        self.cancel_scheduled_event('GiveMeAMinute')

    def handle_output(self):
        self.cancel_scheduled_event('GiveMeAMinute')

    def handle_core_shutdown(self, message):
        """
        Shuts down mycroft modules not the OS
        """
        self.speak_dialog('shutdown.core')
        time.sleep(2)
        path = join(self.core_path, 'stop-core.sh')
        os.system(path)

    def handle_core_reboot(self, message):
        """
        Restart mycroft modules not the OS
        """
        self.speak_dialog('restart.core', {'users_word': ''.join([self.users_word, 'ing'])})
        time.sleep(2)
        path = join(self.core_path, 'start-core.sh all restart')
        os.system(path)

    def handle_system_reboot(self, _):
        self.speak_dialog("rebooting", wait=True)
        subprocess.call(["/usr/bin/systemctl", "reboot"])

    def handle_system_shutdown(self, _):
        subprocess.call(["/usr/bin/systemctl", "poweroff"])

    @intent_handler(IntentBuilder("").require("Speak").require("Words"))
    def speak_back(self, message):
        """
            Repeat the utterance back to the user.

            TODO: The method is very english centric and will need
                  localization.
        """
        # Remove everything up to the speak keyword and repeat that
        utterance = message.data.get('utterance')
        repeat = re.sub('^.*?' + message.data['Speak'], '', utterance)
        self.speak(repeat.strip())

    @intent_handler(IntentBuilder('dismiss.mycroft').require('Nevermind'))
    def handle_dismiss_intent(self, message):
        if self.settings.get('verbal_feedback_enabled', True):
            self.speak_dialog('dismissed')
        self.log.info("User dismissed Mycroft.")

    def handle_boot_finished(self):
        self.speak_dialog('finished.booting')
        self.log.debug('finished booting')

    @intent_handler(IntentBuilder("").require("Stop"))
    def handle_stop(self, event):
        self.bus.emit(Message("core.stop"))
        self.speak_dialog('dismissed')

    def shutdown(self):
        self.remove_event('core.shutdown', self.handle_core_shutdown)
        self.remove_event('core.reboot', self.handle_core_reboot)


def create_skill():
    return CoreSkill()
