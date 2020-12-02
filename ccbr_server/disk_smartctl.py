import json
import logging
import os
import subprocess
import sys
from functools import partial
from tempfile import TemporaryFile

# There is a bug with partial() and Pool.map() for py < 2.7, fixed by using mp.dummy.Pool
if sys.version_info[0] == 2 and sys.version_info[1] < 7:
    from multiprocessing.dummy import Pool
else:
    from multiprocessing import Pool

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


def check_smart(device, smartctl, timeout):
    cmd = ['timeout', str(timeout), smartctl, '--json=c', '--all', '-B',
           '+' + os.path.join(project_root, 'lib/smart/drivedb.h')]
    if 'megaraid' in device['type']:
        cmd += ['--device', device['type']]
    cmd += [device['name']]
    log.debug("Getting SMART for %s: %s", device['name'], ' '.join(cmd))

    out = None

    with TemporaryFile() as tmp:
        ret = subprocess.call(cmd, stdout=tmp)

        if ret != 124:  # Not Timeout
            tmp.seek(0)
            out = tmp.read()
        else:
            log.warning("smartctl timeout for %s", device['name'])

    errors = []

    if ret != 0:
        for bit, error in enumerate(RETURN_CODES):
            isbit = (ret >> bit) & 1
            if isbit:
                errors.append(bit)

    if out:
        device_out = json.loads(out)
        device_out['errors'] = errors
        return device, device_out

    return device, None


class SmartReport(Report):
    """ Parses output of smartctl included with this code
    """
    name = 'smartctl'
    disks = []

    def __init__(self, timeout=10, concurrency=4):
        """
        :param int|str timeout: smartctl timeout in seconds
        :param int|str concurrency: Thread pool size for concurrent checking
        """
        self.timeout = int(timeout)
        self.concurrency = int(concurrency)

        self.executable = self.get_executable()

        if not os.path.exists(self.executable):
            raise ReportException()

        self._check_version()

    def _check_version(self):
        cmd = [self.executable, '-V']
        log.debug("Checking smartctl version: '%s'", ' '.join(cmd))

        p = subprocess.Popen(cmd, stdout=subprocess.PIPE)
        out, _ = p.communicate()

        if p.returncode != 0:
            raise ReportException("Problem executing smartctl")

        first_line = out.decode().splitlines()[0]
        version = first_line.split()[1]
        major = int(version.split('.')[0])

        if major < 7:
            raise ReportException("Smartctl >= 7.0 required (for --json option)")

        log.debug("Found acceptable version '%s'", version)

    # noinspection PyMethodMayBeStatic
    def get_executable(self):
        config = get_config()

        if config.has_option('smart', 'exec') and config.get('smart', 'exec'):
            return config.get('smart', 'exec')
        return os.path.join(project_root, 'lib/smart/smartctl')

    def collect_data(self):
        cmd = [self.executable, '--json=c', '--scan']
        log.debug("Discover all available drives: '%s'", ' '.join(cmd))

        p = subprocess.Popen(cmd, stdout=subprocess.PIPE)
        out, _ = p.communicate()

        if p.returncode != 0:
            raise ReportException("Problem executing smartctl")

        self.disks = []

        devices = json.loads(out)

        log.info("Found %d drives", len(devices['devices']))

        log.debug("Creating smartctl check thread pool of size %s", self.concurrency)
        pool = Pool(processes=self.concurrency)
        res = pool.map(partial(check_smart, smartctl=self.executable, timeout=self.timeout), devices['devices'])
        for device_in, device_out in res:
            if device_out is None:
                device_out = {'device': device_in, 'errors': [-1]}  # We timed out

            self.disks.append(device_out)
        pool.close()

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
    log.setLevel(logging.DEBUG)
    logging.basicConfig(level=log.level)

    # noinspection PyCompatibility
    import argparse
    parser = argparse.ArgumentParser(description='Check smartctl output')
    _ = parser.parse_args()

    hds = SmartReport()
    hds.collect_data()
    hds.stdout()


if __name__ == '__main__':
    main()
