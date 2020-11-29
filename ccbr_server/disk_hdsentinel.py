import logging
import os
import subprocess
from xml.etree import ElementTree

from ccbr_server.common import Report, get_config, project_root, ReportException

log = logging.getLogger(__file__)


class HDSentinelReport(Report):
    """ Parses output of Hard Disk Sentinel (https://www.hdsentinel.com/hard_disk_sentinel_linux.php) included with
    this code
    """
    name = 'hdsentinel'
    disks = []

    def __init__(self):
        self.executable = self.get_executable()

        if not os.path.exists(self.executable):
            raise ReportException()

    # noinspection PyMethodMayBeStatic
    def get_executable(self):
        config = get_config()

        if config.has_option('hdsentinel', 'exec') and config.get('hdsentinel', 'exec'):
            return config.get('hdsentinel', 'exec')
        return os.path.join(project_root, 'lib/hdsentinel/hdsentinel-018c-x64')

    def collect_data(self):
        p = subprocess.Popen([self.executable, '-xml', '-dump'], stdout=subprocess.PIPE)
        out, _ = p.communicate()

        if p.returncode != 0:
            raise ReportException("Problem executing hdsentinel")

        self.disks = []

        xml = ElementTree.fromstring(out)
        for disk_el in xml:
            if disk_el.tag.startswith('Physical_Disk_Information_'):
                disk = {}

                for topic_el in disk_el:
                    if 'S.M.A.R.T.' in topic_el.tag:  # Weird format, don't need it anyway
                        continue

                    topic = {}

                    for prop_el in topic_el:
                        if prop_el.tag in topic:
                            topic[prop_el.tag] += ', %s' % prop_el.text
                        else:
                            topic[prop_el.tag] = prop_el.text or ''

                    disk[topic_el.tag] = topic

                self.disks.append(disk)

        return self

    def to_dict(self):
        return {
            'ver': 1,
            'disks': self.disks
        }

    def stdout(self):
        import json
        print(json.dumps(self.disks, indent=4, sort_keys=True))


report = HDSentinelReport


def main():
    # noinspection PyCompatibility
    import argparse
    parser = argparse.ArgumentParser(description='Check hdsentinel output')
    _ = parser.parse_args()

    hds = HDSentinelReport()
    hds.collect_data()
    hds.stdout()


if __name__ == '__main__':
    main()
