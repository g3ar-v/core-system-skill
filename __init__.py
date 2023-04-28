import os
import subprocess
import sys
import time
from os.path import join

from core.skills.core import MycroftSkill
from core.util.log import LOG


class LinuxSkill(MycroftSkill):
    def __init__(self):
        super(LinuxSkill, self).__init__(name="LinuxSkill")

    def initialize(self):

        mycroft_core_path = os.path.join(os.path.dirname(sys.modules['core'].__file__),
                                         '..')
        self.mycroft_core_path = os.path.abspath(mycroft_core_path)

        print("mycroft-core path:", mycroft_core_path)

        self.add_event('system.shutdown', self.handler_core_shutdown)
        self.add_event('system.reboot', self.handler_core_reboot)

    def handler_core_shutdown(self, message):
        """
        Shuts down mycroft modules not the OS
        """
        self.speak_dialog('shutdown.core')
        time.sleep(2)
        path = join(self.mycroft_core_path, 'stop-mycroft.sh')
        LOG.info(path)
        os.system(path)

    def handler_core_reboot(self, message):
        """
        Restart mycroft modules not the OS
        """
        self.speak_dialog('restart.core')
        time.sleep(2)
        path = join(self.mycroft_core_path, 'start-mycroft.sh all restart')
        LOG.info(path)
        os.system(path)

    def handle_system_reboot(self, _):
        self.speak_dialog("rebooting", wait=True)
        subprocess.call(["/usr/bin/systemctl", "reboot"])

    def handle_system_shutdown(self, _):
        subprocess.call(["/usr/bin/systemctl", "poweroff"])

    def stop(self):
        pass


def create_skill():
    return LinuxSkill()
