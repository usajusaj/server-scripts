import os
import re
import subprocess

from ccbr_server.raid import RaidReport, RaidReportException, Adapter, PhysicalDrive, LogicalDrive

PROP_RE = re.compile(r'(.*?)\s*:\s*(.+)')


class OmreportReport(RaidReport):
    raid_manager = 'omreport'
    executables = ['omreport']

    def parse_adapters(self):
        p = subprocess.Popen([self.executable, 'storage', 'controller'], stdout=subprocess.PIPE)
        out, _ = p.communicate()

        if p.returncode != 0:
            raise RaidReportException("omreport could not get adapter info")

        adapters = []
        adapter = {}

        for line in out.splitlines():
            line = line.rstrip()

            if line.startswith('Controller'):  # Begin parsing new adapter
                adapter = {}
                adapters.append(adapter)
            else:  # We are in adapter block, parse the line
                m = PROP_RE.match(line)
                if m:
                    # noinspection PyTypeChecker
                    adapter.update([m.groups()])  # our regex has exactly 2 groups, ignore warning

        # Convert parsed data to a standard model
        for adapter in sorted(adapters, key=lambda a: a['ID']):
            self.adapters.append(Adapter(
                adapter['ID'],
                adapter['Name'],
                '',
                '',
                adapter
            ))

        return self.adapters

    def __parse_drives(self, drive_type, adapter):
        p = subprocess.Popen([self.executable, 'storage', drive_type, 'controller=%s' % adapter],
                             stdout=subprocess.PIPE)
        out, _ = p.communicate()

        if p.returncode != 0:
            raise RaidReportException("omreport could not get %s info for adapter %s" % (drive_type, adapter))

        drives = []
        drive = {}

        for line in out.splitlines():
            line = line.rstrip()

            if line.startswith('ID'):  # Begin parsing new drive
                drive = {'adapter_id': adapter}
                drives.append(drive)

            m = PROP_RE.match(line)
            if m:
                # noinspection PyTypeChecker
                drive.update([m.groups()])  # our regex has exactly 2 groups, ignore warning

        return drives

    def parse_physical_drives(self):
        if not self.adapters:
            raise RaidReportException("omreport can't get physical drive info w/o controller info")

        drives = []

        for adapter in self.adapters:
            drives.extend(self.__parse_drives('pdisk', adapter.data['ID']))

        for drive in drives:
            drive['logical_drive_id'] = drive['ID'].split(':')[1]

            status = PhysicalDrive.STATUS_GOOD
            if drive['Status'] == 'Critical':
                status = PhysicalDrive.STATUS_FAILED

            pdrive = PhysicalDrive(
                drive['ID'],
                drive['Status'],
                drive['Capacity'].split('(')[0].strip(),
                drive['Bus Protocol'],
                drive['Product ID'],
                '',  # fru
                '',  # temperature
                status,
                drive['adapter_id'],
                drive['ID'],
                drive['Hot Spare'] != 'No',
                drive
            )

            self.phy_drives[drive['adapter_id'] + pdrive.drive_id] = pdrive

        return self.phy_drives

    def parse_logical_drives(self):
        if not self.adapters:
            raise RaidReportException("omreport can't get logical drive info w/o controller info")

        drives = []

        for adapter in self.adapters:
            drives.extend(self.__parse_drives('vdisk', adapter.data['ID']))

        for drive in drives:
            p = subprocess.Popen(
                [self.executable, 'storage', 'pdisk', 'controller=%s' % drive['adapter_id'], 'vdisk=%s' % drive['ID']],
                stdout=subprocess.PIPE)
            out, _ = p.communicate()

            if p.returncode != 0:
                raise RaidReportException("omreport could not get logical drive info")

            pdrives = []

            for line in out.splitlines():
                line = line.rstrip()

                if line.startswith('ID'):
                    m = PROP_RE.match(line)
                    physical_drive_id = m.group(2)
                    pdrives.append(drive['adapter_id'] + physical_drive_id)

            self.log_drives.append(LogicalDrive(
                drive['ID'],
                drive['Layout'],
                drive['Size'].split('(')[0].strip(),
                '%s (%s)' % (drive['Status'], drive['State']),
                drive['adapter_id'],
                pdrives,
                drive['Status'] != 'Ok'
            ))

        return self.log_drives


report = OmreportReport


def main():
    if os.getuid() != 0:
        print("This script must be run by root!")
        exit(1)

    # noinspection PyCompatibility
    import argparse
    parser = argparse.ArgumentParser(description='Analyze omreport output')
    _ = parser.parse_args()

    omreport = OmreportReport()
    omreport.collect_all_data()
    omreport.stdout()


if __name__ == '__main__':
    main()
