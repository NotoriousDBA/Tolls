#!/usr/bin/python3

import json, pause, sys, threading, urllib.request
from datetime import datetime
from datetime import timedelta
from PIL import Image, ImageDraw, ImageFont, ImageTk
import tkinter as tk

def get_history (tolls, trip):
    toll_url = 'http://centralnode.local:5000/gettollprices/{:n}/{:n}/{:n}'
    toll_url = toll_url.format(trip['ramp_on'], trip['ramp_off'], trip['hist_minutes'])

    minute_delta = timedelta(minutes=1)
    last_period = datetime.now().replace(second=0, microsecond=0) - minute_delta
    min_date = datetime.now().replace(second=0, microsecond=0) - timedelta(minutes=trip['hist_minutes'])

    try:
        # Get all of the toll data for the specified trip for the last hist_minutes.
        with urllib.request.urlopen(toll_url) as response:
            tollhist = json.loads(response.read())

        for toll in tollhist:
            # Make sure the start/end dates are truncated to the nearest minute.
            start_date = datetime.strptime(toll['toll_start_date'], '%Y%m%d%H%M')
            end_date = datetime.strptime(toll['toll_end_date'], '%Y%m%d%H%M')
            price = float(toll['toll_price'])

            # Fill in the gaps between one set of toll pricing and another.
            while last_period - minute_delta > end_date:
                tolls.append(0)
                last_period -= minute_delta

            last_period = start_date

            # Backfill the toll price for the whole range from end to start.
            while end_date >= start_date:
                tolls.append(price)
                end_date -= minute_delta

        while last_period >= min_date:
            tolls.append(0)
            last_period -= minute_delta
    except:
        pass

def fetch_toll_data (trip):
    # The URL for the web API that gives us the data we want.
    url = 'https://www.expresslanes.com/maps-api/get-ramps-price?ramp_entry={ramp_on}&ramp_exit={ramp_off}'

    with urllib.request.urlopen(url.format(ramp_on=trip['ramp_on'], ramp_off=trip['ramp_off'])) as response:
        toll = json.loads(response.read())

    return toll

# Get toll and time information for an on/off ramp pair. This also gets us status information
# for the reversible lanes when the trip defined by the ramps traverses those lanes.
def fetch_toll (trip):
    # If we have an issue fetching the toll price, for whatever reason, we'll just return 0.
    toll_price = 0

    try:
        # Get the data from the web API.
        toll = fetch_toll_data(trip)

        # Did we get an error?
        if toll.setdefault('error', '0') in ('0', None, ''):
            # No. Calculate the total toll price and travel time.

            # Treat empty toll prices and travel times as zero.
            if toll.setdefault('price_495', '') in (None, ''): toll['price_495'] = 0
            if toll.setdefault('price_95', '') in (None, ''): toll['price_95'] = 0
            if toll.setdefault('time_495', '') in (None, ''): toll['time_495'] = 0
            if toll.setdefault('time_95', '') in (None, ''): toll['time_95'] = 0

            toll_price = toll['price_495'] + toll['price_95']
            trip['travel_time'] = toll['time_495'] + toll['time_95']
    except Exception as e:
        # Ignore any exceptions. We'll just return None for the toll price.
        pass

    return toll_price

def fetch_reversible_status (trip):
    # If we have an issue fetching the status of the reversible lanes, for whatever reason, we'll just return None.
    reversible_status = None

    try:
        toll = fetch_toll_data(trip)

        # Did we get an error?
        if toll.setdefault('error', '0') in ('0', None, ''):
            # No. Get the status of the reversible lanes.
            reversible_status = toll['status_95']
    except:
        # Ignore this exception. We'll just return None for the reversible status.
        pass

    return reversible_status

# Figure out the status of the reversible lanes.
def fetch_reversible ():
    # Unless we hear otherwise, consider the reversible lanes closed.
    reversible_status = 'C'

    # The on/off ramps to use when checking the status northbound and southbound.
    ramps = {'north':{'ramp_on':218, 'ramp_off':183}, 'south':{'ramp_on':183, 'ramp_off':218}}

    # Get the data for the northbound and southbound trips.
    north = fetch_reversible_status(ramps['north'])
    south = fetch_reversible_status(ramps['south'])

    if north != None and south != None:
        # Derive the status of the reversible lanes based on whether they're
        # reported as "open" for the northbound or southbound trip. If neither
        # we'll return the default of "C" (closed).
        if north == 'open':
            reversible_status = 'N'
        elif south == 'open':
            reversible_status = 'S'

    return reversible_status

