# transport.py  measurement class for IV like transport measurements
# MMW/HR@KIT 11/2017

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


import numpy as np
import logging
#import matplotlib.pylab as plt
#from scipy.optimize import curve_fit
from time import sleep,time
import sys
import qt
import threading

from qkit.storage import hdf_lib as hdf
#from qkit.analysis.resonator import Resonator as resonator
from qkit.gui.plot import plot as qviewkit
from qkit.gui.notebook.Progress_Bar import Progress_Bar
from qkit.measure.measurement_class import Measurement 
import qkit.measure.write_additional_files as waf

##################################################################

class spectrum(object):
    '''
    usage:

    m = spectrum(vna = vna1)

    m.set_x_parameters(arange(-0.05,0.05,0.01),'flux coil current',coil.set_current, unit = 'mA')
    m.set_y_parameters(arange(4e9,7e9,10e6),'excitation frequency',mw_src1.set_frequency, unit = 'Hz')

    m.gen_fit_function(...)      several times

    m.measure_XX()
    '''

    def __init__(self, IV_Device, exp_name = '', sample = None):

        self.IVD = IV_Device
        
        
        self.exp_name = exp_name
        self._sample = sample



        self.comment = ''
        self.dirname = None

        self.x_set_obj = None
        self.y_set_obj = None

        self.progress_bar = True

        self._plot_comment=""

        self.set_log_function()
        
        self.open_qviewkit = True
        self.qviewkit_singleInstance = False
        
        self._measurement_object = Measurement()
        self._measurement_object.measurement_type = 'transport'
        self._measurement_object.sample = self._sample
        
        self._qvk_process = False
        
        self.number_of_timetraces = 1   #relevant in time domain mode
        
        

    def set_log_function(self, func=None, name = None, unit = None, log_dtype = None):
        '''
        A function (object) can be passed to the measurement loop which is excecuted before every x iteration 
        but after executing the x_object setter in 2D measurements and before every line (but after setting 
        the x value) in 3D measurements.
        The return value of the function of type float or similar is stored in a value vector in the h5 file.

        Call without any arguments to delete all log functions. The timestamp is automatically saved.

        func: function object in list form
        name: name of logging parameter appearing in h5 file, default: 'log_param'
        unit: unit of logging parameter, default: ''
        log_dtype: h5 data type, default: 'f' (float32)
        '''

        if name == None:
            try:
                name = ['log_param']*len(func)
            except Exception:
                name = None
        if unit == None:
            try:
                unit = ['']*len(func)
            except Exception:
                unit = None
        if log_dtype == None:
            try:
                log_dtype = ['f']*len(func)
            except Exception:
                log_dtype = None

        self.log_function = []
        self.log_name = []
        self.log_unit = []
        self.log_dtype = []

        if func != None:
            for i,f in enumerate(func):
                self.log_function.append(f)
                self.log_name.append(name[i])
                self.log_unit.append(unit[i])
                self.log_dtype.append(log_dtype[i])

    def set_x_parameters(self, x_vec, x_coordname, x_set_obj, x_unit = ""):
        '''
        Sets parameters for sweep. In a 3D measurement, the x-parameters will be the "outer" sweep.
        For every x value all y values are swept
        Input:
        x_vec (array): conains the sweeping values
        x_coordname (string)
        x_instrument (obj): callable object to execute with x_vec-values (i.e. vna.set_power())
        x_unit (string): optional
        '''
        self.x_vec = x_vec
        self.x_coordname = x_coordname
        self.x_set_obj = x_set_obj
        self.delete_fit_function()
        self.x_unit = x_unit

    def set_y_parameters(self, y_vec, y_coordname, y_set_obj, y_unit = ""):
        '''
        Sets parameters for sweep. In a 3D measurement, the x-parameters will be the "outer" sweep.
        For every x value all y values are swept
        Input:
        y_vec (array): contains the sweeping values
        y_coordname (string)
        y_instrument (obj): callable object to execute with x_vec-values (i.e. vna.set_power())
        y_unit (string): optional
        '''
        self.y_vec = y_vec
        self.y_coordname = y_coordname
        self.y_set_obj = y_set_obj
        self.delete_fit_function()
        self.y_unit = y_unit

        def set_sweep_type(self, sweep_type = 1):
        '''
        Sets the  sweep type, in the moment only simple sweep types are defined: 
        Input:
        sweep_type:
            0: single sweep START -> END 
            1: double sweep START -> END -> START (default)
            2: triple sweep START -> END -> START -> -END
            3: quad sweep   START -> END -> START -> -END -> START
        
        '''
        self.IV_sweep_type = sweep_type


    def _prepare_measurement_IVD(self):
        '''
        all the relevant settings from the vna are updated and called
        '''

        self.IVD.get_all()
        #ttip.get_temperature() 
        # bias mode is either  current=0 or voltage=1
        self._bias_mode = self.IVD.get_bias_mode()
        
        self._nop = self.IVD.get_nop()
        self._sweeptime_averages = self.IVD.get_sweeptime_averages()
        #self._freqpoints = self.IVD.get_freqpoints()

        if self.averaging_start_ready: self.vna.pre_measurement()

    def _prepare_measurement_file(self):
        '''
        creates the output .h5-file with distinct dataset structures for each measurement type.
        at this point all measurement parameters are known and put in the output file
        '''

        self._data_file = hdf.Data(name=self._file_name)
        self._measurement_object.uuid = self._data_file._uuid
        self._measurement_object.hdf_relpath = self._data_file._relpath
        self._measurement_object.instruments = qt.instruments.get_instruments()

        self._measurement_object.save()
        self._mo = self._data_file.add_textlist('measurement')
        self._mo.append(self._measurement_object.get_JSON())

        # write logfile and instrument settings
        self._write_settings_dataset()
        self._log = waf.open_log_file(self._data_file.get_filepath())

        #if not self._scan_time:
        #    self._data_freq = self._data_file.add_coordinate('frequency', unit = 'Hz')
        #    self._data_freq.add(self._freqpoints)

        
        if self._scan_1D:
            if self._bias_mode:# current bias
                #self._data_freq = self._data_file.add_coordinate('frequency', unit = 'Hz')
                for st in range(self.sweep_type):
                    self._data_I[st] = self._data_file.add_value_vector('I_'+str(st), unit = 'A', save_timestamp = True)
                    self._data_V[st] = self._data_file.add_value_vector('V_'+str(st), x = self._data_I, unit = 'V', save_timestamp = True)
                

        if self._scan_2D:
            self._data_x = self._data_file.add_coordinate(self.x_coordname, unit = self.x_unit)
            self._data_x.add(self.x_vec)
            self._data_amp = self._data_file.add_value_matrix('amplitude', x = self._data_x, y = self._data_freq, unit = 'arb. unit', save_timestamp = True)
            self._data_pha = self._data_file.add_value_matrix('phase', x = self._data_x, y = self._data_freq, unit='rad', save_timestamp = True)

            if self.log_function != None:   #use logging
                self._log_value = []
                for i in range(len(self.log_function)):
                    self._log_value.append(self._data_file.add_value_vector(self.log_name[i], x = self._data_x, unit = self.log_unit[i], dtype=self.log_dtype[i]))

            if self._nop < 10:
                """creates view: plot middle point vs x-parameter, for qubit measurements"""
                self._data_amp_mid = self._data_file.add_value_vector('amplitude_midpoint', unit = 'arb. unit', x = self._data_x, save_timestamp = True)
                self._data_pha_mid = self._data_file.add_value_vector('phase_midpoint', unit = 'rad', x = self._data_x, save_timestamp = True)
                #self._view = self._data_file.add_view("amplitude vs. " + self.x_coordname, x = self._data_x, y = self._data_amp[self._nop/2])

        if self._scan_3D:
            self._data_x = self._data_file.add_coordinate(self.x_coordname, unit = self.x_unit)
            self._data_x.add(self.x_vec)
            self._data_y = self._data_file.add_coordinate(self.y_coordname, unit = self.y_unit)
            self._data_y.add(self.y_vec)
            
            if self._nop == 0:   #saving in a 2D matrix instead of a 3D box HR: does not work yet !!! test things before you put them online.
                self._data_amp = self._data_file.add_value_matrix('amplitude', x = self._data_x, y = self._data_y,  unit = 'arb. unit',   save_timestamp = False)
                self._data_pha = self._data_file.add_value_matrix('phase',     x = self._data_x, y = self._data_y,  unit = 'rad', save_timestamp = False)
            else:
                self._data_amp = self._data_file.add_value_box('amplitude', x = self._data_x, y = self._data_y, z = self._data_freq, unit = 'arb. unit', save_timestamp = False)
                self._data_pha = self._data_file.add_value_box('phase', x = self._data_x, y = self._data_y, z = self._data_freq, unit = 'rad', save_timestamp = False)
                
            if self.log_function != None:   #use logging
                self._log_value = []
                for i in range(len(self.log_function)):
                    self._log_value.append(self._data_file.add_value_vector(self.log_name[i], x = self._data_x, unit = self.log_unit[i], dtype=self.log_dtype[i]))

        if self._scan_time:
            self._data_freq = self._data_file.add_coordinate('frequency', unit = 'Hz')
            self._data_freq.add([self.vna.get_centerfreq()])
            
            self._data_time = self._data_file.add_coordinate('time', unit = 's')
            self._data_time.add(np.arange(0,self._nop,1)*self.vna.get_sweeptime()/(self._nop-1))
            
            self._data_x = self._data_file.add_coordinate('trace_number', unit = '')
            self._data_x.add(np.arange(0, self.number_of_timetraces, 1))
            
            self._data_amp = self._data_file.add_value_matrix('amplitude', x = self._data_x, y = self._data_time, unit = 'lin. mag.', save_timestamp = False)
            self._data_pha = self._data_file.add_value_matrix('phase', x = self._data_x, y = self._data_time, unit = 'rad.', save_timestamp = False)
                    
        if self.comment:
            self._data_file.add_comment(self.comment)
            
        if self.qviewkit_singleInstance and self.open_qviewkit and self._qvk_process:
            self._qvk_process.terminate() #terminate an old qviewkit instance

    def _write_settings_dataset(self):
        self._settings = self._data_file.add_textlist('settings')
        settings = waf.get_instrument_settings(self._data_file.get_filepath())
        self._settings.append(settings)

    def measure_1D(self, rescan = True, web_visible = True):
        '''
        measure method to record a single (averaged) VNA trace, S11 or S21 according to the setting on the VNA
        rescan: If True (default), the averages on the VNA are cleared and a new measurement is started. 
                If False, it will directly take the data from the VNA without waiting.
        '''
        self._scan_1D = True
        self._scan_2D = False
        self._scan_3D = False
        self._scan_time = False
        
        self._measurement_object.measurement_func = 'measure_1D'
        self._measurement_object.x_axis = 'frequency'
        self._measurement_object.y_axis = ''
        self._measurement_object.z_axis = ''
        self._measurement_object.web_visible = web_visible

        if not self.dirname:
            self.dirname = 'IVD_tracedata'
        self._file_name = self.dirname.replace(' ', '').replace(',','_')
        if self.exp_name:
            self._file_name += '_' + self.exp_name
            
        # prepare storage
        self._prepare_measurement_IVD()
        self._prepare_measurement_file()


        """opens qviewkit to plot measurement, amp and pha are opened by default"""
        if self.open_qviewkit:
            self._qvk_process = qviewkit.plot(self._data_file.get_filepath(), datasets=['I_0', 'V_0'])
        print('recording trace...')
        sys.stdout.flush()

        qt.mstart()
        if rescan:
            if self.averaging_start_ready:
                self.vna.start_measurement()
                ti = time()
                if self.progress_bar: self._p = Progress_Bar(self.vna.get_averages(),self.dirname,self.vna.get_sweeptime())
                qt.msleep(.2)
                while not self.vna.ready():
                    if time()-ti > self.vna.get_sweeptime(query=False):
                        if self.progress_bar: self._p.iterate()
                        ti = time()
                    qt.msleep(.2)
                if self.progress_bar:
                    while self._p.progr < self._p.max_it:
                        self._p.iterate()
            else:
                self.vna.avg_clear()
                if self.vna.get_averages() == 1 or self.vna.get_Average() == False:   #no averaging
                    if self.progress_bar:self._p = Progress_Bar(1,self.dirname,self.vna.get_sweeptime())
                    qt.msleep(self.vna.get_sweeptime())      #wait single sweep
                    if self.progress_bar: self._p.iterate()
                else:   #with averaging
                    if self.progress_bar: self._p = Progress_Bar(self.vna.get_averages(),self.dirname,self.vna.get_sweeptime())
                    if "avg_status" in self.vna.get_function_names():
                        for a in range(self.vna.get_averages()):
                            while self.vna.avg_status() <= a:
                                qt.msleep(.2) #maybe one would like to adjust this at a later point
                            if self.progress_bar: self._p.iterate()
                    else: #old style
                        for a in range(self.vna.get_averages()):
                            qt.msleep(self.vna.get_sweeptime())      #wait single sweep time
                            if self.progress_bar: self._p.iterate()

        data_amp, data_pha = self.vna.get_tracedata()
        data_real, data_imag = self.vna.get_tracedata('RealImag')

        self._data_amp.append(data_amp)
        self._data_pha.append(data_pha)
        self._data_real.append(data_real)
        self._data_imag.append(data_imag)
        if self._fit_resonator:
            self._do_fit_resonator()

        qt.mend()
        self._end_measurement()
