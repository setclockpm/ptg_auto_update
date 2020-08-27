# based on a script from a data person working on the Iowa Coordinated Campaign

import csv
import datetime
import requests
import io
import itertools
import json
import pytz
import sys

# used for editing Google Sheets with Python
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import pprint

SECRETS_DIR = "./ptg_secrets"

with open("%s/ptg_secret_info" % (SECRETS_DIR), "r") as secrets_file:
	ORG_ID = secrets_file.readline().rstrip()
	MOBILIZE_API_KEY = secrets_file.readline().rstrip()

	# Name of Google Sheet you want to update
	GOOGLE_SHEET_NAME = secrets_file.readline().rstrip()

	# Names of tabs of the Google Sheet that you want to update
	EVENTS_TAB = secrets_file.readline().rstrip()
	ATTENDANCE_TAB = secrets_file.readline().rstrip()
	LAST_UPDATED_TAB = secrets_file.readline().rstrip()

	# Name of JSON containing credentials for editing the Google Sheet
	GOOGLE_SERVICE_CREDENTIALS_JSON = secrets_file.readline().rstrip()
	secrets_file.close()

# the date before which no events are pulled
START_YEAR = 2020
START_MONTH = 6
START_DAY = 1

# API URLs for retrieving data about events and attendance from Mobilize
EVENTS_URL = 'https://api.mobilize.us/v1/organizations/%s/events?visibility=PRIVATE&visibility=PUBLIC&timeslot_start=gte_%d'
ATTENDANCE_URL = 'https://api.mobilize.us/v1/organizations/%s/events/%s/attendances'


# JSON files in which data are stored locally before being uploaded to Google Sheets
TMP_EVENTS_JSON = '%s/tmp_events.json' % (SECRETS_DIR)
TMP_ATTENDANCE_JSON = '%s/tmp_attendance.json' % (SECRETS_DIR)

# change to True during development/testing and False during deployment
# USE_CACHED_EVENTS = True
USE_CACHED_EVENTS = False


# headers for the Google Sheets
EVENTS_HEADER = ["event_type", "contact_name", "owner_email", "event_id", "timeslot_id", "start_date", "end_date", "created_date"]
ATTENDANCE_HEADER = ["first_name", "last_name", "volunteer_id", "event_id", "timeslot_id", "start_date", "end_date", "contact_name","status", "attended", "modified_date", "created_date", "event_type"]

# used for editing the Google Sheets
ALPHABET = ["A","B","C","D","E","F","G","H","I","J","K","L","M","N","O","P","Q", "R","S","T","U","V", "W","X","Y","Z"]

# the timezone you want all your time data to be in
DEFAULT_TZ = pytz.timezone('America/Los_Angeles')

# the current time in the given timezone
AS_OF = pytz.utc.localize(datetime.datetime.utcnow()).astimezone(DEFAULT_TZ).strftime('%Y-%m-%d %H:%M:%S')



'''
take a date in UNIX, convert to the appropriate timezone, and return a version as a string
parameters:
	unix_date: a unix style timestamp
return:
	timestamp formatted as string
'''
def convert_date(unix_date):
    return pytz.utc.localize(
        datetime.datetime.utcfromtimestamp(unix_date)
    ).astimezone(DEFAULT_TZ).strftime('%Y-%m-%d %H:%M:%S')




'''
Get all events from Mobilize within a specific time period and download them into a JSON file
returns:
	events_data: formatted data about all of the events pulled from Mobilize
'''
def fetch_events_from_mobilize():

	# if USE_CACHED_EVENTS is set to TRUE, the program will read the JSON files stored locally instead of
	# trying to pull fresh information from Mobilize
	if USE_CACHED_EVENTS:
		try:
			with open(TMP_EVENTS_JSON, 'r') as f:
				return json.load(f)
		except FileNotFoundError:
			pass

	# take the EVENTS_URL and insert the relevant date information to limit the events returned
	next_url = EVENTS_URL % (
		ORG_ID,
		int(datetime.datetime(START_YEAR, START_MONTH, START_DAY).timestamp())
		)

	events_data = []

	# make the API calls
	while next_url:
		headers = { 'Authorization': f'Bearer {MOBILIZE_API_KEY}' }

		with requests.get(next_url, headers=headers) as r:
			r_json = r.json()
			events_data.extend(r_json['data'])
		next_url = r_json['next']

	# write the information to an external file
	with open(TMP_EVENTS_JSON, 'w') as tmp_json:
		json.dump(events_data, tmp_json, indent = 2)
	print("events_data array length: %s" % len(events_data))
	return events_data