def calc_toll_color(toll):
    low_toll = 10.0
    low_color = (0x2d, 0x82, 0x00)

    high_toll = 20.0
    high_color = (0xff, 0x00, 0x24)
    
    if toll <= low_toll:
        toll_color = low_color
    elif toll >= high_toll:
        toll_color = high_color
    else:
        gradient = (toll - low_toll)/(high_toll - low_toll)
        toll_red = low_color[0] + int((high_color[0] - low_color[0]) * gradient)
        toll_green = low_color[1] + int((high_color[1] - low_color[1]) * gradient)
        toll_blue = low_color[2] + int((high_color[2] - low_color[2]) * gradient)
        toll_color = (toll_red, toll_green, toll_blue)

    return toll_color

def get_toll_display(check_time, trip, tolls, reversible, display_size, fonts):
    # Colors for our display.
    background_color = (0x34, 0x34, 0x34)
    graph_color = (0x8c, 0x13, 0x1a)
    text_color = (0x8b, 0x8b, 0x8b)

    # Calculate the initial dimensions of our image.

    # One pixel of width per toll entry.
    width = len(tolls) - 1

    # One pixel per nickel of the maximum price in the list.
    max_price_pixels = int(max(tolls) * 100 / 5);

    # We want the maximum price to reach one third of the way to the top of the display.
    height = max_price_pixels * 3

    # Create the image for the display, and get a drawing context for it.
    display = Image.new('RGB', (width, height), color=background_color)
    draw = ImageDraw.Draw(display)

    # We're graphing the tolls left to right, oldest to most recent,
    # so initialize the toll index to the oldest toll.
    toll_index = len(tolls)

    # Graph the toll prices onto the image from left to right.
    for index in range(width + 1):
        toll_index -= 1

        # Skip over entries where we don't have price data.
        if tolls[toll_index] == 0: continue

        # Calculate the start/stop coordinates of the line.
        startx = index
        starty = height - int(tolls[toll_index] * 100 / 5)
        stopx = index
        stopy = height

        draw.line((startx, starty, stopx, stopy), fill=graph_color, width=1)

    # Resize the display to its final dimensions.
    display = display.resize(display_size, Image.BICUBIC)
    # After the resize we need a new drawing context.
    draw = ImageDraw.Draw(display)

    day_text = check_time.strftime('%A %m/%d/%Y')
    time_text = check_time.strftime('%I:%M %p')

    #
    # Write all of the text onto the display image.
    #

    # Use this height as the margin.
    margin = fonts['day_height']

    # Put the day and date centered at the top.
    (width, height) = draw.textsize(day_text, font=fonts['day'])
    draw.text(((display_size[0] - width)/2, margin), day_text, fill=text_color, font=fonts['day'])

    # The ramp where the trip starts.
    (width, height) = draw.textsize('From: ', font=fonts['label'])
    anchor = (margin + width, display_size[1]/6)
    draw.text((margin, anchor[1] - fonts['label_height']), 'From: ', fill=text_color, font=fonts['label'])
    draw.text((anchor[0], anchor[1] - fonts['trip_height']), trip['ramp_on_name'], fill=text_color, font=fonts['trip'])

    # The ramp where the trip ends.
    (width, height) = draw.textsize('To: ', font=fonts['label'])
    draw.text((anchor[0] - width, anchor[1]), 'To: ', fill=text_color, font=fonts['label'])
    anchor = (anchor[0], anchor[1] + fonts['label_height'] - fonts['trip_height'])
    draw.text((anchor[0], anchor[1]), trip['ramp_off_name'], fill=text_color, font=fonts['trip'])

    # The highest and lowest tolls in the last X minutes.
    high_toll_text = 'High: ${:.2f}'.format(max(tolls))
    low_toll_text = 'Low: ${:.2f}'.format(min(filter(lambda x: x > 0, tolls)))
    anchor = (margin, anchor[1] + fonts['trip_height'] + margin)
    draw.text((anchor[0], anchor[1]), high_toll_text, fill=text_color, font=fonts['trip'])
    draw.text((anchor[0], anchor[1] + fonts['trip_height'] + margin/2), \
        low_toll_text, fill=text_color, font=fonts['trip'])

    # The status of the reversible lanes.
    reversible_text = 'I95 '
    if reversible == 'N':
        reversible_text += 'Open Northbound'
    elif reversible == 'S':
        reversible_text += 'Open Southbound'
    else:
        reversible_text += 'Closed'

    anchor = (margin, anchor[1] + fonts['trip_height']*2 + margin*2)
    draw.text((anchor[0], anchor[1]), reversible_text, fill=text_color, font=fonts['trip'])

    # The current toll.
    toll_text = '${:.2f}'.format(tolls[0])
    (width, height) = draw.textsize(toll_text, font=fonts['toll'])
    anchor = (display_size[0] - margin, fonts['toll_height'])
    draw.text((anchor[0] - width, (display_size[1]/2) - anchor[1] + margin), \
        toll_text, fill=calc_toll_color(tolls[0]), font=fonts['toll'])

    # The current time.
    (width, height) = draw.textsize(time_text, font=fonts['label'])
    draw.text((anchor[0] - width, (display_size[1]/2) - anchor[1] - fonts['label_height'] + margin), \
        time_text, fill=text_color, font=fonts['label'])

    # The current travel time.
    travel_text = 'Travel Time {:n} Minutes'.format(trip['travel_time'])
    (width, height) = draw.textsize(travel_text, font=fonts['trip'])
    draw.text((anchor[0] - width, (display_size[1]/2) + (margin * 2)), \
        travel_text, fill=text_color, font=fonts['trip'])

    # Return the display image.
    return ImageTk.PhotoImage(image=display)

