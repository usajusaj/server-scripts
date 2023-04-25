import os
import re
import subprocess
from collections import defaultdict

from ccbr_server.raid import RaidReport, RaidReportException, Adapter, PhysicalDrive, LogicalDrive

DRIVE_RE = re.compile(r'Drive /c(\d+)/e(\d+)/s(\d+)')
VD_RE = re.compile(r'/c(\d+)/v(\d+)')


class StorCliReport(RaidReport):
    raid_manager = 'storcli'
    executables = ['storcli', 'storcli64']

    def parse_adapters(self):
        import json

        p = subprocess.Popen([self.executable, '/call', 'show',  'all', 'j', 'nolog'], stdout=subprocess.PIPE)
        out, _ = p.communicate()

        if p.returncode != 0:
            raise RaidReportException("StorCli could not get adapter info")

        cliout = json.loads(out.decode())

        for controller in cliout.get('Controllers', []):
            ctrl_data = controller.get('Response Data', {})
            self.adapters.append(Adapter(
                str(ctrl_data.get('Basics', {}).get('Controller')),
                ctrl_data.get('Basics', {}).get('Model'),
                ctrl_data.get('Basics', {}).get('Serial Number'),
                ctrl_data.get('HwCfg', {}).get('ROC temperature(Degree Celsius)'),
                data=ctrl_data
            ))

        return self.adapters

    def parse_physical_drives(self):
        """ EID=Enclosure Device ID
            Slt=Slot No
            DID=Device ID
            ---STATE
                Onln=Online
                Offln=Offline
            DG=DriveGroup
            ---SIZE
            Intf=Interface
            Med=Media Type
            SED=Self Encryptive Drive
            PI=Protection Info
            SeSz=Sector Size
            --MODEL
            Sp=Spun
                U=Up
                D=Down

            DHS=Dedicated Hot Spare
            UGood=Unconfigured Good
            GHS=Global Hotspare
            UBad=Unconfigured Bad
            Sntze=Sanitize
            T=Transition
            F=Foreign
            UGUnsp=UGood Unsupported
            UGShld=UGood shielded
            HSPShld=Hotspare shielded
            CFShld=Configured shielded
            Cpybck=CopyBack
            CBShld=Copyback Shielded
            UBUnsp=UBad Unsupported
            Rbld=Rebuild
        """

        import json

        p = subprocess.Popen([self.executable, '/call/eall/sall', 'show', 'all', 'j', 'nolog'], stdout=subprocess.PIPE)
        out, _ = p.communicate()

        if p.returncode != 0:
            raise RaidReportException("StorCli could not get physical drives info")

        cliout = json.loads(out.decode())

        drives = defaultdict(dict)

        for controller in cliout.get('Controllers', []):
            data = controller.get('Response Data', {})

            for k, v in data.items():
                if k.endswith('Detailed Information'):
                    driveid = k.split('-')[0].strip()
                    for dk, dv in v.items():
                        drives[driveid][dk.replace(driveid, '').strip()] = dv
                else:
                    v[0]['Controller'] = str(controller['Command Status']['Controller'])
                    drives[k]['Basic'] = v[0]

        for drive_id, drive in drives.items():
            controller, enclosure, slot = DRIVE_RE.match(drive_id).groups()

            state = PhysicalDrive.STATUS_GOOD
            ds = drive['State']

            if drive['Basic']['State'] != 'Onln':
                state = PhysicalDrive.STATUS_FAILED
            elif ds['Media Error Count'] != 0 or ds['Other Error Count'] != 0 or ds['Predictive Failure Count'] != 0:
                state = PhysicalDrive.STATUS_FAILING

            pdrive = PhysicalDrive(
                str(drive['Basic']['DID']),
                drive['Basic']['State'],
                drive['Basic']['Size'],
                drive['Basic']['Intf'],
                drive['Basic']['Model'],
                drive['Device attributes']['FRU/CRU'].strip(),
                drive['State']['Drive Temperature'].strip().split(' ')[0],  # No fahrenheit
                state,
                drive['Basic']['Controller'],
                slot,
                drive['Policies/Settings']['Commissioned Spare'] != 'No'
            )
            self.phy_drives[drive['Basic']['EID:Slt']] = pdrive

        return self.phy_drives

    def parse_logical_drives(self):
        import json

        p = subprocess.Popen([self.executable, '/call/vall', 'show', 'all', 'j', 'nolog'], stdout=subprocess.PIPE)
        out, _ = p.communicate()

        if p.returncode != 0:
            raise RaidReportException("StorCli could not get logical drives info")

        cliout = json.loads(out.decode())

        vds = defaultdict(dict)

        for controller in cliout['Controllers']:
            for k, v in controller['Response Data'].items():
                if k.startswith('PDs for'):
                    vds[k.split(' ')[-1]]['drive_list'] = v
                elif k.endswith('Properties'):
                    vd = k.split(' ')[0].replace('VD', '')
                    vds[vd]['Properties'] = v
                else:
                    ctrl, vd = VD_RE.match(k).groups()
                    v = v[0]
                    v['Controller'] = ctrl
                    vds[vd]['Basic'] = v

        for vdid, vd in vds.items():
            self.log_drives.append(LogicalDrive(
                    vdid,
                    vd['Basic']['TYPE'],
                    vd['Basic']['Size'],
                    vd['Basic']['State'],
                    vd['Basic']['Controller'],
                    [d['EID:Slt'] for d in vd['drive_list']],
                    vd['Basic']['State'] != 'Optl'
                ))

        return self.log_drives


report = StorCliReport


def main():
    if os.getuid() != 0:
        print("This script must be run by root!")
        exit(1)

    # noinspection PyCompatibility
    import argparse
    parser = argparse.ArgumentParser(description='Analyze storcli output')
    _ = parser.parse_args()

    storcli = StorCliReport()
    storcli.collect_all_data()
    storcli.stdout()


if __name__ == '__main__':
    main()
