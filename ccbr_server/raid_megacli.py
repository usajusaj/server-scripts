import os
import re
import subprocess

from ccbr_server.raid import RaidReport, RaidReportException, Adapter, PhysicalDrive, LogicalDrive

PROP_RE = re.compile(r'(.*?)\s*:\s*(.+)')
RAID_LEVEL_MAP = {
    'Primary-1, Secondary-0, RAID Level Qualifier-0': 'RAID1',
    'Primary-5, Secondary-0, RAID Level Qualifier-3': 'RAID5'
}


class MegaCliReport(RaidReport):
    raid_manager = 'megacli'
    executables = ['megacli', 'MegaCli', 'MegaCli64']

    def parse_adapters(self):
        p = subprocess.Popen([self.executable, 'adpallinfo', 'aall', 'nolog'], stdout=subprocess.PIPE)
        out, _ = p.communicate()

        if p.returncode != 0:
            raise RaidReportException("MegaCli could not get adapter info")

        adapters = []
        adapter = {}

        for line in out.decode().splitlines():
            line = line.rstrip()

            if line.startswith('Adapter #'):  # Begin parsing new adapter
                adapter_id = line.replace('Adapter #', '')
                adapter = {'id': adapter_id}
                adapters.append(adapter)
            elif adapter:  # We are in adapter block, parse the line
                m = PROP_RE.match(line)
                if m:
                    # noinspection PyTypeChecker
                    adapter.update([m.groups()])  # our regex has exactly 2 groups, ignore warning

        # Convert parsed data to a standard model
        for adapter in sorted(adapters, key=lambda a: a['id']):
            self.adapters.append(Adapter(
                adapter['id'],
                adapter['Product Name'],
                adapter['Serial No'],
                'ROC temperature' in adapter and adapter['ROC temperature'].split()[0]
            ))

        return self.adapters

    def parse_physical_drives(self):
        p = subprocess.Popen([self.executable, 'pdlist', 'aall', 'nolog'], stdout=subprocess.PIPE)
        out, _ = p.communicate()

        if p.returncode != 0:
            raise RaidReportException("MegaCli could not get physical drives info")

        adapter = None
        drives = []
        drive = {}
        blank_count = 0

        for line in out.decode().splitlines():
            line = line.rstrip()

            if not line:
                blank_count += 1
            else:
                blank_count = 0

            if blank_count == 3 and drive:
                drives.append(drive)
                # self.phy_drives[drive['Device Id']] = drive
                drive = {}

            if line.startswith('Adapter #'):  # Begin parsing new adapter
                adapter = line.replace('Adapter #', '')

            if adapter is not None:  # Ignore anything before adapter is defined
                drive['adapter_id'] = adapter  # can't be bothered to have an if or this line duplicated somewhere

                m = PROP_RE.match(line)
                if m:
                    # noinspection PyTypeChecker
                    drive.update([m.groups()])  # our regex has exactly 2 groups, ignore warning
                elif line.startswith('Hotspare Information:'):
                    drive['hotspare'] = True

        for drive in drives:
            status = PhysicalDrive.STATUS_GOOD
            if drive['Predictive Failure Count'] != '0':
                status = PhysicalDrive.STATUS_FAILING
            if 'bad' in drive['Firmware state']:
                status = PhysicalDrive.STATUS_FAILED

            pdrive = PhysicalDrive(
                drive['Device Id'],
                drive['Firmware state'],
                drive['Raw Size'].split('[')[0].strip(),
                drive['PD Type'],
                ' '.join(drive['Inquiry Data'].split()),
                drive.get('IBM FRU/CRU', ''),
                drive['Drive Temperature'].split()[0],
                status,
                drive['adapter_id'],
                drive['Slot Number'],
                drive.get('hotspare', False)
            )
            self.phy_drives[pdrive.drive_id] = pdrive

        return self.phy_drives

    def parse_logical_drives(self):
        p = subprocess.Popen([self.executable, 'ldpdinfo', 'aall', 'nolog'], stdout=subprocess.PIPE)
        out, _ = p.communicate()

        if p.returncode != 0:
            raise RaidReportException("MegaCli could not get logical drives info")

        re_adp = re.compile(r'Adapter #(\d+)')
        re_vdr = re.compile(r'Virtual Drive: (\d+)')

        adapter_id = None
        drive_id = None
        parse_opts = False

        drives = []
        drive = {}

        for line in out.decode().splitlines():
            line = line.rstrip()

            if line.startswith('Adapter #'):  # Begin parsing new adapter
                adapter_id = re_adp.match(line).group(1)
            elif line.startswith('Virtual Drive: '):
                drive_id = re_vdr.match(line).group(1)
                drive = {'id': drive_id, 'adapter_id': adapter_id, 'physical_drives': []}
                drives.append(drive)
                parse_opts = True
            elif line.startswith('PD:'):
                parse_opts = False

            if adapter_id and drive_id:
                if parse_opts:  # get logical drive options
                    m = PROP_RE.match(line)
                    if m:
                        # noinspection PyTypeChecker
                        drive.update([m.groups()])  # our regex has exactly 2 groups, ignore warning
                elif line.startswith('Device Id:'):  # get physical drive id
                    drive['physical_drives'].append(PROP_RE.match(line).group(2))

        for drive in drives:
            self.log_drives.append(LogicalDrive(
                drive['id'],
                RAID_LEVEL_MAP.get(drive['RAID Level'], '?'),
                drive['Size'],
                drive['State'],
                drive['adapter_id'],
                drive['physical_drives'],
                drive['State'] != 'Optimal'
            ))

        return self.log_drives


report = MegaCliReport


def main():
    if os.getuid() != 0:
        print("This script must be run by root!")
        exit(1)

    # noinspection PyCompatibility
    import argparse
    parser = argparse.ArgumentParser(description='Analyze MegaCli output')
    _ = parser.parse_args()

    megacli = MegaCliReport()
    megacli.collect_all_data()
    megacli.stdout()


if __name__ == '__main__':
    main()
