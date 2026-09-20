import machine
import neopixel
import network
import urequests
import time

## Initial Variables
SSID = "tufts_eecs" #use tufts_eecs
PASSWORD = "foundedin1883" #foundedin1883

btn = machine.Pin(34, machine.Pin.IN, machine.Pin.PULL_UP)
DEBOUNCE_MS = 100
last_press = 0

TIME_URL = "http://api.timezonedb.com/v2.1/get-time-zone?key=3PGW072533EQ&format=json&by=zone&zone=America/New_York"
clock_mode = True
clock_last_press = 0
CLOCK_MS = 60_000
cur_time = None
time_synced = False

WEATHER_URL = "http://api.open-meteo.com/v1/forecast?latitude=42.425&longitude=-71.110&current=apparent_temperature,cloud_cover"
weather_last_press = 0
WEATHER_MS = 60_000
cur_weather = None

rtc = machine.RTC()

clock_fail = 0
weather_fail = 0
PRINT_MS = 10_000
last_print = 0

## Functions
def degree2servo(angle):
    # assume angle between 0 and 180
    angle = max(0, min(180, angle))
    ms_pulse = angle / 90 + 0.5
    duty = ms_pulse / 20 * 65535
    return int(duty)

def connect_wifi():
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    if not wlan.isconnected():
        print("Connecting to WiFi...")
        wlan.connect(SSID, PASSWORD)
        while not wlan.isconnected():
            time.sleep(0.5)
    print("Connected! IP address:", wlan.ifconfig()[0])
    return wlan

def button_handler(pin):
    global clock_mode, last_press
    now = time.ticks_ms()
    if time.ticks_diff(now, last_press) > DEBOUNCE_MS:
        last_press = now
        if (pin.value() == 0):
            clock_mode = not clock_mode

def clock_handler():
    global clock_last_press, time_synced, clock_fail
    now = time.ticks_ms()
    if time.ticks_diff(now, clock_last_press) < CLOCK_MS:
        return
    
    try:
        clock_last_press = now
        response = urequests.get(TIME_URL)
        clock_data = response.json()
        response.close()
    except Exception as e:
        print("time fetch failed:", type(e).__name__, e)
        clock_fail += 1
        return None

    if clock_data.get("status") != "OK":
        print("api error:", clock_data.get("message"))
        clock_fail += 1
        return None
    
    api = time.localtime(clock_data["timestamp"] - 946684800)
    rtc.datetime((api[0], api[1], api[2], api[6] + 1, api[3], api[4], api[5], 0))
    time_synced = True
    clock_fail = 0
    print("time synced %02d:%02d:%02d" % (api[3], api[4], api[5]))

def weather_handler():
    global weather_last_press, weather_fail
    now = time.ticks_ms()
    if time.ticks_diff(now, weather_last_press) < WEATHER_MS:
        return
    
    try:
        weather_last_press = now
        response = urequests.get(WEATHER_URL)
        weather_data = response.json()
        response.close()
    except Exception as e:
        print("weather fetch failed:", type(e).__name__, e)
        weather_fail += 1
        return None
    
    c = weather_data.get("current")
    if not c:
        print("no current block:", weather_data)
        weather_fail += 1
        return None
    
    weather_fail = 0
    print("weather synced")
    return weather_data["current"]["apparent_temperature"], weather_data["current"]["cloud_cover"]

## Setup
btn.irq(trigger=machine.Pin.IRQ_FALLING, handler=button_handler)
lights = neopixel.NeoPixel(machine.Pin(15),2)
hour_pwm = machine.PWM(machine.Pin(5),freq=50)
min_pwm = machine.PWM(machine.Pin(19),freq=50)
connect_wifi()
time.sleep(2)

## Run
while(True):
    now = time.ticks_ms()
    if clock_mode: # clock
        lights[0] = (50,50,50)
        clock_handler()
        if time_synced:
            tm = time.localtime()
            hour = tm[3] + tm[4] / 60 + tm[5] / 3600
            hour_pwm.duty_u16(degree2servo(hour / 24 * 180))
            minute = tm[4] + tm[5] / 60
            min_pwm.duty_u16(degree2servo(minute / 60 * 180))
    else: # alt mode
        lights[0] = (0,50,50)
        new_weather = weather_handler()
        if new_weather:
            cur_weather = new_weather
        if cur_weather is not None:
            fahrenheit = cur_weather[0] * 9 / 5 + 32
            hour_pwm.duty_u16(degree2servo(cur_weather[1] / 100 * 180))
            min_pwm.duty_u16(degree2servo(fahrenheit / 100 * 180))
            
    if clock_mode:
        has_data = time_synced
        fails = clock_fail
    else:
        has_data = cur_weather is not None
        fails = weather_fail

    if not has_data:
        lights[1] = (40, 0, 0)      # red: nothing to show in this mode
    elif fails:
        lights[1] = (40, 20, 0)     # amber: last fetch for this mode failed
    else:
        lights[1] = (0, 30, 0)      # green: current
    lights.write()
    
    if time.ticks_diff(now, last_print) >= PRINT_MS:
        last_print = now
        tm = time.localtime()
        if cur_weather is None:
            wx = "wx --"
        else:
            wx = "wx %.1fC/%.0fF  cloud %d%%" % (cur_weather[0], cur_weather[0] * 9 / 5 + 32, cur_weather[1])
        print("%02d:%02d:%02d  %-7s  %s  fails=%d" % (tm[3], tm[4], tm[5],"clock" if clock_mode else "weather",wx, fails))
    time.sleep_ms(20)
    
hour_pwm.deinit()
min_pwm.deinit()
    
