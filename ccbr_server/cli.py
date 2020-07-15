import json
import logging
import os
import socket

from ccbr_server.disk_usage import UsageReport
from ccbr_server.raid import RaidReport, RaidReportException
from ccbr_server.raid_megacli import MegaCliReport
from ccbr_server.raid_omreport import OmreportReport
from ccbr_server.stale_nfs import StaleNFSReport

try:
    import configparser as configparser
except ImportError:
    import ConfigParser as configparser

log = logging.getLogger(__file__)

try:
    # noinspection PyCompatibility
    from urllib.request import urlopen, Request
except ImportError:
    # noinspection PyCompatibility
    from urllib2 import urlopen, Request


def all_reports(parser, args, config):
    """

    :param ArgumentParser parser:
    :param Namespace args:
    :param configparser.ConfigParser config:
    """
    reports = []

    # Print by default if we're in offline mode
    stdout = args.print_reports or args.offline

    for check in args.enabled_checks.split(','):
        if check == 'raid':
            log.debug("Initializing RAID report")
            report = None

            if config.has_option('raid', 'type'):
                raid_type = config.get('raid', 'type')
                if raid_type == 'megacli':
                    report = MegaCliReport()
                elif raid_type == 'omreport':
                    report = OmreportReport()

            if report is None:
                try:
                    report = RaidReport.automatic_cli()
                except RaidReportException:
                    parser.error("Can't find a supported RAID manager")

            log.info("Adding %s to reports", report.__class__.__name__)

            reports.append(report)
        elif check == 'nfs':
            log.info("Adding StaleNFSReport to reports")
            reports.append(StaleNFSReport(timeout=config.get('nfs', 'stale_timeout'),
                                          concurrency=config.get('nfs', 'concurrency')))
        elif check == 'disk_usage':
            log.info("Adding UsageReport to reports")
            reports.append(UsageReport())

    post = {
        'reports': {}
    }

    for report in reports:
        report.collect_data()
        post['reports'][report.name] = report.to_dict()

        if stdout:
            report.stdout()

    if not args.offline:  # POST here
        if not config.get('DEFAULT', 'hostname'):
            config.set('DEFAULT', 'hostname', socket.gethostname().split('.')[0])

        log.info("Sending reports to %s", config.get('DEFAULT', 'post_url'))

        req = Request(config.get('DEFAULT', 'post_url'))
        req.add_header('Content-Type', 'application/json')
        _ = urlopen(req, json.dumps(post))  # Ignore response for now


def main():
    if os.getuid() != 0:
        print("This script must be run by root!")
        # exit(1)

    project_root = os.path.dirname(os.path.dirname(__file__))
    default_config = os.path.join(project_root, 'etc/ccbr_scripts.ini')

    config = configparser.ConfigParser()
    config.read([default_config, '/etc/ccbr_scripts.ini'])

    # noinspection PyCompatibility
    import argparse
    parser = argparse.ArgumentParser(
        description='Collect server reports and send them to a monitoring site. Default parameters are read from '
                    '/etc/ccbr_scripts.ini, arguments to this script will override them.')
    parser.add_argument("-v", "--verbose", dest="verbose_count",
                        action="count", default=0,
                        help="increases log verbosity for each occurence.")

    subparsers = parser.add_subparsers()

    parser_all = subparsers.add_parser('all', help='Fully autonomous reporting for all reports')
    parser_all.add_argument('-c', '--enabled-checks',
                            default=config.get('DEFAULT', 'enabled_checks'))
    parser_all.add_argument('-o', '--offline', default=False, action='store_true',
                            help='Do not POST to URL, just print the report to stdout.')
    parser_all.add_argument('-p', '--print-reports', default=False, action='store_true',
                            help='Print each report to stdout.')
    parser_all.set_defaults(func=all_reports)

    args = parser.parse_args()

    # Logging
    log_fmt = "[%(asctime)-15s] %(name)s %(levelname)s %(message)s"
    log.setLevel(max(5 - args.verbose_count, 0) * 10)
    logging.basicConfig(format=log_fmt, level=log.level)

    # noinspection PyStatementEffect
    args.func(parser, args, config)


if __name__ == '__main__':
    main()
