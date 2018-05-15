#!/usr/bin/python

from collections import namedtuple


from six.moves import range


KHZ = 1000
MHZ = KHZ * 1000


# https://www.sigidwiki.com/wiki/Iridium
ChannelInfo = namedtuple('ChannelInfo', ['description', 'frequency'])
SIMPLEX_CHANELS = {
    ChannelInfo('Guard Channel', 1626.020833 * MHZ),
    ChannelInfo('Guard Channel', 1626.062500 * MHZ),
    ChannelInfo('Quaternary Messaging', 1626.104167 * MHZ),
    ChannelInfo('Tertiary Messaging', 1626.145833 * MHZ),
    ChannelInfo('Guard Channel', 1626.187500 * MHZ),
    ChannelInfo('Guard Channel', 1626.229167 * MHZ),
    ChannelInfo('Ring Alert', 1626.270833 * MHZ),
    ChannelInfo('Guard Channel', 1626.312500 * MHZ),
    ChannelInfo('Guard Channel', 1626.354167 * MHZ),
    ChannelInfo('Secondary Messaging', 1626.395833 * MHZ),
    ChannelInfo('Primary Messaging', 1626.437500 * MHZ),
    ChannelInfo('Guard Channel', 1626.479167 * MHZ),
}
DUPLEX_CHANELS = frozenset(SIMPLEX_CHANELS)

DUPLEX_CHANELS = set()
for n in range(1, 240):
    frequency = (1616 + 0.020833 * (2 * n - 1)) * MHZ
    DUPLEX_CHANELS.add(ChannelInfo('Channel {}'.format(n), frequency))
DUPLEX_CHANELS = frozenset(DUPLEX_CHANELS)

ALL_CHANELS = frozenset((SIMPLEX_CHANELS | DUPLEX_CHANELS))


def add_chanel_lines_to_axis(axis):
    for channel in ALL_CHANELS:
        if 'Guard' in channel.description:
            color = 'tab:gray'
        elif 'Messaging' in channel.description:
            color = 'tab:orange'
        elif 'Ring' in channel.description:
            color = 'tab:red'
        else:
            color = 'tab:green'
        axis.axhline(channel.frequency, color=color, alpha=0.3, label=channel.description)


if __name__ == '__main__':
    raise RuntimeError('{} can only be used as a module'.format(__name__))
