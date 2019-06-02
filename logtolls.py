#!/usr/bin/python3

import mysql.connector
import json, logging, pause, signal, sys, urllib.request
from datetime import datetime
from datetime import timedelta

# We want these as global variables, so we can reference them in the shutdown routine.
conn = None
curs = None

# We got a signal telling us to quit.
def handler (signum, frame):
    logging.info('received signal {}'.format(str(signum)))
    shutdown()

# We got a signal telling us to quit. Do a little housekeeping first.
def shutdown ():
    logging.info('shutting down')

    # If we've opened a cursor, try to close it.
    if curs != None:
        try:
            curs.close()
        except:
            # The cursor apparently wasn't actually open. No problem.
            pass

    # If we've connected to the database, try to close our connection.
    if conn != None:
        try:
            conn.close()
        except:
            # Apparently we don't actually have a connection to the database.
            # No problem.
            pass

    logging.info('shutdown complete')
    logging.shutdown()

    # That's it. Go ahead and exit.
    sys.exit()

def log_error (toll, curs):
    insertSQL = '''
        INSERT
          INTO error_log (error_log_date, ramp_on, ramp_off, error_text)
          VALUES (%(error_log_date)s, %(ramp_on)s, %(ramp_off)s, %(error_text)s)
    '''

    toll['error_log_date'] = datetime.now()
    toll['error_text'] = 'error %d - %s' % (toll['error'], toll['error_text'])

    try:
        curs.execute(insertSQL, toll)
    except Exception as e:
        logging.critical('insert into error_log failed: {}'.format(str(e)))
        shutdown()

# Get toll and time information for an on/off ramp pair. This also gets us status information
# for the reversible lanes when the trip defined by the ramps traverses those lanes.
def fetch_toll (trip):
    # The URL for the web API that gives us the data we want.
    url = 'https://www.expresslanes.com/maps-api/get-ramps-price?ramp_entry={ramp_on}&ramp_exit={ramp_off}'

    try:
        # Call the web API, and parse the JSON it returns.
        with urllib.request.urlopen(url.format(ramp_on=trip['ramp_on'], ramp_off=trip['ramp_off'])) as response:
            toll = json.loads(response.read().decode('utf-8'))

        # Make sure we have an error entry, and that it's an int.
        # An error of 0 just means no error.
        if toll.setdefault('error', None) == None: toll['error'] = 0
        toll['error'] = int(toll['error'])

        # Change a blank error_text to None.
        if toll.setdefault('error_text', None) == '': toll['error_text'] = None

        # Copy the on/off ramps of the trip into the data for the toll.
        toll['ramp_on'] = trip['ramp_on']
        toll['ramp_off'] = trip['ramp_off']

        # Did we get an error?
        if toll['error'] == 0:
            # No. Derive the direction of the trip; i.e. northbound or southbound.
            if trip['ramp_on'] > trip['ramp_off']:
                toll['direction'] = 'N'
            else:
                toll['direction'] = 'S'

            # Translate all empty strings in the response to None.
            if toll.setdefault('price_495', None) == '': toll['price_495'] = None
            if toll.setdefault('price_95', None) == '': toll['price_95'] = None
            if toll.setdefault('time_495', None) == '': toll['time_495'] = None
            if toll.setdefault('time_95', None) == '': toll['time_95'] = None
    except Exception as e:
        # We got an exception trying to get the toll. Oops. Save the data
        # about the trip and the exception so that the caller can log it.
        toll = {'error':-1, 'error_text':str(e), 'ramp_on':trip['ramp_on'], 'ramp_off':trip['ramp_off']}
        logging.warning('got exception trying to retrieve toll data: {}'.format(str(e)))

    return toll

# Figure out the status of the reversible lanes.
def fetch_reversible ():
    # Unless we hear otherwise, consider the reversible lanes closed.
    reversible = {'status_code':'C', 'error':0, 'error_text':None}

    # The on/off ramps to use when checking the status northbound and southbound.
    ramps = {'north':{'ramp_on':218, 'ramp_off':183}, 'south':{'ramp_on':183, 'ramp_off':218}}

    # Get the data for the northbound and southbound trips.
    north = fetch_toll(ramps['north'])
    south = fetch_toll(ramps['south'])

    if north['error'] != 0:
        # We got an error trying to fetch the northbound status.
        # Save the information to return to the caller.
        reversible['error'] = north['error']
        reversible['error_text'] = north['error_text']
        reversible['ramp_on'] = north['ramp_on']
        reversible['ramp_off'] = north['ramp_off']
    elif south['error'] != 0:
        # We got an error trying to fetch the southbound status.
        # Save the information to return to the caller.
        reversible['error'] = south['error']
        reversible['error_text'] = south['error_text']
        reversible['ramp_on'] = south['ramp_on']
        reversible['ramp_off'] = south['ramp_off']
    else:
        # Derive the status of the reversible lanes based on whether they're
        # reported as "open" for the northbound or southbound trip. If neither
        # we'll return the default of "C" (closed).
        if north['status_95'] == 'open':
            reversible['status_code'] = 'N'
        elif south['status_95'] == 'open':
            reversible['status_code'] = 'S'

    return reversible

