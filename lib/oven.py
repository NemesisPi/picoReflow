#Include to guarantee that division will produce a floating-point value in Python 2.x


import threading
import time
import random
import datetime
import logging
import json
import config
import math



log = logging.getLogger(__name__)

try:
    if config.max31855 + config.max6675 + config.max31855spi != 1:
        log.error("choose (only) one converter IC")
        exit()
    if config.max31855:
        from max31855 import MAX31855, MAX31855Error
        log.info("import MAX31855")
        spi_reserved_gpio = [config.gpio_sensor_cs, config.gpio_sensor_clock, config.gpio_sensor_data]
    if config.max31855spi:
        import Adafruit_GPIO.SPI as SPI
        from max31855spi import MAX31855SPI, MAX31855SPIError
        log.info("import MAX31855SPI")
        spi_reserved_gpio = [7, 8, 9, 10, 11]

    if config.max6675:
        from max6675 import MAX6675, MAX6675Error
        log.info("import MAX6675")
        spi_reserved_gpio = [config.gpio_sensor_cs, config.gpio_sensor_clock, config.gpio_sensor_data]


    if config.air_enabled and config.gpio_air in spi_reserved_gpio:
        raise Exception("gpio_air pin %s collides with SPI pins %s" % (config.gpio_air, spi_reserved_gpio))
    if config.cool_enabled and config.gpio_cool in spi_reserved_gpio:
        raise Exception("gpio_cool pin %s collides with SPI pins %s" % (config.gpio_cool, spi_reserved_gpio))
    if config.door_enabled and config.gpio_door in spi_reserved_gpio:
        raise Exception("gpio_door pin %s collides with SPI pins %s" % (config.gpio_door, spi_reserved_gpio))
    if config.heat_enabled and config.gpio_heat in spi_reserved_gpio:
        raise Exception("gpio_heat pin %s collides with SPI pins %s" % (config.gpio_heat, spi_reserved_gpio))
    if config.heat2_enabled and config.gpio_heat2 in spi_reserved_gpio:
        raise Exception("gpio_heat2 pin %s collides with SPI pins %s" % (config.gpio_heat2, spi_reserved_gpio))

    sensor_available = True

except ImportError:
    log.exception("Could not initialize temperature sensor, using dummy values!")
    sensor_available = False

try:
    import RPi.GPIO as GPIO
    GPIO.setmode(GPIO.BCM)
    GPIO.setwarnings(False)
    GPIO.setup(config.gpio_heat, GPIO.OUT) 	if config.heat_enabled else None
    GPIO.setup(config.gpio_heat2, GPIO.OUT) if config.heat2_enabled else None
    GPIO.setup(config.gpio_cool, GPIO.OUT) 	if config.cool_enabled else None
    GPIO.setup(config.gpio_air, GPIO.OUT) 	if config.air_enabled else None
    GPIO.setup(config.gpio_door, GPIO.IN, pull_up_down=GPIO.PUD_UP) if config.door_enabled else None
    gpio_available = True

except ImportError:
    msg = "Could not initialize GPIOs, oven operation will only be simulated!"
    log.warning(msg)
    gpio_available = False


