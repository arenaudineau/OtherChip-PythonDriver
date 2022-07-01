from typing import List

from d3 import mcd, B1530Lib
from d3.mcd import State #, add other usefull import here

import functools as ft

###############################
# WGFMU Configuration Constants
WGFMU_CONFIG_SENSE = 0

# Utils export from mcd
print_ports = mcd.MCDriver.print_ports
print_visa_dev = B1530Lib.print_devices

######################
# class Design3Driver
######################
class Design3Driver:
	"""
		Design3 Driver

		...
		Attributes
		----------
		_mcd: mcd.MCDriver
			The low-level driver used for the µc

		_b1530: B1530Lib.B1530
			The driver used to control the B1530

		_last_wgfu_config: int
			Stores the last operation performed, not to reconfigure everything if it is the same (see 'WGFMU Configuration Constants')
	"""

	def __init__(self, uc_pid = mcd.MCDriver.DEFAULT_PID, visa_addr = B1530Lib.B1530.DEFAULT_ADDR):
		"""
		Creates the driver.

		Details:
			It will search for the µc using the PID value 'DEFAULT_PID' or the one provided in argument.
			Takes the first found if many have the same PID.
			RAISE Exception if not found.

		Arguments:
			pid: optional, the pid to search for.
		"""
		self._mcd = mcd.MCDriver(uc_pid)

		try:
			self._b1530 = B1530Lib.B1530(addr=visa_addr)
		except Exception as e:
			self._mcd.ser.close()
			raise e
		
		self.reset_state()

	def reset_state(self):
		"""
		Resets the state of the driver, to run after exception catching for example.
		"""
		self._mcd.flush_input() # Flush any remaning inputs stuck in the buffer
		self._mcd.ack_mode(mcd.ACK_ALL) # Enable ACK for every procedure commands
		self._last_wgfu_config = -1 # Initially, no WGFMU Configuration
		self.discharge_delay = None

	##### µC-RELATED METHODS #####
	# EMPTY

	##### B1530-RELATED METHODS #####
	def configure_wgfmu_default(self):
		"""
		Configures the WGFMUs by default
		"""
		chan = self._b1530.chan

		bit_in = chan[1]
		cwl    = chan[2]
		csl    = chan[3]
		clk    = chan[4]

		self.discharge_delay = self.discharge_delay or 0.3e-6

		bit_in.name = 'bit_in'
		cwl.name    = 'cwl'
		csl.name    = 'csl'
		clk.name    = 'clk'

		bit_in.wave = B1530Lib.Pulse(
			voltage  = 1,
			interval = 1e-6,
			edges    = 1e-7,
			length   = 2e-6,
		)

		cwl.wave = bit_in.wave.centered_on(
			voltage  = 1,
			length   = 1e-6,
		)

		cwl.wave.wait_end += self.discharge_delay

		csl.wave = cwl.wave.reduced_length(
			length   = cwl.wave.length - self.discharge_delay,
			voltage = 1,
		)

		clk.wave = B1530Lib.Pulse(
			voltage  = 1,
			interval = 1e-7,
			edges    = 1e-7,
			length   = cwl.wave.interval / 5, 
		)
		
		clk.wave.wait_begin = cwl.wave.get_total_duration() # Clk only when cwl has been reset
		clk.wave.wait_end   = 1e-8

		# Repeat once control signals, but this time with bit_in at GND 
		cwl.wave.repeat(1)
		csl.wave.repeat(1)
		clk.wave.append(
			clk.wave.copy(wait_begin = clk.wave.wait_begin - clk.wave.length)
		)

		self._b1530.configure()

	##### HIGH-LEVEL ARRAY MANIPULATION METHODS #####
	@staticmethod
	def ternary_to_repr(t: int):
		return {
			 1: 0b10,
			 0: 0b00,
			-1: 0b01,
		}[t]

	@staticmethod
	def binary_to_repr(b: int):
		return {
			 1: 0b1,
			-1: 0b0,
			 0: 0b0, # == mcd.State.RESET
		}[b]

	def fill(self, values):
		"""
		Fills in the array
		
		Parameters:
			values: List[List[int]]
			Details:
				2D array of '1', '-1' or '0'
				[[col0, col1, ..., col7], # row 0
				[col0, col1, ..., col7],  # row 1
					...,
				[col0, col1, ..., col7]]  # row 7
		"""
		if len(values) != 8 and len(values[0]) != 8:
			raise ValueError("Expected 8x8 array")
		
		values = list(ft.reduce(
				lambda reduced_rows, rows:
					reduced_rows + list(map(self.ternary_to_repr, rows)),
				values,
				[],
		))
		self._mcd.fill(*values)

	def sense(self):
		"""
		Reads out the array

		Returns:
			values: List[List[int]]
			Details:
				2D array of integers '0b00', '0b10' or '0b01'
				[[col0, col1, ..., col7], # row 0
				[col0, col1, ..., col7],  # row 1
					...,
				[col0, col1, ..., col7]]  # row 7
		"""
		return self._mcd.sense()