from __future__ import print_function
from __future__ import division
from __future__ import unicode_literals
from __future__ import absolute_import
from future import standard_library


standard_library.install_aliases()

from rohc import *
from RohcCompressor import *
from RohcDecompressor import *



def compressor():
    return RohcCompressor(cid_type=ROHC_LARGE_CID, profiles=[ROHC_PROFILE_IP, ROHC_PROFILE_TCP], verbose=False)

def decompressor():
    return RohcDecompressor(cid_type=ROHC_LARGE_CID, profiles=[ROHC_PROFILE_IP, ROHC_PROFILE_TCP], verbose=False)

def compress(comp, data, debug=False):
    (status, comp_pkt) = comp.compress(data)
    if status == ROHC_STATUS_OK:
        data = comp_pkt
    else:
        if debug:
            print("ROHC compress ip hdr failed")
    return data


def decompress(decomp, data, debug=False):
    (status, decomp_pkt, _, _) = decomp.decompress(data)
    if status == ROHC_STATUS_OK:
        data = decomp_pkt
    else:
        if debug:
            print("ROHC decompress ip hdr failed!")
    return data