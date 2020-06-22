# noinspection PyUnresolvedReferences
from distutils.spawn import find_executable


def format_msg(msg, color=None):
    """ Wrap msg in bash escape characters

    :param str msg: Message
    :param color: red, orange, error or warn
    :return: Escaped message
    """
    if color in ('red', 'error'):
        esc_char = '41'
    elif color in ('orange', 'warn'):
        esc_char = '43'
    else:
        esc_char = '42'

    return '\033[%sm%s\033[0m' % (esc_char, msg)


class RaidCliException(Exception):
    pass


class RaidCli:
    """ Standardized interface to all RAID cli's
    :type executables: list[str]
    :type adapters: list[Adapter]
    :type phy_drives: dict[int, PhysicalDrive]
    :type log_drives: list[LogicalDrive]
    """
    executables = []

    adapters = []
    phy_drives = {}
    log_drives = []

    def __init__(self):
        self.executable = self.find_cli_path()

    def find_cli_path(self):
        """ Search for the executable for this raid CLI. Subclass must provide list of possible command names in
         self.executables

        :return: Path to the first executable found
        :rtype: str
        :raises: RaidCliException if an executable could not be found
        """
        for exe in self.executables:
            path = find_executable(exe)
            if path:
                return path
        raise RaidCliException("Could not find executable on PATH")

    def collect_all_data(self, connect=True):
        """ Collect all possible information about RAID

        :param bool connect: Connect collected data
        """
        self.parse_adapters()
        self.parse_physical_drives()
        self.parse_logical_drives()

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
        :raises: RaidCliException if there was a problem with cli tool
        """
        raise NotImplementedError()

    def parse_physical_drives(self):
        """ Query RAID system to get a list of physical drives

        :return: Physical drives present on this system
        :rtype: dict[str, dict[str, str]]
        :raises: RaidCliException if there was a problem with cli tool
        """
        raise NotImplementedError()

    def parse_logical_drives(self):
        """ Query RAID system to get a list of logical drives

        :return: Logical drives present on this system
        :rtype: list[dict[str, str]]
        :raises: RaidCliException if there was a problem with cli tool
        """
        raise NotImplementedError()


class Adapter:
    """ Standardized Adapter model

    :type logical_drives: list[LogicalDrive]
    :type physical_drives: list[PhysicalDrive]
    :type spare_physical_drives: list[PhysicalDrive]
    """
    logical_drives = None
    physical_drives = None
    spare_physical_drives = None

    def __init__(self, adapter_id, name, serial, temperature):
        """
        :param str adapter_id: Numerical ID of this adapter
        :param str name: Adapter name, usually make/model
        :param str serial: Adapter's serial number
        :param str temperature: Temperature of ROC (raid-on-chip)
        """
        self.adapter_id = int(adapter_id)
        self.name = name
        self.serial = serial
        self.temperature = int(temperature)

    def __str__(self):
        return "Adapter {adapter_id}: {name} | {temperature}C".format(**vars(self))


class LogicalDrive:
    """ Standardized logical drive model

    :type adapter: Adapter
    :type physical_drives: list[PhysicalDrive]
    """
    adapter = None
    physical_drives = None

    def __init__(self, drive_id, raid_level, size, state, adapter_id, pd_list):
        """
        :param str drive_id: Numerical ID of this logical drive
        :param str raid_level: RAID level
        :param str size: Size
        :param str state: State
        :param str adapter_id: Adapter ID
        :param list[str] pd_list: List of physical drive ids
        """
        self.drive_id = int(drive_id)
        self.raid_level = raid_level
        self.size = size
        self.state = state
        self.adapter_id = int(adapter_id)
        self.phy_drive_ids = [int(d) for d in pd_list]

    def __str__(self):
        state = format_msg(self.state, self.state != 'Optimal' and 'red')
        return "Logical drive {drive_id}: {raid_level}, {size}, {st}".format(st=state, **vars(self))


class PhysicalDrive:
    """ Standardized physical drive model

    :type adapter: Adapter
    :type logical_drive: LogicalDrive
    """
    adapter = None
    logical_drive = None

    def __init__(self, drive_id, state, size, protocol, drive_type, fru, temperature, pred_fail, adapter_id, slot,
                 hotspare):
        """
        :param str drive_id:
        :param str state:
        :param str size:
        :param str protocol:
        :param str drive_type:
        :param str fru:
        :param str temperature:
        :param bool pred_fail:
        :param str adapter_id:
        :param str slot:
        :param bool hotspare:
        """
        self.drive_id = int(drive_id)
        self.state = state
        self.size = size
        self.protocol = protocol
        self.drive_type = drive_type
        self.fru = fru
        self.temperature = temperature
        self.predictive_fail = pred_fail
        self.adapter_id = int(adapter_id)
        self.slot = int(slot)
        self.hotspare = hotspare

    def __str__(self):
        predictive_fail = ''
        if self.predictive_fail:
            predictive_fail = format_msg('Predictive fail', 'orange')

        return "Drive {drive_id:>2}: {state}; {size} {protocol} {drive_type}; {temperature}; {will_fail}".format(
            will_fail=predictive_fail,
            **vars(self))