"""
    def measure_2D(self, web_visible = True):
        '''
        measure method to record a (averaged) VNA trace, S11 or S21 according to the setting on the VNA
        for all parameters x_vec in x_obj
        '''

        if not self.x_set_obj:
            logging.error('axes parameters not properly set...aborting')
            return
        self._scan_1D = False
        self._scan_2D = True
        self._scan_3D = False
        self._scan_time = False
        
        self._measurement_object.measurement_func = 'measure_2D'
        self._measurement_object.x_axis = self.x_coordname
        self._measurement_object.y_axis = 'frequency'
        self._measurement_object.z_axis = ''
        self._measurement_object.web_visible = web_visible

        if not self.dirname:
            self.dirname = self.x_coordname
        self._file_name = '2D_' + self.dirname.replace(' ', '').replace(',','_')
        if self.exp_name:
            self._file_name += '_' + self.exp_name

        if self.progress_bar: self._p = Progress_Bar(len(self.x_vec),'2D VNA sweep '+self.dirname,self.vna.get_sweeptime_averages())

        self._prepare_measurement_vna()
        self._prepare_measurement_file()

        """opens qviewkit to plot measurement, amp and pha are opened by default"""
        if self._nop < 10:
            if self.open_qviewkit: self._qvk_process = qviewkit.plot(self._data_file.get_filepath(), datasets=['amplitude_midpoint', 'phase_midpoint'])
        else:
            if self.open_qviewkit: self._qvk_process = qviewkit.plot(self._data_file.get_filepath(), datasets=['amplitude', 'phase'])
        if self._fit_resonator:
            self._resonator = resonator(self._data_file.get_filepath())
        self._measure()


    def measure_3D(self, web_visible = True):
        '''
        measure full window of vna while sweeping x_set_obj and y_set_obj with parameters x_vec/y_vec. sweep over y_set_obj is the inner loop, for every value x_vec[i] all values y_vec are measured.

        optional: measure method to perform the measurement according to landscape, if set
        self.span is the range (in units of the vertical plot axis) data is taken around the specified funtion(s)
        note: make sure to have properly set x,y vectors before generating traces
        '''
        if not self.x_set_obj or not self.y_set_obj:
            logging.error('axes parameters not properly set...aborting')
            return
        self._scan_1D = False
        self._scan_2D = False
        self._scan_3D = True
        self._scan_time = False
        
        self._measurement_object.measurement_func = 'measure_3D'
        self._measurement_object.x_axis = self.x_coordname
        self._measurement_object.y_axis = self.y_coordname
        self._measurement_object.z_axis = 'frequency'
        self._measurement_object.web_visible = web_visible

        if not self.dirname:
            self.dirname = self.x_coordname + ', ' + self.y_coordname
        self._file_name = '3D_' + self.dirname.replace(' ', '').replace(',','_')
        if self.exp_name:
            self._file_name += '_' + self.exp_name

        if self.progress_bar: self._p = Progress_Bar(len(self.x_vec)*len(self.y_vec),'3D VNA sweep '+self.dirname,self.vna.get_sweeptime_averages())

        self._prepare_measurement_vna()
        self._prepare_measurement_file()
        """opens qviewkit to plot measurement, amp and pha are opened by default"""
        """only middle point in freq array is plotted vs x and y"""
        if self.open_qviewkit: self._qvk_process = qviewkit.plot(self._data_file.get_filepath(), datasets=['amplitude', 'phase'])
        if self._fit_resonator:
            self._resonator = resonator(self._data_file.get_filepath())

        if self.landscape:
            self.center_freqs = np.array(self.landscape).T
        else:
            self.center_freqs = []     #load default sequence
            for i in range(len(self.x_vec)):
                self.center_freqs.append([0])

        self._measure()
"""        
        

    def _measure(self):
        '''
        measures and plots the data depending on the measurement type.
        the measurement loops feature the setting of the objects and saving the data in the .h5 file.
        '''
        qt.mstart()
        try:
            """
            loop: x_obj with parameters from x_vec
            """
            for ix, x in enumerate(self.x_vec):
                self.x_set_obj(x)
                sleep(self.tdx)
                
                if self.log_function != None:
                    for i,f in enumerate(self.log_function):
                        self._log_value[i].append(float(f()))

                if self._scan_3D:
                    for y in self.y_vec:
                        """
                        loop: y_obj with parameters from y_vec (only 3D measurement)
                        """
                        if (np.min(np.abs(self.center_freqs[ix]-y*np.ones(len(self.center_freqs[ix])))) > self.span/2.) and self.landscape:    #if point is not of interest (not close to one of the functions)
                            data_amp = np.zeros(int(self._nop))
                            data_pha = np.zeros(int(self._nop))      #fill with zeros
                        else:
                            self.y_set_obj(y)
                            sleep(self.tdy)
                            if self.averaging_start_ready:
                                self.vna.start_measurement()
                                qt.msleep(.2) #just to make sure, the ready command does not *still* show ready
                                while not self.vna.ready():
                                    qt.msleep(.2)
                            else:
                                self.vna.avg_clear()
                                qt.msleep(self._sweeptime_averages)
                                
                            #if "avg_status" in self.vna.get_function_names():
                            #       while self.vna.avg_status() < self.vna.get_averages():
                            #            qt.msleep(.2) #maybe one would like to adjust this at a later point
                            
                            """ measurement """
                            data_amp, data_pha = self.vna.get_tracedata()

                        if self._nop == 0: # this does not work yet.
                           print data_amp[0], data_amp, self._nop
                           self._data_amp.append(data_amp[0])
                           self._data_pha.append(data_pha[0])
                        else:
                           self._data_amp.append(data_amp)
                           self._data_pha.append(data_pha)
                        if self._fit_resonator:
                            self._do_fit_resonator()
                        if self.progress_bar:
                            self._p.iterate()
                        qt.msleep()
                    """
                    filling of value-box is done here.
                    after every y-loop the data is stored the next 2d structure
                    """
                    self._data_amp.next_matrix()
                    self._data_pha.next_matrix()

                if self._scan_2D:
                    if self.averaging_start_ready:
                        self.vna.start_measurement()
                        qt.msleep(.2) #just to make sure, the ready command does not *still* show ready
                        while not self.vna.ready():
                            qt.msleep(.2)
                    else:
                        self.vna.avg_clear()
                        qt.msleep(self._sweeptime_averages)
                    """ measurement """
                    data_amp, data_pha = self.vna.get_tracedata()
                    self._data_amp.append(data_amp)
                    self._data_pha.append(data_pha)
                    if self._nop < 10:
                        #print data_amp[self._nop/2]
                        self._data_amp_mid.append(float(data_amp[self._nop/2]))
                        self._data_pha_mid.append(float(data_pha[self._nop/2]))
                        
                    if self._fit_resonator:
                        self._do_fit_resonator()
                    if self.progress_bar:
                        self._p.iterate()
                    qt.msleep()
        except Exception as e:
            print e.__doc__
            print e.message        
        finally:
            self._end_measurement()
            qt.mend()

    def _end_measurement(self):
        '''
        the data file is closed and filepath is printed
        '''
        print self._data_file.get_filepath()
        #qviewkit.save_plots(self._data_file.get_filepath(),comment=self._plot_comment) #old version where we have to wait for the plots
        t = threading.Thread(target=qviewkit.save_plots,args=[self._data_file.get_filepath(),self._plot_comment])
        t.start()
        self._data_file.close_file()
        waf.close_log_file(self._log)
        self.dirname = None
        


    def set_span(self, span):
        self.span = span

    def get_span(self):
        return self.span

    def set_tdx(self, tdx):
        self.tdx = tdx

    def set_tdy(self, tdy):
        self.tdy = tdy

    def get_tdx(self):
        return self.tdx

    def get_tdy(self):
        return self.tdy

    def f_parab(self,x,a,b,c):
        return a*(x-b)**2+c

    def f_hyp(self,x,a,b,c):
        "hyperbolic function with the form y = sqrt[ a*(x-b)**2 + c ]"
        return np.sqrt(a*(x-b)**2+c)

    def set_plot_comment(self, comment):
        '''
        Small comment to add at the end of plot pics for more information i.e. good for wiki entries.
        '''
        self._plot_comment=comment