import os
import subprocess
import sys
import time
from os.path import join

from core.messagebus.message import Message
from core.skills import Skill, intent_handler


class CoreSkill(Skill):
    def __init__(self):
        super(CoreSkill, self).__init__(name="CoreSkill")

    def initialize(self):
        core_path = os.path.join(os.path.dirname(sys.modules['core'].__file__),
                                 '..')
        self.core_path = os.path.abspath(core_path)
        self.add_event('core.shutdown', self.handle_core_shutdown)
        self.add_event('core.reboot', self.handle_core_reboot)
        self.add_event('question:query', self.handle_response)
        self.add_event('recognizer_loop:audio_output_start', self.handle_output)

    # change yes to a a Vocabulary for flexibility
    @intent_handler("reboot.intent")
    def handle_reboot(self, event):
        if self.ask_yesno("confirm.reboot") == "yes":
            self.bus.emit(Message("core.reboot"))

    @intent_handler("shutdown.intent")
    def handle_shutdown(self, event):
        if self.ask_yesno("confirm.shutdown") == "yes":
            self.bus.emit(Message("core.shutdown"))

    def handle_response(self, message):
        # self.timeout_time = time.time() + 4
        self.schedule_event(self.taking_too_long, when=4, name='GiveMeAMinute')

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
        self.log.info(path)
        os.system(path)

    def handle_core_reboot(self, message):
        """
        Restart mycroft modules not the OS
        """
        self.speak_dialog('restart.core')
        time.sleep(2)
        path = join(self.core_path, 'start-core.sh all restart')
        self.log.info(path)
        os.system(path)

    def handle_system_reboot(self, _):
        self.speak_dialog("rebooting", wait=True)
        subprocess.call(["/usr/bin/systemctl", "reboot"])

    def handle_system_shutdown(self, _):
        subprocess.call(["/usr/bin/systemctl", "poweroff"])

    def shutdown(self):
        self.remove_event('core.shutdown', self.handle_core_shutdown)
        self.remove_event('core.reboot', self.handle_core_reboot)


def create_skill():
    return CoreSkill()