class Oven (threading.Thread):
    STATE_IDLE = "IDLE"
    STATE_RUNNING = "RUNNING"
    STATE_TUNING = "TUNING"

    def __init__(self, simulate=False, time_step=config.sensor_read_period):
        threading.Thread.__init__(self)
        self.daemon=True
        self.simulate = simulate
        self.time_step = time_step
        #self.reset()
        if simulate:
            self.temp_sensor = TempSensorSimulate(self, 0.5, self.time_step)
        if sensor_available:
            self.temp_sensor = TempSensorReal(self.time_step)
        else:
            self.temp_sensor = TempSensorSimulate(self,
                                                  self.time_step,
                                                  self.time_step)
        self.temp_sensor.start()
        self.PWM = PWM(config.PWM_Period_s, config.PWM_MinimumOnOff_s, config.PWM_PeriodMax_s)
        self.PWM.start()
        self.start()
        self.pid = PID(ki=config.pid_ki, kd=config.pid_kd, kp=config.pid_kp)
        self.heat = 0
        self.reset()



    def reset(self):
        self.profile = None
        self.start_time = 0
        self.runtime = 0
        self.totaltime = 0
        self.target = 0
        self.heatOn = False
        self.heat = 0
        self.door = self.get_door_state()
        self.state = Oven.STATE_IDLE
        self.PWM.setHeat1(0)
        self.PWM.setHeat2(0)
        self.set_cool(False)
        self.set_air(False)
        self.pid.reset()

    def run_profile(self, profile, resume = False):
        log.info("Running profile %s" % profile.name)
        self.profile = profile
        self.totaltime = profile.get_duration()
        if resume:
            progress = self.profile.findTemp(self.temp_sensor.temperature)
            self.start_time = datetime.datetime.now() - progress
            log.info("Skipping ahead to %s", str(progress))
        else:
            self.start_time = datetime.datetime.now()
        self.state = Oven.STATE_RUNNING
        self.pid.reset()
        log.info("Starting")

    def abort_run(self):
        self.reset()

    def run_tuning(self): #, temp_target, n_cycles):
        temp_target = config.tune_target_temp
        n_cycles = config.tune_cycles

        log.info("Running auto-tune algorithm. Target: %.0f deg C, Cycles: %.0f", temp_target, n_cycles);
        self.state = Oven.STATE_TUNING
        self.start_time = datetime.datetime.now()
        self.heatOn = True
        self.heat = 0.8       ##Marlin starts at 50%. What happens if this isn't enough to hit the target?
        self.bias = .4
        self.tunecycles = n_cycles
        self.d = .4
        self.target = temp_target
        self.totaltime = n_cycles * 1000        #Just an estimate; no good way to fill this in
        self.cycles = 0
        self.maxtemp = -10000
        self.mintemp = 10000
        self.t1 = datetime.datetime.now()   #t1 is when the temp goes over target
        self.t2 = self.t1                   #t2 is when it goes under
        self.t_high = 0
        self.t_low = 0
        log.info("Starting")

    def run(self):
        temperature_count = 0
        last_temp = 0
        pid = 0

        while True:

            now = datetime.datetime.now()
            
            #Log Data:
            with open("/home/pi//NemesisPI/storage/logs/log_{0}.txt".format(now.strftime("")), "a") as filelog:
                filelog.write("".format(
                    now.strftime(""),
                    self.temp_sensor.temperature,
                    self.target,
                    self.heat))

            self.door = self.get_door_state()


            if self.state == Oven.STATE_TUNING:

                log.debug("running at %.1f deg C (Target: %.1f) , heat %.2f, cool %.2f, air %.2f, door %s (%.1fs/%.0f)" %
                         (self.temp_sensor.temperature, self.target, self.heat, self.cool, self.air, self.door,
                          self.runtime,
                          self.totaltime))
                self.runtime = (now-self.start_time).total_seconds()
                #This algorithm is based off that used by Marlin (3-D printer control).
                #It essentially measures the overshoot and undershoot when turning the heat on and off,
                #Then applies some guideline formulas to come up with the K values
                #This is called the Relay Method
                temp = self.temp_sensor.temperature
                self.maxtemp = max(self.maxtemp, temp)
                self.mintemp = min(self.mintemp, temp)
                if self.heatOn and temp > self.target and (now - self.t2).total_seconds() > 60.0:
                    #These events occur once we swing over the temperature target
                    #debounce: prevent noise from triggering false transition
                                                            ##This might need to be longer for large systems
                    self.heatOn = False
                    self.heat = (self.bias - self.d)
                    self.t1 = now
                    self.t_high = (self.t1-self.t2).total_seconds()
                    self.maxtemp = temp
                    log.info("Over Target, setting heat to %.2f", self.heat)

                if self.heatOn == False and temp < self.target and (now - self.t1).total_seconds() > 60.0:
                    #This occurs when we swing below the target
                    self.heatOn = True
                    self.t2 = now
                    self.t_low = (self.t2-self.t1).total_seconds()
                    if self.cycles > 0:
                        self.bias = self.bias + (self.d * (self.t_high - self.t_low))/(self.t_low + self.t_high)
                        self.bias = sorted([0.10, self.bias, 0.90])[1]
                        self.d = self.bias if self.bias < 0.50 else 1 - self.bias
                        log.info("bias: %.0f, d: %.0f, min: %.0f, max: %.0f", self.bias, self.d, self.mintemp, self.maxtemp)
                    if self.cycles > 2:
                        #Magic formulas:
                        Ku = (4.0 * self.d)/ (math.pi * (self.maxtemp - self.mintemp) / 2)
                        Tu = (self.t_low + self.t_high)
                        log.info("Ku: %.6f, Tu: %.6f", Ku, Tu)
                        Kp = 0.6 * Ku
                        Ki = 2*Kp/Tu
                        Kd = Kp * Tu/8
                        log.info("Kp: %.8f, Ki: %.8f, Kd = %.8f", Kp, Ki, Kd)
                    self.heat = (self.bias + self.d)
                    self.cycles= self.cycles + 1
                    log.info(
                        "Under Target, new values: d: %.2f, bias: %.2f, t_low: %.0f, t_high: %.0f, MaxT: %.0f, MinT: %.0f",
                        self.d, self.bias, self.t_low, self.t_high, self.maxtemp, self.mintemp)
                    self.mintemp = self.target
                    self.maxtemp = self.target


                if  self.cycles > self.tunecycles:
                    self.pid.Kp = Kp
                    self.pid.Ki = Ki
                    self.pid.Kd = Kd
                    log.info("Tuning Complete.")
                    log.info("Make these values permanent by entering them in to the config.py file.")
                    self.reset()
                    continue

            elif self.state == Oven.STATE_RUNNING:
                if self.simulate: ##Probably just won't touch the simulation
                    self.runtime += 0.5
                else:
                    runtime_delta = datetime.datetime.now() - self.start_time
                    self.runtime = runtime_delta.total_seconds()
                log.info("running at %.1f deg C (Target: %.1f) , heat %.2f, cool %.2f, air %.2f, door %s (%.1fs/%.0f)" %
                         (self.temp_sensor.temperature, self.target, self.heat, self.cool, self.air, self.door, self.runtime,
                          self.totaltime))
                self.target = self.profile.get_target_temperature(self.runtime, self.temp_sensor.temperature)
                pid = self.pid.compute(self.target, self.temp_sensor.temperature + config.thermocouple_offset)

                ##Should we store the current run time in case of power failure?
                ##Add to future release
                
                log.debug("pid: %.3f" % pid)

                self.set_cool(pid <= -1)
                if(pid > 0):
                    ##keep this... but double check that it won't cause false failure in large systems
                    # The temp should be changing with the heat on
                    # Count the number of time_steps encountered with no change and the heat on
                    if last_temp == self.temp_sensor.temperature:
                        temperature_count += 1 ##rename this variable
                    else:
                        temperature_count = 0
                    # If the heat is on and nothing is changing, reset
                    # The direction or amount of change does not matter
                    # This prevents runaway in the event of a sensor read failure
                    if temperature_count > 100:
                        log.info("Error reading sensor, oven temp not responding to heat.")
                        self.reset()
                        continue
                else:
                    temperature_count = 0


                last_temp = self.temp_sensor.temperature
                self.heat = pid


                #if self.profile.is_rising(self.runtime):
                #    self.set_cool(False)
                #    self.set_heat(self.temp_sensor.temperature < self.target)
                #else:
                #    self.set_heat(False)
                #    self.set_cool(self.temp_sensor.temperature > self.target)


                # if self.temp_sensor.temperature > 200:
                    # self.set_air(False)
                # elif self.temp_sensor.temperature < 180:
                    # self.set_air(True)

                # High Limit for Emergency Shut off
                if(self.temp_sensor.temperature + config.thermocouple_offset >= config.emergency_shutoff_temp):
                    log.info("Warning! Temperature above emergency shut off temp set in config, Stopping to protect your device")
                    self.reset()

                if self.runtime >= self.totaltime:
                    self.reset()
                    continue
            else:  # Not tuning or running - make sure oven is off
                self.heat = 0

                                    
               
            #Do these regardless of the machine state
            if self.heat > 0:
                self.PWM.setHeat1(self.heat + config.heat1adj)
                self.PWM.setHeat2(self.heat + config.heat2adj)
            else:
                self.PWM.setHeat1(0)
                self.PWM.setHeat2(0)
            time.sleep(self.time_step)


    def set_cool(self, value):
        if value:
            self.cool = 1.0
            if gpio_available and config.cool_enabled:
                GPIO.output(config.gpio_cool, GPIO.LOW)
        else:
            self.cool = 0.0
            if gpio_available and config.cool_enabled:
                GPIO.output(config.gpio_cool, GPIO.HIGH)

    def set_air(self, value):
        if value:
            self.air = 1.0
            if gpio_available and config.air_enabled:
                GPIO.output(config.gpio_air, GPIO.LOW)
        else:
            self.air = 0.0
            if gpio_available and config.air_enabled:
                GPIO.output(config.gpio_air, GPIO.HIGH)

    def get_state(self):
        state = {
            'runtime': self.runtime,
            'temperature': self.temp_sensor.temperature + config.thermocouple_offset,
            'target': self.target,
            'state': self.state,
            'heat': sorted((0, self.heat, 1))[1],
            'cool': self.cool,
            'air': self.air,
            'totaltime': self.totaltime,
            'door': self.door
        }
        return state

    def get_door_state(self):

        if gpio_available and config.door_enabled:
            return "OPEN" if GPIO.input(config.gpio_door) else "CLOSED"
        else:
            return "UNKNOWN"


