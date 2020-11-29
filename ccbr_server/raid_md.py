import subprocess
import re
from collections import defaultdict

from ccbr_server.raid import RaidReport, RaidReportException, Adapter, PhysicalDrive, LogicalDrive

PROP_RE = re.compile(r'(.*?)\s*:\s*(.+)')


class MdReport(RaidReport):
    raid_manager = 'md'
    executables = ['mdadm']
    arrays = []

    def __init__(self):
        super(MdReport, self).__init__()

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

    # noinspection PyMethodMayBeStatic
    def _examine_physical_drive(self, drive_name):
        p = subprocess.Popen(
            ['mdadm', '--examine', '/dev/%s1' % drive_name],  # We partition drive and use first partition for md
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT)
        out, _ = p.communicate()

        if p.returncode != 0:
            return {}

        drive = {}
        for line in out.decode().splitlines():
            m = PROP_RE.match(line.strip())
            if m:
                # noinspection PyTypeChecker
                drive.update([m.groups()])  # our regex has exactly 2 groups, ignore warning

        return drive

    def parse_physical_drives(self):
        # Find OS drive first, so we can exclude it from the list
        os_drives = []
        with open('/etc/mtab') as mtab:
            for line in mtab:
                if line.startswith('/dev/sd'):
                    partition = line.split()[0]
                    os_drives.append(re.sub(r'[0-9]', '', partition))

        p = subprocess.Popen(
            ['lsblk', '--ascii', '--nodeps', '--noheadings', '--raw', '--output', 'NAME,MAJ:MIN,MODEL,SIZE,STATE'],
            stdout=subprocess.PIPE)
        out, _ = p.communicate()

        if p.returncode != 0:
            raise RaidReportException("Error running lsblk")

        for line in out.decode('ascii').splitlines():
            line = re.sub(r'\\x[0-9]{2}', '_', line)  # Replace all \\x## with underscore
            drive_id, device_number, model, size, state = line.split()

            device_path = '/dev/' + drive_id

            if device_path in os_drives:
                continue

            status = PhysicalDrive.STATUS_GOOD
            if state != 'running':
                status = PhysicalDrive.STATUS_FAILED

            drive = self._examine_physical_drive(drive_id)

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
                drive.get('Device Role') == 'spare',
                drive
            )

            self.phy_drives[drive_id] = pdrive

        return self.phy_drives

    def parse_logical_drives(self):
        pdrives_by_array_uuid = defaultdict(list)
        for drive_id, drive in self.phy_drives.items():
            if not drive.hotspare and 'Array UUID' in drive.data:
                pdrives_by_array_uuid[drive.data['Array UUID']].append(drive_id)

        for arr in self.arrays:
            p = subprocess.Popen([self.executable, '--detail', arr], stdout=subprocess.PIPE)
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
                '%.1fTB' % (size / 1024**3, ),
                drive['State'],
                'Linux RAID',
                pdrives_by_array_uuid.get(drive['UUID'], []),
                'FAILED' in drive['State']
            ))

        return self.log_drives


report = MdReport


def main():
    # noinspection PyCompatibility
    import argparse
    parser = argparse.ArgumentParser(description='Analyze md raid')
    _ = parser.parse_args()

    omreport = MdReport()
    omreport.collect_all_data()
    omreport.stdout()


if __name__ == '__main__':
    main()
