Nemesis PI is a Fork or picoThermal which is a fork off of picoReflow by [apollo-ng]. It is intended to make it more 
versatile (suited for ceramic Pottery kilns) by adding several features:
Some Functions below are work in progress see config.py

Not Limited by stages and or programs ,you can have Thousands depending on PI4 models memory 4Gb or 8Gb
* Automatic PID tuning
* Time and temperature units defined per profile
* Added a High Limit Emergency shut off     Heating will be turned off and program stopped
* Added a Thermocouple Offset     adjust if needed to calibrate
* Removed CSV Logging MAKES IT SAFE NOT WRITING TO THE DISK! ACCESS LOGGING DATA IN TERMINAL CONTROLLER IS RUNNING IN only in manual mode or graph screen shot       will move to cloud. 
* Use the Live graph to help diagnose loose thermocouple connections and kiln issues such as relays and element wear over time. 
* Logging will be moved to online logging with the new app! Logging currently in manual mode in terminal when not auto booting controller.

26/8/20
* added 2 key press Stop Button option also setting up 2 and 3 zone removed simulate function still on single zone

29/11/20
* added Talking Kiln Controller update and bungs in terminal notification!
Change the .wav files with your voice just name them exactly as is.
This software Perfect for controlling a electric kiln and is works reliably with full remote control if needed via Phone ,Tablet or PC etc.. 
The added options make it suitable for a much wider range of thermal control.

26/01/21 added Hot Links to make getting Help and Firing Profiles for your Nemesis PI controller easier and added multi configs for easy copy and paste for Heat Treatment kilns as they do long holds at many different temperatures easy as copying and pasting config then restart controller to take effect quicker than having to constantly auto tuning kilns like simple PID controllers takes just 1 minute instead of some times hours like older controllers

Has error codes and will stop on errors for "safety" for max 31855k current driver supported module more coming soon very soon type k , n , r ,s ,j ,t, etc
NO connection     Thermocouple sensor break
Short to ground   Thermocouple short to ground     Grounding on metal case of kiln
Short to Vcc      Thermocouple picking up voltage from elements,old insulation or thermoouple close to elements small voltage can make errors in temperature readings.

Error Fault code 4 = Temperature reading 4 deg C means line fault or thermocouple board issue


Much much more coming soon all avaliable via updating 

Just keep your controller software updated ,come back from time to time to see the advancements we are making!!!

Use "simplescreenrecorder" from the app store in Linux to record your firing logs or if in manual mode copy and paste out of Terminal into speadshhet and save
Rememeber share and  email your friends your working firing programs great to help out the Noobs

Great for Glass kilns pottery kilns distilleries and the list goes on and on

Watch this Space!!!

Special thanks for the auto tune function implementation it just works!!!
cheers to 
Peter Thompson
Petronator
Also Special Thanks To JBruce12000 for all his hard work in many other areas of the programming making it a way better controller

Updates will be maintained for free by us and the community make it your own expand it!
Please send us a message to help make it better!

Step 1)
INSTALL KILN CONTROLLER
Copy lines below and paste in terminal press ,answer Y to any prompts and press Enter.

git clone https://github.com/Brett308/NemesisPI.git
sleep 2
sudo pip install ez-setup
sleep 2
sudo apt install libffi-dev
sleep 2
sudo pip3 install greenlet bottle gevent gevent-websocket
sleep 2
sudo apt-get install python3-pip python3-dev libevent-dev git -y
sleep 2
sudo apt install onboard -y
sudo su
update-alternatives --install /usr/bin/python python /usr/bin/python3 1

Thats it now you can start the controller see full manual other options SUCH AS REMOTE VIEWING

Step 2)
Manual Server Startup
Copy lines below and paste in terminal press enter 

cd NemesisPI
python picoreflowd.py

Then open web browser on the 
Nemesis PI and enter into address bar 127.0.0.1:8081 Press enter ,controller interface will load.refresh browser if not loaded correctly
OR GO TO FILE MANAGER home/pi/NemesisPI/NemesisPI double click icon then select execute

Step 3)
Once Autotuned then set up below
Autostart Server on Boot(do this after Auto Tuning Nemesis PI
If you want the server to autostart on boot, run the following commands

sudo nano /etc/rc.local

add the line:

`sudo python /home/pi/NemesisPI/picoreflowd.py &`

Add above line just above last exit at bottom of file once changed hold down Ctrl key + o to save then press enter then close terminal close Terminal and reboot Nemesis PI.

Step 4)Auto Tuning see videos and full manual on help page nemesispi.com.au


For more updated help see Nemesis Pi help page as things change in the operating system from time to time we 
update as fast as we can to make sure all is working

This quick install file can be found on our help page and manual page see full manual/Videos for AutoTuning
HAVE GOOD WIFI AND IF IT DOSNT WORK REDO ABOVE BUT IT WILL









