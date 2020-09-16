import sys
import logging
import subprocess
from functools import partial

# There is a bug with partial() and Pool.map() for py < 2.7, fixed by using mp.dummy.Pool
if sys.version_info[0] == 2 and sys.version_info[1] < 7:
    from multiprocessing.dummy import Pool
else:
    from multiprocessing import Pool

from ccbr_server.common import Report, shclr, SHBGRED, SHBGGREEN

log = logging.getLogger(__file__)

RETURN_CODES = {
    0: 'success',
    2: 'permission denied',
    124: 'timeout reached'
}


def check_stale_nfs(path, timeout):
    """ The execution function for our pool, checks one NFS if it's stale
    Even if we are root and can't see inside some mounts, if we get permission denied that's fine, it means nfs is
    working but we can't see inside.
    ret == 2 -> permission denied
    ret >= 124 -> timeout reached

    :param str path: NFS mountpoint to check
    :param int timeout: ls timeout in seconds
    :return: checked path and if it's stale or not
    :rtype: tuple[str, bool]
    """
    with open('/dev/null', 'wb') as devnull:  # pipe stdout to devnull instead of printing
        ret = subprocess.call(['timeout', str(timeout), 'ls', path], stdout=devnull, stderr=devnull)
        log.debug("ls on mount point %s returned: %d (%s)", path, ret, RETURN_CODES.get(ret, 'unknown'))
        return path, ret >= 124


class StaleNFSReport(Report):
    """ Checks if NFS mount is stale by running ls on it with a timeout

    :type mounts: dict[str, bool]
    :type groups: dict[str, list[str]]
    """
    name = 'nfs'

    def __init__(self, timeout=2, concurrency=4):
        """
        :param int|str timeout: Stale timeout in seconds
        :param int|str concurrency: Thread pool size for NFS checking
        """
        self.timeout = int(timeout)
        self.concurrency = int(concurrency)

        self.mounts = {}
        self.groups = {}

        self._parse_mounted_nfs()

    def _parse_mounted_nfs(self):
        """ Parse current NFS mounts from mtab
        """
        with open('/etc/mtab') as fio:
            for mline in fio.readlines():
                dev, mount_point, fs_type, opts = mline.split()[:4]

                if fs_type.startswith('nfs') and fs_type != 'nfsd':
                    self.mounts[mount_point] = False
                    log.debug("Adding NFS mount point: %s", mount_point)

    def collect_data(self):
        """ Check NFS concurrently to avoid long wait times if there's a lot of stale mounts
        """
        log.debug("Creating NFS check thread pool of size %d", self.concurrency)
        pool = Pool(processes=self.concurrency)
        res = pool.map(partial(check_stale_nfs, timeout=self.timeout), self.mounts.keys())
        for mount_point, is_stale in res:
            self.mounts[mount_point] = is_stale
        pool.close()

    def to_dict(self):
        result = []
        for mount_point, is_stale in sorted(self.mounts.items()):
            result.append({
                'path': mount_point,
                'is_stale': is_stale
            })

        return {
            'ver': 1,
            'stale_timeout': self.timeout,
            'mount_points': result
        }

    def stdout(self):
        for nfs_mount, is_stale in sorted(self.mounts.items(), key=lambda x: (x[1], x[0])):
            print("%s: %s" % (nfs_mount, is_stale and shclr('stale', SHBGRED) or shclr('OK', SHBGGREEN)))


report = StaleNFSReport


def main():
    # noinspection PyCompatibility
    import argparse
    parser = argparse.ArgumentParser(description='Check for stale NFS mounts')
    _ = parser.parse_args()

    nfs = StaleNFSReport()
    nfs.collect_data()
    nfs.stdout()


if __name__ == '__main__':
    main()