class PWM(threading.Thread):
    def __init__(self, Period_s, MinimumOnOff_s, PeriodMax_s):
        threading.Thread.__init__(self)
        self.daemon = True
        self.PeriodSet = Period_s
        self.MinimumOnOff = MinimumOnOff_s
        self.PeriodMax = PeriodMax_s
        self.Heat1 = 0
        self.Heat2 = 0
        self.lock = threading.Lock()
        self.period = 1
        self.heat1On = 0
        self.heat2On = 0

    def setHeat1(self, newPWM):
        self.Heat1 = sorted((0, newPWM, 1))[1]
        self.adjPWM()
    def setHeat2(self, newPWM):
        self.Heat2 = sorted((0, newPWM, 1))[1]
        self.adjPWM()

    def adjPWM(self):
        period = self.PeriodSet

        ##only do period adjustments for heat1? makes it simpler
        #Calculate on/off time of each cycle
        heat1ontime = self.Heat1 * period
        heat1offtime = period - heat1ontime
        if (heat1ontime < self.MinimumOnOff):
            #the on time is under the minimum. First try extending the period
            if (self.Heat1 * self.PeriodMax >= self.MinimumOnOff):
                period = self.MinimumOnOff / self.Heat1
                heat1ontime = self.MinimumOnOff
            else:
                # That didn't work; just turn the heater off
                heat1ontime = 0
        elif (heat1offtime < self.MinimumOnOff):
            if ((1-self.Heat1) * self.PeriodMax >= self.MinimumOnOff):
                period = self.MinimumOnOff / (1-self.Heat1)
                heat1ontime = period - self.MinimumOnOff
            else:
                heat1ontime = period

        with self.lock:
            self.period = period
            self.heat1On = heat1ontime
            h2 = self.Heat2 * period
            self.heat2On = 0 if h2 < self.MinimumOnOff else period if h2 > (period - self.MinimumOnOff) else h2

    def run(self):

        if config.heater_invert:
            ON = GPIO.LOW
            OFF = GPIO.HIGH
        else:
            ON = GPIO.HIGH
            OFF = GPIO.LOW


        while True:
            start = datetime.datetime.now()
            #grab our values here in case they change mid-period
            #Using a lock to prevent values being acquired while they're changed
            with self.lock:
                pwmperiod = self.period
                pwmheat1 = self.heat1On
                pwmheat2 = self.heat2On


            # To improve performance, the heaters will alternate. Heater 1 turns on at the beginning of the period,
            # and heater 2 turns off at the end of the period. They may overlap in the middle if the sum of the times
            # exceeds the period, otherwise there will some time where neither is on.
            # Each on/off checks to make sure the the on time is not zero or one
            if pwmheat1 != 0: GPIO.output(config.gpio_heat, ON)
            if (pwmheat1 <= pwmperiod - pwmheat2):		#In this case, 1 turns off before 2 turns on
                time.sleep(self.heat1On)
                if pwmheat1 != pwmperiod: GPIO.output(config.gpio_heat, OFF)

                #When sleeping here, need to check that the required time has not already elapsed
                t = (pwmperiod - pwmheat2) - (datetime.datetime.now()-start).total_seconds()
                if t > 0: time.sleep(t)
                if pwmheat2 != 0: GPIO.output(config.gpio_heat2, ON)
            else:										#Otherwise, 2 turns on before 1 turns off
                time.sleep(pwmperiod - pwmheat2)
                if pwmheat2 != 0: GPIO.output(config.gpio_heat2, ON)
                t = pwmheat1 - (datetime.datetime.now()-start).total_seconds()
                if t > 0: time.sleep(t)
                if pwmheat1 != pwmperiod: GPIO.output(config.gpio_heat, OFF)

            t = pwmperiod - (datetime.datetime.now()-start).total_seconds()
            if t > 0: time.sleep(t)
            if pwmheat2 != pwmperiod: GPIO.output(config.gpio_heat2, OFF)