# Log the toll record for a trip.
def log_toll(toll, curs):
    insertSQL = '''
        INSERT
          INTO toll_log (toll_start_date, toll_end_date, ramp_on, ramp_off, direction,
              price_495, price_95)
          VALUES (%(toll_start_date)s, %(toll_end_date)s, %(ramp_on)s, %(ramp_off)s, %(direction)s,
            %(price_495)s, %(price_95)s)
    '''

    updateSQL = '''
        UPDATE toll_log
          SET toll_end_date = %(toll_end_date)s
          WHERE toll_log_id = %(toll_log_id)s
    '''

    if 'toll_log_id' in toll:
        try:
            # We're updating an existing toll record, to extend the end data of the series.
            curs.execute(updateSQL, toll)
        except Exception as e:
            logging.critical('update of toll_log failed: {}'.format(str(e)))
            shutdown()

        toll_log_id = toll['toll_log_id']
    else:
        try:
            # We're creating an new toll record to create a new series of entries for a particular toll amount.
            curs.execute(insertSQL, toll)
            curs.execute('SELECT LAST_INSERT_ID()')
            toll_log_id = curs.fetchone()[0]
        except Exception as e:
            logging.critical('insert into toll_log failed: {}'.format(str(e)))
            shutdown()

    # Return the id of the new/updated toll record.
    return toll_log_id

def log_time(toll, curs):
    insertSQL = '''
        INSERT
          INTO time_log (time_start_date, time_end_date, ramp_on, ramp_off, direction,
              time_495, time_95)
          VALUES (%(time_start_date)s, %(time_end_date)s, %(ramp_on)s, %(ramp_off)s, %(direction)s,
            %(time_495)s, %(time_95)s)
    '''

    updateSQL = '''
        UPDATE time_log
          SET time_end_date = %(time_end_date)s
          WHERE time_log_id = %(time_log_id)s
    '''

    if 'time_log_id' in toll:
        try:
            curs.execute(updateSQL, toll)
        except Exception as e:
            logging.critical('update of time_log failed: {}'.format(str(e)))
            shutdown()

        time_log_id = toll['time_log_id']
    else:
        try:
            curs.execute(insertSQL, toll)
            curs.execute('SELECT LAST_INSERT_ID()')
            time_log_id = curs.fetchone()[0]
        except Exception as e:
            logging.critical('insert into time_log failed: {}'.format(str(e)))
            shutdown()

    return time_log_id

def log_reversible(reversible, curs):
    insertSQL = '''
        INSERT
          INTO reversible_log (reversible_start_date, reversible_end_date, status_code)
          VALUES (%(reversible_start_date)s, %(reversible_end_date)s, %(status_code)s)
    '''

    updateSQL = '''
        UPDATE reversible_log
          SET reversible_end_date = %(reversible_end_date)s,
            status_code = %(status_code)s
          WHERE reversible_log_id = %(reversible_log_id)s
    '''

    if 'reversible_log_id' in reversible:
        try:
            curs.execute(updateSQL, reversible)
        except Exception as e:
            logging.critical('update of reversible_log failed: {}'.format(str(e)))
            shutdown()

        reversible_log_id = reversible['reversible_log_id']
    else:
        try:
            curs.execute(insertSQL, reversible)
            curs.execute('SELECT LAST_INSERT_ID()')
            reversible_log_id = curs.fetchone()[0]
        except Exception as e:
            logging.critical('insert into reversible_log failed: {}'.format(str(e)))
            shutdown()

    return reversible_log_id

