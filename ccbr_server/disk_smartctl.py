import json
import logging
import os
import subprocess

from ccbr_server.common import Report, get_config, project_root, ReportException

log = logging.getLogger(__file__)

RETURN_CODES = [
    'Command line did not parse.',
    'Device open failed, device did not return an IDENTIFY DEVICE structure, or device is in a low-power mode',
    'Some SMART or other ATA command to the disk failed, or there was a checksum error in a SMART data structure',
    'SMART status check returned "DISK FAILING"',
    'We found prefail Attributes <= threshold',
    'SMART status check returned "DISK OK" but we found that some (usage or prefail) Attributes have been <= threshold '
    'at some time in the past',
    'The device error log contains records of errors',
    'The device self-test log contains records of errors'
]


class SmartReport(Report):
    """ Parses output of smartctl included with this code
    """
    name = 'smartctl'
    disks = []

    def __init__(self):
        self.executable = self.get_executable()

        if not os.path.exists(self.executable):
            raise ReportException()

        self._check_version()

    def _check_version(self):
        p = subprocess.Popen([self.executable, '-V'], stdout=subprocess.PIPE)
        out, _ = p.communicate()

        if p.returncode != 0:
            raise ReportException("Problem executing smartctl")

        first_line = out.decode().splitlines()[0]
        version = first_line.split()[1]
        major = int(version.split('.')[0])

        if major < 7:
            raise ReportException("Smartctl >= 7.0 required (for --json option)")

    # noinspection PyMethodMayBeStatic
    def get_executable(self):
        config = get_config()

        if config.has_option('smart', 'exec') and config.get('smart', 'exec'):
            return config.get('smart', 'exec')
        return os.path.join(project_root, 'lib/smart/smartctl')

    def collect_data(self):
        p = subprocess.Popen([self.executable, '--json=c', '--scan'], stdout=subprocess.PIPE)
        out, _ = p.communicate()

        if p.returncode != 0:
            raise ReportException("Problem executing smartctl")

        self.disks = []

        devices = json.loads(out)

        for device in devices['devices']:
            cmd = [self.executable, '--json=c', '--all']
            if 'megaraid' in device['type']:
                cmd += ['--device', device['type']]
            cmd += [device['name']]

            p = subprocess.Popen(cmd, stdout=subprocess.PIPE)
            out, _ = p.communicate()

            errors = []

            if p.returncode != 0:
                for bit, error in enumerate(RETURN_CODES):
                    isbit = (p.returncode >> bit) & 1
                    if isbit:
                        errors.append(bit)

            if out:
                device_out = json.loads(out)
                device_out['errors'] = errors
                self.disks.append(device_out)

        return self

    def to_dict(self):
        return {
            'ver': 1,
            'disks': self.disks
        }

    def stdout(self):
        import json
        print(json.dumps(self.disks, indent=4, sort_keys=True))


report = SmartReport


def main():
    # noinspection PyCompatibility
    import argparse
    parser = argparse.ArgumentParser(description='Check smartctl output')
    _ = parser.parse_args()

    hds = SmartReport()
    hds.collect_data()
    hds.stdout()


if __name__ == '__main__':
    main()
