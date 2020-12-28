import requests
import os
import sys
import csv
import time
from datetime import datetime, timedelta
import json
from concurrent.futures import ThreadPoolExecutor, as_completed


def getAccessToken():
    try:
        with open("tokens.csv") as tokens_file:
            reader = csv.DictReader(tokens_file)
            for row in reader:
                if (int(row["expires_at"]) > time.time()):
                    print("Reusing existing token")
                    return row["access_token"]
                else:
                    try:
                        print("Fetching new token...")
                        r = requests.post("https://www.strava.com/oauth/token",
                            data = {
                                "client_id":os.environ["STRAVA_CLIENT_ID"],
                                "client_secret":os.environ["STRAVA_CLIENT_SECRET"],
                                "grant_type":"refresh_token",
                                "refresh_token":row["refresh_token"]
                            })
                        r.raise_for_status()
                        with open("tokens.csv", "w") as tokens_file:
                            writer = csv.writer(tokens_file, delimiter=",")
                            writer.writerow(["access_token","expires_at","refresh_token"])
                            writer.writerow([r.json()["access_token"],r.json()["expires_at"],r.json()["refresh_token"]])

                        return r.json()["access_token"] 
                    except requests.exceptions.RequestException as err:
                        raise SystemExit(err)
    except IOError:
        print('Could not find tokens.csv. Maybe you need to create one per the instructions in README')
        raise SystemExit()

def printProgressBar (iteration, total, finalMessage = 'Done!', printEnd = "\r"):
    iteration += 1
    if iteration == 1:
        time.perf_counter()
    percent = ("{0:.1f}").format(100 * (iteration / float(total)))
    filledLength = int(100 * iteration // total)
    bar = '█' * filledLength + '-' * (100 - filledLength)
    print(f'{iteration}/{total} |{bar}| {percent}%', end = printEnd)
    if iteration == total:
        elapsed = round(time.perf_counter(),1) 
        print(f'\n{finalMessage}\nFinished in {elapsed}s')

def parseStravaRateLimit(headers):
    maxPer15 = headers['X-RateLimit-Limit'].split(',')[0]
    maxPerDay = headers['X-RateLimit-Limit'].split(',')[1]
    usagePer15 = headers['X-RateLimit-Usage'].split(',')[0]
    usagePerDay = headers['X-RateLimit-Usage'].split(',')[1]
    print(f"\nERROR: Rate limit exceeded. \n  Used {usagePer15}/{maxPer15} max requests per 15 minutes\
    \n  Used {usagePerDay}/{maxPerDay} max requests per day\n")
    now = datetime.now()
    if int(usagePer15)>int(maxPer15):
        add_mins = 15 - (now.minute % 15)
        new_time = now + timedelta(minutes = add_mins)
        print("Try again at " + new_time.strftime('%-I:%M %p') + "\n")
    elif int(usagePerDay)>int(maxPerDay):
        print("Try again tomorrow\n")
    else: print("Try again later")
    raise SystemExit()

def run():
    token = getAccessToken()
    print("Fetching activities...")
    headers = {'Authorization': "Bearer {0}".format(token)}

    with open("walks.csv", "w") as walks_file:
        writer = csv.writer(walks_file, delimiter=",")
        writer.writerow(["id", "polyline"])

        page = 1
        output = "No activities returned"
        while True:  
            try:
                r = requests.get("https://www.strava.com/api/v3/athlete/activities?page={0}".format(page), headers = headers)
                r.raise_for_status
                if r.status_code == 429:
                    parseStravaRateLimit(r.headers)
                response = r.json()
                if len(response) == 0:
                    print(output)
                    break 
                else:
                    i = 0
                    total = len(response)
                    threads= []
                    with ThreadPoolExecutor(max_workers=10) as executor:
                        for activity in response:
                            threads.append(executor.submit(requests.get, "https://www.strava.com/api/v3/activities/{0}?include_all_efforts=true".format(activity["id"]), headers = headers))

                        for task in as_completed(threads):
                            r = task.result()
                            r.raise_for_status
                            if r.status_code == 429:
                                parseStravaRateLimit(r.headers)
                            polyline = r.json()["map"]["polyline"]
                            writer.writerow([activity["id"], polyline])
                            printProgressBar(i, total, f'Downloaded polylines for {total} activities on page {page}')
                            i += 1
                    page += 1
                    output = "Updated walks.csv with latest activities"
            except requests.exceptions.RequestException as err:
                raise SystemExit(err)

def updateWalksJS():
    walks = []
    with open("walks.csv", "r") as walks_file:
        reader = csv.DictReader(walks_file)

        for row in reader:
            walks.append(row["polyline"])

    with open('static/walks.js', 'w') as f:
        f.write('var walks = ' + json.dumps(walks))
    print('Updated walks.js')

if __name__ == '__main__':
    run()
    updateWalksJS()