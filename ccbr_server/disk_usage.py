import os

from ccbr_server.common import Report


class UsageReport(Report):
    """ Report for disk usage

    :type usages: list[Usage]
    """
    name = 'disk_usage'
    usages = []

    def collect_data(self):
        with open('/etc/mtab') as fio:
            mtab = fio.read()

        mtab = mtab.splitlines()

        for mline in mtab:
            dev, mount_point, fs_type, opts = mline.split()[:4]

            if not dev.startswith('/'):  # Use only local devices
                continue

            opts = opts.split(',')

            fs_stat = os.statvfs(mount_point)

            size = fs_stat.f_blocks * fs_stat.f_bsize
            free = fs_stat.f_bfree * fs_stat.f_bsize
            avail = fs_stat.f_bavail * fs_stat.f_bsize

            self.usages.append(Usage(dev, mount_point, fs_type, opts, size, free, avail))

        return self

    def to_dict(self):
        return {
            'ver': 1,
            'mount_points': [vars(u) for u in self.usages]
        }

    def stdout(self):
        formats = ('%s', '%s', '%s', '%s', '%d%%', '%s')

        data = [('device', 'size', 'used', 'avail', 'use%', 'mount_point')]
        for u in sorted(self.usages):
            used = u.size - u.free
            use = (1. * used / u.size) * 100.
            row = (u.device, byte_to_human(u.size), byte_to_human(used), byte_to_human(u.available), use, u.mount_point)

            data.append([(f % v) for f, v in zip(formats, row)])

        # Find how wide should our columns be
        maxwidth = [0] * len(formats)
        for row in data:
            for i, c in enumerate(row):
                maxwidth[i] = max(maxwidth[i], len(c))

        # Print the table
        for row in data:
            out_row = []

            for width, column in zip(maxwidth, row):
                out_row.append(column.ljust(width, ' '))

            print(' | '.join(out_row))


class Usage:
    def __init__(self, device, mount_point, fs_type, options, size, free, available):
        """ Convenient usage model

        :param str device: Device path or name
        :param str mount_point: Mount point
        :param str fs_type: File system type
        :param list[str] options: List of mount options
        :param int size: Size in bytes
        :param int free: Free space in bytes
        :param int available: Available space in bytes
        """
        self.device = device
        self.mount_point = mount_point
        self.fs_type = fs_type
        self.options = options
        self.size = size
        self.free = free
        self.available = available

    def __lt__(self, other):
        """ For easy sorting

        :param Usage other: Usage object we're comparing to
        """
        return self.mount_point < other.mount_point


def byte_to_human(val):
    """ Convert byte value into a human readable representation using MB/GB/...

    :param int val: Byte value
    :return: Formatted value
    :rtype: str
    """
    if val == 0:
        return '0'

    for unit in ['k', 'M', 'G', 'T', 'P']:
        val = val / 1024.
        if val < 1024:
            break

    return '%.1f%s' % (val, unit)


report = UsageReport


def main():
    # noinspection PyCompatibility
    import argparse
    parser = argparse.ArgumentParser(description='Collect local disk usage')
    _ = parser.parse_args()

    usage = UsageReport()
    usage.collect_data()
    usage.stdout()


if __name__ == '__main__':
    main()