class TempSensor(threading.Thread):
    def __init__(self, time_step):
        threading.Thread.__init__(self)
        self.daemon=True
        self.temperature = 0
        self.time_step = time_step


class TempSensorReal(TempSensor):
    def __init__(self, time_step):
        TempSensor.__init__(self, time_step)
        if config.max6675:
            log.info("init MAX6675")
            self.thermocouple = MAX6675(config.gpio_sensor_cs,
                                     config.gpio_sensor_clock,
                                     config.gpio_sensor_data,
                                     config.temp_scale)

        if config.max31855:
            log.info("init MAX31855")
            self.thermocouple = MAX31855(config.gpio_sensor_cs,
                                     config.gpio_sensor_clock,
                                     config.gpio_sensor_data,
                                     config.temp_scale)

        if config.max31855spi:
            log.info("init MAX31855-spi")
            self.thermocouple = MAX31855SPI(spi_dev=SPI.SpiDev(port=0, device=config.spi_sensor_chip_id))

    def run(self):
        lasttemp = 0

        while True:
            try:
                self.temperature = self.thermocouple.get()
                lasttemp = self.temperature
            except Exception:
                self.temperature = lasttemp
                log.exception("problem reading temp")
            time.sleep(self.time_step)


class TempSensorSimulate(TempSensor):
    def __init__(self, oven, time_step, sleep_time):
        TempSensor.__init__(self, time_step)
        self.oven = oven
        self.sleep_time = sleep_time

    def run(self):
        t_env      = config.sim_t_env
        c_heat     = config.sim_c_heat
        c_oven     = config.sim_c_oven
        p_heat     = config.sim_p_heat
        R_o_nocool = config.sim_R_o_nocool
        R_o_cool   = config.sim_R_o_cool
        R_ho_noair = config.sim_R_ho_noair
        R_ho_air   = config.sim_R_ho_air

        t = t_env  # deg C  temp in oven
        t_h = t    # deg C temp of heat element
        while True:
            #heatOn energy
            Q_h = p_heat * self.time_step * self.oven.heat

            #temperature change of heat element by heatOn
            t_h += Q_h / c_heat

            if self.oven.air:
                R_ho = R_ho_air
            else:
                R_ho = R_ho_noair

            #energy flux heat_el -> oven
            p_ho = (t_h - t) / R_ho

            #temperature change of oven and heat el
            t   += p_ho * self.time_step / c_oven
            t_h -= p_ho * self.time_step / c_heat

            #energy flux oven -> env
            if self.oven.cool:
                p_env = (t - t_env) / R_o_cool
            else:
                p_env = (t - t_env) / R_o_nocool

            #temperature change of oven by cooling to env
            t -= p_env * self.time_step / c_oven
            log.debug("energy sim: -> %dW heater: %.0f -> %dW oven: %.0f -> %dW env" % (int(p_heat * self.oven.heat), t_h, int(p_ho), t, int(p_env)))
            self.temperature = t

            time.sleep(self.sleep_time)


