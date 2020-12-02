import logging
import os
import re
import subprocess
from collections import defaultdict
from functools import partial
from tempfile import TemporaryFile

from ccbr_server.common import get_pool
from ccbr_server.raid import RaidReport, RaidReportException, Adapter, PhysicalDrive, LogicalDrive

log = logging.getLogger(__file__)

PROP_RE = re.compile(r'(.*?)\s*:\s*(.+)')


def examine_physical_drive(device_path, mdadm, timeout):
    cmd = ['timeout', str(timeout), mdadm, '--examine', device_path]
    log.debug("Examining physical drive '%s'" % (' '.join(cmd),))

    out = None

    with TemporaryFile() as tmp:
        ret = subprocess.call(cmd, stdout=tmp, stderr=tmp)

        if ret != 124:  # Not Timeout
            tmp.seek(0)
            out = tmp.read()
        else:
            log.warning("mdadm timeout for %s", device_path)

    if ret != 0:
        return device_path, {}

    drive = {}
    for line in out.decode().splitlines():
        m = PROP_RE.match(line.strip())
        if m:
            # noinspection PyTypeChecker
            drive.update([m.groups()])  # our regex has exactly 2 groups, ignore warning

    return device_path, drive


class MdReport(RaidReport):
    raid_manager = 'md'
    executables = ['mdadm']
    arrays = []

    def __init__(self, timeout=10, concurrency=4):
        """
        :param int|str timeout: mdadm timeout in seconds
        :param int|str concurrency: Thread pool size for concurrent checking
        """
        super(MdReport, self).__init__()

        self.timeout = int(timeout)
        self.concurrency = int(concurrency)

        self._check_array_list()

    def _check_array_list(self):
        p = subprocess.Popen([self.executable, '--detail', '--scan'], stdout=subprocess.PIPE)
        out, _ = p.communicate()

        if p.returncode != 0:
            raise RaidReportException("mdadm could not get list of arrays")

        if not out:
            raise RaidReportException("mdadm is not managing any arrays")

        for line in out.decode().splitlines():
            self.arrays.append(line.split()[1])  # second item is device

    def parse_adapters(self):
        # No physical adapters present, just the software RAID
        self.adapters.append(Adapter(
            'Linux RAID',
            'Linux RAID',
            '',
            '',
        ))

        return self.adapters

    def parse_physical_drives(self):
        # Find OS drive first, so we can exclude it from the list
        os_drives = []
        with open('/etc/mtab') as mtab:
            for line in mtab:
                if line.startswith('/dev/sd'):
                    partition = line.split()[0]
                    os_drives.append(re.sub(r'[0-9]', '', partition))

        log.info("Ignoring drives with OS partitions on them: %s" % (', '.join(os_drives),))

        cmd = ['lsblk', '--ascii', '--nodeps', '--noheadings', '--raw', '--output', 'NAME,MAJ:MIN,MODEL,SIZE,STATE']
        log.debug("Listing physical drives: '%s'" % (' '.join(cmd), ))

        p = subprocess.Popen(cmd, stdout=subprocess.PIPE)
        out, _ = p.communicate()

        if p.returncode != 0:
            raise RaidReportException("Error running lsblk")

        devices = {}

        for line in out.decode('ascii').splitlines():
            # noinspection PyTypeChecker
            line = re.sub(r'\\x[0-9]{2}', '_', line)  # Replace all \\x## with underscore
            drive_id, device_number, model, size, state = line.split()

            device_path = '/dev/' + drive_id

            if device_path in os_drives:
                continue

            status = PhysicalDrive.STATUS_GOOD
            if state != 'running':
                status = PhysicalDrive.STATUS_FAILED

            if os.path.exists(device_path + '1'):
                # We're using partitions in mdadm
                device_path += '1'

            devices[device_path] = drive_id

            pdrive = PhysicalDrive(
                drive_id,
                state,
                size,
                device_number,
                model,
                '',  # fru
                '',  # temperature
                status,
                'Linux RAID',
                device_number,
                False  # hotspare
            )

            self.phy_drives[drive_id] = pdrive

        log.debug("Creating mdadm check thread pool of size %s", self.concurrency)
        pool = get_pool()(processes=self.concurrency)
        res = pool.map(partial(examine_physical_drive, mdadm=self.executable, timeout=self.timeout), devices.keys())
        for device_path, device_out in res:
            pdrive = self.phy_drives[devices[device_path]]  # Map path back to PhysicalDrive

            if device_out:
                pdrive.hotspare = device_out.get('Device Role') == 'spare'
                pdrive.data = device_out
            else:  # mdadm timeout occurred
                pdrive.status = PhysicalDrive.STATUS_FAILING

        pool.close()

        return self.phy_drives

    def parse_logical_drives(self):
        pdrives_by_array_uuid = defaultdict(list)
        for drive_id, drive in self.phy_drives.items():
            if not drive.hotspare and 'Array UUID' in drive.data:
                pdrives_by_array_uuid[drive.data['Array UUID']].append(drive_id)

        for arr in self.arrays:
            cmd = [self.executable, '--detail', arr]
            log.debug("Logical drive %s details: '%s'" % (arr, ' '.join(cmd), ))

            p = subprocess.Popen(cmd, stdout=subprocess.PIPE)
            out, _ = p.communicate()

            if p.returncode != 0:
                raise RaidReportException("mdadm could not get array details")

            drive = {}
            for line in out.decode().splitlines():
                m = PROP_RE.match(line.strip())
                if m:
                    # noinspection PyTypeChecker
                    drive.update([m.groups()])  # our regex has exactly 2 groups, ignore warning

            size = 0
            if 'Array Size' in drive:  # Failed arrays don't report size
                size = int(drive['Array Size'].split('(')[0].strip())

            self.log_drives.append(LogicalDrive(
                arr,
                drive['Raid Level'].upper(),
                '%.1fTB' % (size / 1024 ** 3,),
                drive['State'],
                'Linux RAID',
                pdrives_by_array_uuid.get(drive['UUID'], []),
                'FAILED' in drive['State']
            ))

        return self.log_drives


report = MdReport


def main():
    log.setLevel(logging.DEBUG)
    logging.basicConfig(level=log.level)

    # noinspection PyCompatibility
    import argparse
    parser = argparse.ArgumentParser(description='Analyze md raid')
    _ = parser.parse_args()

    omreport = MdReport()
    omreport.collect_all_data()
    omreport.stdout()


if __name__ == '__main__':
    main()
