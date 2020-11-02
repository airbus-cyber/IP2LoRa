#!/usr/bin/python3

import logging
import threading
import time
import random
from socketserver import TCPServer
from collections import defaultdict

from umodbus import conf
from umodbus.server.tcp import RequestHandler, get_server
from umodbus.utils import log_to_stream



class manage_datastore(threading.Thread):
    def __init__(self, datastore=None):
        threading.Thread.__init__(self)
        self._datastore = defaultdict(int)
        self._lock_datastore = threading.Lock()
        self._isRunning = False


    def run(self):
        self._isRunning = True

        while self._isRunning:
            # increase sign of life
            self._lock_datastore.acquire()
            self._datastore[0] += 1
            self._datastore[0] = self._datastore[0] % 0xfff

            for i in range(1,0x40):
                self._datastore[i] = random.randint(-0x700,0x700)
            self._lock_datastore.release()
            time.sleep(10)



    def stop(self):
        self._isRunning = False


    def get_value(self, idx):
        self._lock_datastore.acquire()
        v = self._datastore[idx]
        self._lock_datastore.release()
        return v



# Add stream handler to logger 'uModbus'.
log_to_stream(level=logging.DEBUG)



# Enable values to be signed (default is False).
conf.SIGNED_VALUES = True

TCPServer.allow_reuse_address = True
app = get_server(TCPServer, ('0.0.0.0', 502), RequestHandler)


t_manage_datastore = manage_datastore()



@app.route(slave_ids=[1], function_codes=[3, 4], addresses=list(range(0, 0x40)))
def read_data_store(slave_id, function_code, address):
    """" Return value of address. """
    return t_manage_datastore.get_value(address)




if __name__ == '__main__':
    t_manage_datastore = manage_datastore()
    t_manage_datastore.start()
    try:
        app.serve_forever()
    finally:
        app.shutdown()
        app.server_close()
    t_manage_datastore.stop()
    t_manage_datastore.join()