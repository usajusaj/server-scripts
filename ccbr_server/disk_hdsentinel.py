import logging

from ccbr_server.common import Report, get_config

log = logging.getLogger(__file__)


class HDSentinelReport(Report):
    """ Parses output of Hard Disk Sentinel (https://www.hdsentinel.com/hard_disk_sentinel_linux.php) included with
    this code
    """
    name = 'hdsentinel'

    def __init__(self):
        config = get_config()
        self.executable = ''

    def collect_data(self):
        """ Check NFS concurrently to avoid long wait times if there's a lot of stale mounts
        """

    def to_dict(self):
        return {
            'ver': 1,
        }

    def stdout(self):
        pass


report = HDSentinelReport


def main():
    # noinspection PyCompatibility
    import argparse
    parser = argparse.ArgumentParser(description='Check hdsentinel output')
    _ = parser.parse_args()

    nfs = HDSentinelReport()
    nfs.collect_data()
    nfs.stdout()


if __name__ == '__main__':
    main()