class Profile():
    def __init__(self, json_data):
        obj = json.loads(json_data)
        self.name = obj["name"]

        #self.data is an array of 2-element arrays [time, temp]
        self.data = sorted(obj["data"])

        self.tempunit = obj["TempUnit"]
        self.timeunit = obj["TimeUnit"]
        log.debug(self.tempunit)
        log.debug(self.timeunit)

        #Convert these to seconds/Celsius
        tconv = 60 if (self.timeunit == "m") else 3600 if (self.timeunit == "h") else 1
        #self.data[:][0] = [i * tconv for i in self.data[:][0]]
        for dat in self.data:
            dat[0]=dat[0] * tconv
        if self.tempunit == "f":
            log.info("Converting from Farenheit")
            for dat in self.data:
                dat[1] = (dat[1] -32) / 1.8
            #self.data[:][1] = [(i - 32) / 1.8 for i in self.data[:][1]]
        #elif self.tempunit == "Kelvin": 	self.data[:][1] = [i - 273.15 for i in self.data[:][1]]
        self.targethit = [False] * len(self.data)

    def get_duration(self):
        return max([t for (t, x) in self.data])


    def get_surrounding_points(self, time):
        if time > self.get_duration():
            return (self.data[-1], None)
        elif time <= 0:
            return (None, self.data[0])

        prev_point = None
        next_point = None

        for i in range(len(self.data)):
            if time <= self.data[i][0]:         #if time is on a point, return point and one before it
                prev_point = self.data[i-1]
                next_point = self.data[i]
                break

        return (prev_point, next_point)

    def get_index_of_time(self, time):
        for i in range(len(self.data)):
            if time == self.data[i][0]:
                return i

        return None


    def is_rising(self, time):
        (prev_point, next_point) = self.get_surrounding_points(time)
        if prev_point and next_point:
            return prev_point[1] < next_point[1]
        else:
            return False

    ## findTemp - Returns the first time in the profile where the target temperature is
    ## equal to the input temperature
    def findTemp(self, temperature):
        if temperature < self.data[0][1]:
            return datetime.timedelta() #Start at the beginning
        elif temperature > max([x for (t, x) in self.data]):
            log.exception("Current temperature is higher than max profile point! Cannot resume.")
            return None
        else:
            for index in range(1, len(self.data)):
                if self.data[index][1] == temperature:
                    return datetime.timedelta(seconds = self.data[index][0])
                elif self.data[index][1] > temperature:
                    slope = (self.data[index][0] - self.data[index-1][0]) / (self.data[index][1] - self.data[index-1][1])
                    point = self.data[index-1][0] + slope * (temperature - self.data[index-1][1])
                    return datetime.timedelta(seconds = point)
                else:
                    continue


    def get_target_temperature(self, time, currtemp = 10000):

        (prev_point, next_point) = self.get_surrounding_points(time)
        index = self.get_index_of_time(prev_point[0])

        #The following algorithm does two things, intended for kiln firing:
            #1: Guarentees that the target temperature has been reached before continuing
            #2: Adjusts the target temperature in the event that the slope is less than expected
                #This adjustment is to maintain constant heat soaking

        #This is only enabled if must_hit_temp is set. Check if previous target has been hit already
        if config.must_hit_temp and not self.targethit[index]:

            if self.is_rising(prev_point[0]) and currtemp > (prev_point[1]-5):
                #If not, see if we just hit it now
                self.targethit[index] = True
            elif not self.is_rising(prev_point[0]):
                #if temperature was going down, don't worry about it
                self.targethit[index] = True

            else:
                #in this case, modify our profile to push the timing out
                delay = time - prev_point[0]

                (prev_prev_point, prev_point) = self.get_surrounding_points(prev_point[0])

                #Push the previous target and all future targets out in time
                for P in self.data[index:]:
                    P[0] = P[0] + delay

                #Reduce the target setpoint - only if this is the max point
                if self.data[index][1] >= max([x for (t, x) in self.data]):
                    #Determine original slope
                    #Determine new slope
                    oldslope = (prev_point[1] - prev_prev_point[1]) / (prev_point[0] - prev_prev_point[0])
                    newslope = (prev_point[1]-prev_prev_point[1]) / (prev_point[0]+delay-prev_prev_point[0])

                    #Calculation of new endpoint: old endpoint - change in slope(C/hr) * cone adj rate (C / (C/hr))
                    self.data[index][1]  = prev_point[1]- (config.cone_slope_adj*3600.0) * (oldslope-newslope)

                    log.debug("prev_prev_point: %.2f, %.2f, prev_point: %.2f, %.2f, old slope: %.8f, new slope: %.8f, index: %.0f",
                        prev_prev_point[0], prev_prev_point[1],
                        prev_point[0], prev_point[1],
                        oldslope, newslope, index)

                return self.data[index][1]

        if time > self.get_duration():
            return 0



        incl = float(next_point[1] - prev_point[1]) / float(next_point[0] - prev_point[0])
        if math.isnan(incl): incl = 0
        temp = prev_point[1] + (time - prev_point[0]) * incl
        return temp


