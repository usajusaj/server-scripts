import logging
import os

# noinspection PyUnresolvedReferences
from distutils.spawn import find_executable

from ccbr_server.common import Report, format_msg, ReportException

log = logging.getLogger(__file__)


class RaidReportException(ReportException):
    pass


class RaidReport(Report):
    """ Standardized interface to all RAID cli's
    :type executables: list[str]
    :type adapters: list[Adapter]
    :type phy_drives: dict[str, PhysicalDrive]
    :type log_drives: list[LogicalDrive]
    """
    name = 'raid'
    raid_manager = ''
    executables = []

    adapters = []
    phy_drives = {}
    log_drives = []

    def __init__(self):
        self.executable = self.find_cli_path()

    def collect_data(self):
        self.collect_all_data()
        return self

    # noinspection PyTypeChecker
    def to_dict(self):
        raid = []

        for adapter in self.adapters:
            d_adapter = adapter.to_dict()
            d_adapter['logical_drives'] = [d.to_dict() for d in adapter.logical_drives]
            d_adapter['physical_drives'] = [d.to_dict() for d in adapter.physical_drives]

            raid.append(d_adapter)

        return {
            'ver': 1,
            'adapters': raid,
            'manager': self.raid_manager,
        }

    def find_cli_path(self):
        """ Search for the executable for this raid CLI. Subclass must provide list of possible command names in
         self.executables

        :return: Path to the first executable found
        :rtype: str
        :raises: RaidReportException if an executable could not be found
        """
        for exe in self.executables:
            path = find_executable(exe)
            if path:
                return path
        raise RaidReportException("Could not find executable on PATH: %s" % ','.join(self.executables))

    def collect_all_data(self, connect=True):
        """ Collect all possible information about RAID

        :param bool connect: Connect collected data
        """
        self.parse_adapters()
        self.parse_physical_drives()
        self.parse_logical_drives()

        self.post_process()

        if connect:
            self.connect_data()

    def connect_data(self):
        """ Replace id's of collected data with object references
        """
        adapter_map = {}
        for adapter in self.adapters:
            adapter.physical_drives = []
            adapter.logical_drives = []
            adapter_map[adapter.adapter_id] = adapter

        for drive in self.log_drives:
            drive.adapter = adapter_map[drive.adapter_id]
            drive.physical_drives = [self.phy_drives[d] for d in drive.phy_drive_ids]
            for pdrive in drive.physical_drives:
                pdrive.logical_drive = drive

            drive.adapter.logical_drives.append(drive)

        for drive in self.phy_drives.values():
            drive.adapter = adapter_map[drive.adapter_id]
            drive.adapter.physical_drives.append(drive)

        for adapter in self.adapters:
            adapter.spare_physical_drives = [d for d in adapter.physical_drives if not d.logical_drive]

    def parse_adapters(self):
        """ Query RAID system to get controller info

        :return: Adapters present on this system
        :rtype: dict[str, dict[str, str]]
        :raises: RaidReportException if there was a problem with cli tool
        """
        raise NotImplementedError()

    def parse_physical_drives(self):
        """ Query RAID system to get a list of physical drives

        :return: Physical drives present on this system
        :rtype: dict[str, dict[str, str]]
        :raises: RaidReportException if there was a problem with cli tool
        """
        raise NotImplementedError()

    def parse_logical_drives(self):
        """ Query RAID system to get a list of logical drives

        :return: Logical drives present on this system
        :rtype: list[dict[str, str]]
        :raises: RaidReportException if there was a problem with cli tool
        """
        raise NotImplementedError()

    def post_process(self):
        """ Any post processing code that before we start linking models
        """

    @staticmethod
    def automatic_cli():
        """ Automatically detect the RAID manager on this system

        :return: Supported RAID report instance
        :rtype: RaidReport
        """
        for f in os.listdir(os.path.dirname(__file__)):
            log.info("Considering %s", f)
            if not (f.startswith('raid_') and f.endswith('.py')):
                continue

            module_name, _py = os.path.splitext(f)
            try:
                module = __import__(module_name)
            except ImportError:
                # Should not happen
                log.debug("Import failed for %s", f)
                continue

            try:
                report = module.report()
                log.info("Found supported RAID manager: %s", module.report.__name__)
                return report
            except AttributeError:
                # There is no report = ReportClass in the module
                log.debug("Not a valid RAID manager: %s", module.report.__name__)
            except RaidReportException:
                # Current report is not supported on this system
                log.debug("Unsupported RAID manager: %s", module.report.__name__)

        raise RaidReportException("No supported RAID managers found.")

    def stdout(self):
        for adapter in self.adapters:
            print(adapter)

            for ldrive in adapter.logical_drives:
                print('\t%s' % ldrive)

                for pdrive in ldrive.physical_drives:
                    print('\t\t%s' % pdrive)

            if adapter.spare_physical_drives:
                print('\tSpare drives:')

                for pdrive in adapter.spare_physical_drives:
                    print('\t\t%s' % pdrive)


