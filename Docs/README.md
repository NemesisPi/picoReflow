Nemesis PI is a Fork or picoThermal which is a fork off of picoReflow by [apollo-ng]. It is intended to make it more 
versatile (suited for reflow oven or ceramic kiln) by adding several features:
Some Functions below are work in progress see config.py

* Ability to disable cooling, air, door sensor, etc.
* Handling of two separate heaters
* Automatic PID tuning
* Time and temperature units defined per profile
* Temperature PWM loop separated from control loop
* Option to wait for system to reach target temperature before going to next profile stage
* For ceramic kilns, dynamic calculation of end temperature based on heat rate

* High Limit Emergency shut off     Heating will be turned off and program stopped
* Thermocouple Offset     adjust if needed to calibrate experience people use only

This software Perfect for controlling a electric kiln and is works reliably. 
The added options make it suitable for a much wider range of thermal controllers. 
