
import re
import random
import zlib
import getmac
import pyroute2


def mac_to_int(mac):
    res = re.match('^((?:(?:[0-9a-f]{2}):){5}[0-9a-f]{2})$', mac.lower())
    if res is None:
        raise ValueError('invalid mac address')
    return int(res.group(0).replace(':', ''), 16)

def int_to_mac(macint):
    if type(macint) != int:
        raise ValueError('invalid integer')
    return ':'.join(['{}{}'.format(a, b)
                     for a, b
                     in zip(*[iter('{:012x}'.format(macint))]*2)])


def del_random_in_list(my_list, nb2del=1):
    i = 0
    while i < nb2del:
        idx2del = random.randint(0, len(my_list)-1)
        del my_list[idx2del]
        i += 1
    return my_list


def zlib_compress(data):
    return zlib.compress(data, level=9)


def zlib_decompress(data, debug=False):
    try:
        data = zlib.decompress(data)
    except Exception as e:
        if debug:
            print("zlib_decompress failed!")
            print(e)
        return data
    return data

def get_mac(iface="eth0", ipaddress="127.0.0.1"):
    return getmac.get_mac_address(interface=iface, ip=ipaddress, network_request=False)

"""
Get gateway ip to route packet
"""
def get_gateway(ip_dst="8.8.8.8"):
    ipr = pyroute2.IPRoute()
    m = ipr.route('get', dst=ip_dst)[0]
    return m.get_attr("RTA_GATEWAY")