class Adapter:
    """ Standardized Adapter model

    :type logical_drives: list[LogicalDrive]
    :type physical_drives: list[PhysicalDrive]
    :type spare_physical_drives: list[PhysicalDrive]
    :type data: dict[str, str]
    """
    logical_drives = None
    physical_drives = None
    spare_physical_drives = None

    data = {}

    def __init__(self, adapter_id, name, serial, temperature, data=None):
        """
        :param str adapter_id: Numerical ID of this adapter
        :param str name: Adapter name, usually make/model
        :param str serial: Adapter's serial number
        :param str temperature: Temperature of ROC (raid-on-chip)
        :param dict[str, str] data: raw values read from raid management
        """
        self.adapter_id = adapter_id
        self.name = name
        self.serial = serial
        self.temperature = int(temperature) if temperature else None

        if data:
            self.data = data

    def __str__(self):
        string_fmt = ['Adapter {adapter_id}: {name}']
        if self.temperature:
            string_fmt.append('{temperature}C')

        string_fmt = ' | '.join(string_fmt)
        return string_fmt.format(**vars(self))

    def to_dict(self):
        return {
            'id': self.adapter_id,
            'name': self.name,
            'serial': self.serial,
            'temperature': self.temperature
        }


class LogicalDrive:
    """ Standardized logical drive model

    :type adapter: Adapter
    :type physical_drives: list[PhysicalDrive]
    :type data: dict[str, str]
    """
    adapter = None
    physical_drives = None

    data = {}

    def __init__(self, drive_id, raid_level, size, state, adapter_id, pd_list, problem, data=None):
        """
        :param str drive_id: Numerical ID of this logical drive
        :param str raid_level: RAID level
        :param str size: Size
        :param str state: State
        :param str adapter_id: Adapter ID
        :param list[str] pd_list: List of physical drive ids
        """
        self.drive_id = drive_id
        self.raid_level = raid_level
        self.size = size
        self.state = state
        self.adapter_id = adapter_id
        self.phy_drive_ids = [d for d in pd_list]
        self.problem = problem

        if data:
            self.data = data

    def __str__(self):
        state = format_msg(self.state, self.problem and 'red')
        return "Logical drive {drive_id}: {raid_level}, {size}, {st}".format(st=state, **vars(self))

    def to_dict(self):
        return {
            'id': self.drive_id,
            'level': self.raid_level,
            'size': self.size,
            'state': self.state
        }


class PhysicalDrive:
    """ Standardized physical drive model

    :type adapter: Adapter
    :type logical_drive: LogicalDrive
    :type data: dict[str, str]
    """
    STATUS_GOOD = 0
    STATUS_FAILING = 1
    STATUS_FAILED = 2

    adapter = None
    logical_drive = None

    data = {}

    def __init__(self, drive_id, state, size, protocol, drive_type, fru, temperature, status, adapter_id, slot,
                 hotspare, data=None):
        """
        :param str drive_id:
        :param str state:
        :param str size:
        :param str protocol:
        :param str drive_type:
        :param str fru:
        :param str temperature:
        :param bool status:
        :param str adapter_id:
        :param str slot:
        :param bool hotspare:
        """
        self.drive_id = drive_id
        self.state = state
        self.size = size
        self.protocol = protocol
        self.drive_type = drive_type
        self.fru = fru
        self.temperature = temperature
        self.status = status
        self.adapter_id = adapter_id
        self.slot = slot
        self.hotspare = hotspare

        if data:
            self.data = data

    def __str__(self):
        if self.status == PhysicalDrive.STATUS_GOOD:
            status = format_msg(self.state, 'green')
        elif self.status == PhysicalDrive.STATUS_FAILING:
            status = format_msg(self.state, 'orange')
        elif self.status == PhysicalDrive.STATUS_FAILED:
            status = format_msg(self.state, 'red')
        else:
            status = format_msg(self.state, 'red')

        return "Drive {drive_id:>2}: {size} {protocol} {drive_type}; {temperature}; {will_fail}".format(
            will_fail=status,
            **vars(self))

    def to_dict(self):
        return {
            'id': self.drive_id,
            'state': self.state,
            'size': self.size,
            'protocol': self.protocol,
            'type': self.drive_type,
            'temperature': self.temperature,
            'status': self.status,
            'slot': self.slot,
            'hotspare': self.hotspare,
            'logical_drive': self.logical_drive.drive_id if self.logical_drive else None
        }
