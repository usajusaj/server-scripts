import os

try:
    import configparser as configparser
except ImportError:
    # noinspection PyPep8Naming
    import ConfigParser as configparser


def project_root():
    return os.path.dirname(os.path.dirname(__file__))


project_root = project_root()


def get_config():
    """ Get configuration by parsing default settings and any custom settings in /etc

    :return: Configuration
    :rtype: configparser.ConfigParser
    """
    default_config = os.path.join(project_root, 'etc/ccbr_scripts.ini')

    config = configparser.ConfigParser()
    config.read([default_config, '/etc/ccbr_scripts.ini'])

    return config


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


SHBGRED = 41
SHBGGREEN = 42
SHBGORANGE = 43


def shclr(msg, code):
    """ Wrap msg in bash escape characters

    :param str msg: Message
    :param int code: escape character
    :return: Escaped message
    """
    return '\033[%sm%s\033[0m' % (code, msg)


class Report(object):
    name = ''

    def collect_data(self):
        """ Run data collection for this report

        :rtype: Report
        """
        raise NotImplementedError()

    def to_dict(self):
        """ Format this report as a dictionary to send via json

        :return: dictionary representation of this report
        :rtype: dict[str, Any]
        """
        raise NotImplementedError()

    def stdout(self):
        """ Print report to stdout
        """
        raise NotImplementedError()

    @staticmethod
    def simple_report():
        """ Convenience method that saves 3 separate calls for each report

        :return: Dictionary representation of this report
        :rtype: dict[str, Any]
        """
        return Report().collect_data().to_dict()