def font_heights(fonts):
    # We need an image and a drawing context to find the font heights.
    junkimg = Image.new('RGB', (800, 480), color=(0x00, 0x00, 0x00))
    junkdraw = ImageDraw.Draw(junkimg)

    # Find the height of each font.
    for font_name in list(fonts.keys()):
        (width, fonts[font_name + '_height']) = junkdraw.textsize('X', font=fonts[font_name])

def get_fonts():
    fonts = {}

    fonts['day'] = ImageFont.truetype(font='Ubuntu-R', size=22)
    fonts['label'] = ImageFont.truetype(font='Ubuntu-R', size=42)
    fonts['trip'] = ImageFont.truetype(font='Ubuntu-R', size=24)
    fonts['time'] = ImageFont.truetype(font='Ubuntu-R', size=24)
    fonts['toll'] = ImageFont.truetype(font='Ubuntu-B', size=140)

    # Find the "absolute" height for each font.
    font_heights(fonts)

    return fonts

# The main body of the program.
def update_display(toll_label):
    # Load the fonts we're going to use in the display.
    fonts = get_fonts()

    # The trip we're going to track the tolls and time for.
    trip = {'ramp_on':182, 'ramp_off':191,
            'ramp_on_name':'Route 267',
            'ramp_off_name':'Springfield Interchange'}

    minute_delta = timedelta(minutes=1)

    # The list of tolls over time.
    tolls = []

    # We want to show the minute by minute history of toll prices over the last 12 hours.
    hist_minutes = 720

    # Calculate the earliest date we want to fetch toll prices for.
    trip['hist_minutes'] = hist_minutes

    # Initialize our tolls dataset by fetching the toll data for the last hist_minutes minutes.
    get_history(tolls, trip)

    # Now that we have the history of the toll price, check the toll price every minute going forward.
    while True:
        # To keep things simple, truncate the current date/time to the nearest minute.
        check_time = datetime.now().replace(second=0, microsecond=0)

        # Get the current toll and the status of the reversible lanes on 95.
        toll = fetch_toll(trip)
        reversible = fetch_reversible()

        # Add this toll price to the beginning of our list, dropping off the oldest price.
        tolls = [toll] + tolls[0:(hist_minutes + 1)]

        # Paint the toll display.

        # Get the new image.
        toll_display = get_toll_display(check_time, trip, tolls, reversible, DISPLAY_SIZE, fonts)
        # Update the label used to display it with the new image.
        toll_label.configure(image=toll_display)
        toll_label.image = toll_display

        # Check again when we get to the next minute.
        pause.until(check_time + minute_delta)

if __name__ == '__main__':
    DISPLAY_SIZE = (800, 480)

    root = tk.Tk()

    # Initialize the display to a properly-sized blank image.
    im = ImageTk.PhotoImage(image=Image.new('RGB', DISPLAY_SIZE, (0, 0, 0)))

    # Create the label used to display the image.
    toll_label = tk.Label(root, image=im)
    toll_label.pack()

    # Spin off a thread to update the display once a minute.
    updater = threading.Thread(target=update_display, args=(toll_label,))
    updater.start()

    # Start the app.
    root.mainloop()