class PID():
    def __init__(self, ki=1.0, kp=1.0, kd=1.0):
        self.ki = ki
        self.kp = kp
        self.kd = kd
        self.lastNow = datetime.datetime.now()
        self.iterm = 0.0
        self.lastErr = 0.0
        self.dErr = 0

    def reset(self):
        self.lastNow = datetime.datetime.now()
        self.iterm = 0
        self.lastErr = 0

    def compute(self, setpoint, ispoint):
        now = datetime.datetime.now()
        timeDelta = (now - self.lastNow).total_seconds()

        error = float(setpoint - ispoint)

        #Smooth out the dErr by running it through a simple filter
        self.dErr = (((error - self.lastErr) / timeDelta) + self.dErr) / 2
        if math.isnan(self.dErr): self.dErr = 0
        if self.kd != 0: self.dErr = sorted([-2/self.kd, self.dErr, 2/self.kd])[1]
        #Integral anti-windup: Only enable the integrator if the error is small enough
        if (self.kp * error + self.kd * self.dErr) < 5:
            self.iterm += (error * timeDelta * self.ki)
            self.iterm = sorted([0.0, self.iterm, 1.0])[1] #Keep iterm in control boundary


        output = self.kp * error + self.iterm + self.kd * self.dErr
        #output = sorted([-1, output, 1])[1] #allow values to exceed 100%
        self.lastErr = error
        self.lastNow = now

        return output
