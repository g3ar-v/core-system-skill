from core.skills.core import MycroftSkill, intent_file_handler
from core.util.log import LOG
from os.path import join, expanduser, abspath
import os
import sys


class LinuxSkill(MycroftSkill):
    def __init__(self):
        super(LinuxSkill, self).__init__(name="LinuxSkill")

    def initialize(self):

        mycroft_core_path = os.path.join(os.path.dirname(sys.modules['core'].__file__), '..')
        self.mycroft_core_path = os.path.abspath(mycroft_core_path)

        print("mycroft-core path:", mycroft_core_path)

        self.add_event('system.shutdown', self.handler_system_shutdown)
        self.add_event('system.reboot', self.handler_system_reboot)

    def handler_system_shutdown(self, message):
        """
        Shuts down mycroft modules not the OS
        """
        path = join(self.mycroft_core_path, 'stop-mycroft.sh')
        LOG.info(path)
        os.system(path)

    def handler_system_reboot(self, message):
        """
        Restart mycroft modules not the OS
        """
        path = join(self.mycroft_core_path, 'start-mycroft.sh all restart')
        LOG.info(path)
        os.system(path)

    def stop(self):
        pass


def create_skill():
    return LinuxSkill()