def log_trip_toll(trip, log_date, curs):
    current_toll = fetch_toll(trip)

    if current_toll['error'] == 0:
        # No error getting the toll data.

        # Check the tolls first.

        # Is this the first entry in a series of toll prices?
        if 'last' not in trip or trip['last']['price_495'] != current_toll['price_495'] \
          or trip['last']['price_95'] != current_toll['price_95']:
            # This is the first entry in a series of toll prices.
            current_toll['toll_start_date'] = log_date
        else:
            # This is the continuation of the current series of toll prices.
            current_toll['toll_start_date'] = trip['last']['toll_start_date']
            current_toll['toll_log_id'] = trip['last']['toll_log_id']

        # Now check the travel times.

        # Is this the first entry in a series of travel times?
        if 'last' not in trip or trip['last']['time_495'] != current_toll['time_495'] \
          or trip['last']['time_95'] != current_toll['time_95']:
            # This is the first entry in a series of travel times.
            current_toll['time_start_date'] = log_date
        else:
            # This is the continuation of the current series of travel times.
            current_toll['time_start_date'] = trip['last']['time_start_date']
            current_toll['time_log_id'] = trip['last']['time_log_id']

        # Until the next interval, the log time of this interval will be the end date of both series.
        current_toll['toll_end_date'] = log_date
        current_toll['time_end_date'] = log_date

        # Log this toll entry.
        current_toll['toll_log_id'] = log_toll(current_toll, curs)
        # And this time entry.
        current_toll['time_log_id'] = log_time(current_toll, curs)

        # Replace the trip's last toll entry.
        trip['last'] = current_toll
    else:
        logging.warning('could not get toll info for trip')
        # We couldn't get the toll data for whatever reason. Log the error.
        log_error(current_toll, curs)

        # Remove the data for the last toll from the trip. This will force a
        # new series of both price and travel time values.
        if 'last' in trip: del trip['last']

def log_reversible_status(reversible, log_date, curs):
    current_reversible = fetch_reversible()

    if current_reversible['error'] == 0:
        # No error getting the toll data.

        # Is this the first entry in a series of reversible lane statuses?
        if 'last' not in reversible or reversible['last']['status_code'] != current_reversible['status_code']:
            # This is the first entry in a series.
            current_reversible['reversible_start_date'] = log_date
        else:
            # This is the continuation of the current series of toll prices.
            current_reversible['reversible_start_date'] = reversible['last']['reversible_start_date']
            current_reversible['reversible_log_id'] = reversible['last']['reversible_log_id']

        # Until the next interval, the log time of this interval will be the end date of the series.
        current_reversible['reversible_end_date'] = log_date

        # Log this reversible lanes status entry.
        current_reversible['reversible_log_id'] = log_reversible(current_reversible, curs)

        reversible['last'] = current_reversible
    else:
        logging.warning('could not get status of reversible lanes')
        # We couldn't get the data for the reversible lanes, for whatever reason. Log the error.
        log_error(current_reversible, curs)
        # Remove the data for the last reversible lane status. This will force a new series.
        if 'last' in reversible: del reversible['last']

# The main body of the program.
def main():
    logging.basicConfig(format='%(asctime)s:%(levelname)s:%(message)s', \
	filename='/var/run/tollogger/tollogger.log', level=logging.INFO)
    logging.info('logger started')

    # Catch these signals, so we can shut down cleanly.
    signal.signal(signal.SIGHUP, handler)
    signal.signal(signal.SIGINT, handler)
    signal.signal(signal.SIGQUIT, handler)
    signal.signal(signal.SIGABRT, handler)
    signal.signal(signal.SIGFPE, handler)
    signal.signal(signal.SIGTERM, handler)
    signal.signal(signal.SIGTSTP, handler)

    try:
        # Get a connection to the database, and a cursor.
        conn = mysql.connector.connect(user='tollogger', database='tolls', autocommit=True)
        curs = conn.cursor()
        logging.info('connected to database')
    except Exception as e:
        logging.critical('database connection failed: {}'.format(str(e)))
        shutdown()

    # The trips we're going to track the tolls and time for.
    trips = [{'ramp_on':182, 'ramp_off':191}, {'ramp_on':191, 'ramp_off':182}]

    # Start with an empty dictionary for the reversible variable. This will
    # be used later to keep track of the last status received.
    reversible = {}

    while True:
        # To keep things simple, trucate the log date/time to the nearest minute.
        log_date = datetime.now().replace(second=0, microsecond=0)

        # Log the toll/time info for each of the trips we're interested in.
        for trip in trips:
            log_trip_toll(trip, log_date, curs)

        # Log the status of the reversible lanes.
        log_reversible_status(reversible, log_date, curs)

        # Check again when we get to the next minute.
        next_time = log_date + timedelta(minutes=1)
        pause.until(next_time)

if __name__ == '__main__':
    # This file is being run as a script, so execute the main body.
    main();