'''
Read the information taken from Mobilize and extract the relevant fields. This helps limit the amount of data that
needs to be loaded into Google Sheets.
parameters:
	events_data: the JSON-style data from Mobilize
return:
	event_relevant_metrics: a list of lists contains all the relevant information about all the relevant events
'''
def extract_event_data(events_data):
	event_relevant_metrics = []
	for event in events_data:
		contact_name = ""
		contact_email = ""

		if not event['contact'] is None:
		    contact_name = event['contact']['name']
		    contact_email = event['contact']['email_address']

		event_id = event['id']
		event_type = event['event_type']
		created_date = event["created_date"]

		for timeslot in event["timeslots"]:
			chosen_metrics = []
			chosen_metrics.append(event_type)
			chosen_metrics.append(contact_name)
			chosen_metrics.append(contact_email)
			chosen_metrics.append(event_id)
			chosen_metrics.append((timeslot["id"]))
			chosen_metrics.append(convert_date(timeslot["start_date"]))
			chosen_metrics.append(convert_date(timeslot["end_date"]))
			chosen_metrics.append(convert_date(created_date))

			event_relevant_metrics.append(chosen_metrics)
	event_relevant_metrics.insert(0,EVENTS_HEADER) #not needed, duplicates headers
	return event_relevant_metrics

# EVENTS_HEADER
# ------------------------------------------------------------------------------------------------
# event_type, contact_name, owner_email, event_id, timeslot_id, start_date, end_date, created_date
# ------------------------------------------------------------------------------------------------

'''
Take the list of lists with info about events - write the data to a csv
parameters:
	event_relevant_metrics: list of lists containing data about events
'''
def write_events_to_csv(event_relevant_metrics):
	with open(f'events.csv', 'w', newline='') as csvfile:
		writer = csv.writer(csvfile, dialect='excel')
		writer.writerow(EVENTS_HEADER)
		for row in event_relevant_metrics:
			writer.writerow(row)





'''
Get attendance info from Mobilize for all events pulled previously
parameters:
	events_data: JSON style data from Mobilize about events
returns:
	attendance data: formatted data about all of the attendances pulled from Mobilize
'''
def fetch_attendance_from_mobilize(events_data):

	# if True, use local files rather than pulling fresh from Mobilize
	if USE_CACHED_EVENTS:
		try:
			with open(TMP_ATTENDANCE_JSON, 'r') as f:
				return json.load(f)
		except FileNotFoundError:
			pass

	attendance_data = []

	# Get the event_id for each event in events_data
	for event in events_data:
		event_id = event["id"]
		next_url = ATTENDANCE_URL % (ORG_ID, event_id)

		#make the API calls
		while next_url:
			headers = {
				'Authorization': f'Bearer {MOBILIZE_API_KEY}',
			}
			with requests.get(next_url, headers=headers) as r:
				r_json = r.json()
				attendance_data.extend(r_json['data'])
			print("next_url: %s" % r_json['next'])
			next_url = r_json['next']

		print("For event id: %s" % event_id)
		print(len(attendance_data))


	#write information to an external file
	with open(TMP_ATTENDANCE_JSON, 'w') as tmp_json:
		json.dump(attendance_data, tmp_json, indent = 2)

	return attendance_data

'''
Read the information taken from Mobilize and extract the relevant fields. This helps limit the amount of data that
needs to be loaded into Google Sheets.
parameters:
	attendance_data: the JSON-style data from Mobilize
return:
	attendance_relevant_metrics: a list of lists contains all the relevant information about attendance
'''
def extract_attendance_data(attendance_data):
	attendance_relevant_metrics = []
	for attendance in attendance_data:
		chosen_metrics = []
		chosen_metrics.append(attendance["person"]["given_name"])
		chosen_metrics.append(attendance["person"]["family_name"])
		chosen_metrics.append(attendance["person"]["user_id"])
		chosen_metrics.append(attendance["event"]["id"])
		chosen_metrics.append(attendance["timeslot"]["id"])
		chosen_metrics.append(convert_date(attendance['timeslot']["start_date"]))
		chosen_metrics.append(convert_date(attendance['timeslot']["end_date"]))
		if attendance["event"]['contact'] is None:
		    chosen_metrics.append("")
		else:
			chosen_metrics.append(attendance["event"]["contact"]["name"])
		chosen_metrics.append(attendance["status"])
		chosen_metrics.append(attendance["attended"])
		chosen_metrics.append(convert_date(attendance["modified_date"]))
		chosen_metrics.append(convert_date(attendance["created_date"]))
		chosen_metrics.append(attendance["event"]["event_type"])
		attendance_relevant_metrics.append(chosen_metrics)
	attendance_relevant_metrics.insert(0,ATTENDANCE_HEADER)
	return attendance_relevant_metrics





