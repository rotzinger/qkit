# worker class for parameter value readout written by HR,JB@KIT 2016

# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin St, Fifth Floor, Boston, MA  02110-1301  USA


#import random
import time#,sys
#import atexit
#import math

from threading import Thread 
#from threading import Lock

        
class IO_worker(Thread):
    " start a thread and get/set the IO data"
    def __init__(self,DATA):
        self.DATA = DATA
        Thread.__init__(self)
        
    def run(self):
        
        print 'Worker started.'
        while True:
            for p in self.DATA.parameters:
                if p.logging:
                    p.create_logfile()
            while int(time.strftime("%H%M",time.localtime(time.time()+10))) != 0:
                #readout all parameters
                for p in self.DATA.parameters:
                    if p.schedule():
                        p.store_value(p.data_request_object())
                        if self.DATA.debug: print 'readout %s.'%p.name
                                
                time.sleep(self.DATA.cycle_time)
            for p in self.DATA.parameters:
                if p.logging: p.close_logfile()
            time.sleep(70)