'''
Open the Google Sheet Events tab. Delete all existing data. Replace it with new events data
from Mobilize
parameters:
	event_relevant_metrics: list of lists of info about events
'''
def update_events(event_relevant_metrics):
	sheet = client.open(GOOGLE_SHEET_NAME).worksheet(EVENTS_TAB)

	# get all records from the tab
	data = sheet.get_all_records()
	rows = len(data)
	cols = len(EVENTS_HEADER)
	print(rows)
	print(cols)

	list_of_empty_string_lists = []

	# create a list of empty strings large enough to overwrite the old data
	for i in range(0,rows):
		empty_string_list = []
		for j in range(0,cols):
			empty_string_list.append("")
		list_of_empty_string_lists.append(empty_string_list)

	# overwrite the old data
	sheet.update('%s:%s' % (ALPHABET[0], ALPHABET[cols - 1])
		,list_of_empty_string_lists)

	rows = len(event_relevant_metrics)
	cols = len(event_relevant_metrics[0])
	print(event_relevant_metrics[0])

	print(rows)
	print(ALPHABET[0])
	print(ALPHABET[cols - 1])

	# write the new data
	sheet.update('%s:%s' % (ALPHABET[0], ALPHABET[cols - 1])
		,event_relevant_metrics)

'''
Open the Google Sheet Attendance tab. Delete all existing data. Replace it with new attendance data
from Mobilize

parameters:
	attendance_relevant_metrics: list of lists of info about attendance
'''
def update_attendance(attendance_relevant_metrics):
	sheet = client.open(GOOGLE_SHEET_NAME).worksheet(ATTENDANCE_TAB)

	data = sheet.get_all_records()
	rows = len(data)
	cols = len(ATTENDANCE_HEADER)
	print(rows)
	print(cols)

	list_of_empty_string_lists = []

	# create a list of empty strings large enough to overwrite the old data
	for i in range(0,rows):
		empty_string_list = []
		for j in range(0,cols):
			empty_string_list.append("")
		list_of_empty_string_lists.append(empty_string_list)

	# overwrite the old data
	sheet.update('%s:%s' % (ALPHABET[0], ALPHABET[cols - 1])
		,list_of_empty_string_lists)


	rows = len(attendance_relevant_metrics)
	cols = len(attendance_relevant_metrics[0])
	print(attendance_relevant_metrics[0])

	print(rows)
	print(ALPHABET[0])
	print(ALPHABET[cols - 1])

	# write the new data
	sheet.update('%s:%s' % (ALPHABET[0], ALPHABET[cols - 1])
		,attendance_relevant_metrics)


'''
Open the Google Sheet Last Updated tab. Write the current date/time
'''
def add_last_updated_at():
	sheet = client.open(GOOGLE_SHEET_NAME).worksheet(LAST_UPDATED_TAB)
	sheet.update("A2", AS_OF)
	print(AS_OF)




# Get the events data from Mobilize
events_data = fetch_events_from_mobilize()
# Put the relevant metrics into a list of lists
event_relevant_metrics = extract_event_data(events_data)
# Get the attendance data from Mobilize
attendance_data = fetch_attendance_from_mobilize(events_data)
# Put the relevant metrics into a list of lists
attendance_relevant_metrics = extract_attendance_data(attendance_data)

# Put the relevant metrics into a list of lists
write_events_to_csv(event_relevant_metrics)






# authorize this Python script to edit Google Sheets
scope = ['https://spreadsheets.google.com/feeds','https://www.googleapis.com/auth/drive']
creds = ServiceAccountCredentials.from_json_keyfile_name("%s/%s" % (SECRETS_DIR, GOOGLE_SERVICE_CREDENTIALS_JSON), scope)
client = gspread.authorize(creds)

# udpate the events tab of your Google Sheet
update_events(event_relevant_metrics)
# update the attendance tab of your Google Sheet
update_attendance(attendance_relevant_metrics)
# add information about when the Google Sheet was last updated
add_last_updated_at()
