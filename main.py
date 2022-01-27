import time
from selenium import webdriver
import selenium.common.exceptions as seleniumexceptions
import requests
import pickle
import datetime
import os
import csv
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy
import scipy.interpolate


class Thermostat:
    def __init__(self):
        lat = str(input("What is your latitude? "))
        long = str(input("What is your longitude? "))
        control_url = input("What is the AC control URL? ")
        csv_path = input("What is the CSV path? ")
        cd_path = input("What is the webdriver path? ")
        username = input("What is your username? ")
        password = input("What is your password? ")

        self.location = (lat, long)
        self.control_url = control_url
        self.csv_path = csv_path
        self.cd_path = cd_path

        self.credentials_file = "credentials.txt"

        with open(self.credentials_file, "wb") as f:
            credentials = {
                "username": username,
                "password": password,
            }
            pickle.dump(credentials, f)

    def login(self):
        driver = webdriver.Chrome(self.cd_path)
        driver.get(self.control_url)
        try:
            username_form = driver.find_element_by_name("usernameForm")
            password_form = driver.find_element_by_name("passwordForm")
        except seleniumexceptions.NoSuchElementException as e:
            print("The username and/or password forms could not be found.")
            raise e

        else:
            with open(self.credentials_file, "rb") as f:
                credentials = pickle.load(f)
                username_form.send_keys(
                    credentials["username"]
                )  # retrieves the username and password and inputs them
                password_form.send_keys(
                    credentials["password"]
                )  # retrieves the username and password and inputs them

            signin_button = driver.find_element_by_name("signin")
            signin_button.click()

        return driver

    def navigate_to_control(self):
        driver = self.login()

        ac = driver.find_element_by_xpath(
            "/html/body/div[3]/div[1]/div[3]/table/tbody/tr/td[1]/div[5]/div/table/tbody/tr/td/div/table/tbody/tr[2]/td/table/tbody/tr[1]/td[3]/a"
        )
        ac.click()

        driver.implicitly_wait(2)

        return driver

    def get_temperature(self):
        driver = self.navigate_to_control()

        temp = driver.find_element_by_xpath(
            '//*[@id="otherDevicesList"]/table/tbody/tr[1]/td/table/tbody/tr[1]/td[3]/a/span'
        ).text

        driver.quit()

        return temp

    def set_temperature(self, temp, mode):
        driver = self.navigate_to_control()

        driver.implicitly_wait(4)

        elem = driver.find_element_by_id("__icd_1_cf__")

        driver.switch_to.frame(elem)

        driver.implicitly_wait(4)

        menus = driver.find_elements_by_tag_name("select")

        temp_button = menus[0] if mode == "cool" else menus[1]

        temp_button.click()

        driver.implicitly_wait(1)

        temp_button.send_keys(temp)
        temp_button.click()

        mode_button = menus[2]
        mode_button.click()
        mode_button.send_keys(mode[0])
        mode_button.click()

        set_button = driver.find_element_by_xpath('//*[@id="action_button"]')
        set_button.click()

        driver.implicitly_wait(5)
        driver.quit()

        return f"The thermostat is now set to {temp}° in {mode} mode."

    def get_outside_past_week_temp(self):
        url = "https://api.openweathermap.org/data/2.5/onecall/timemachine"
        params = {
            "lat": self.location[0],
            "lon": self.location[1],
            "dt": int(
                (datetime.datetime.utcnow() - datetime.timedelta(days=5)).timestamp()
            ),
            "appid": "49a31051cc231d178b6576204c035598",
            "units": "imperial",
            "lang": "en",
        }

        dt_now = datetime.datetime.utcnow()

        temps = []

        for i in range(5, 0, -1):
            params["dt"] = int((dt_now - datetime.timedelta(days=i)).timestamp())
            r = requests.get(url, params=params)

            if r.status_code == 200:
                data = r.json()

                for hour in data["hourly"]:
                    dt_and_temp = {
                        "dt": datetime.datetime.fromtimestamp(hour["dt"]),
                        "temp": hour["temp"],
                    }
                    temps.append(dt_and_temp)
            else:
                print(r.json())
                raise Exception("Invalid request")

        return temps

    @staticmethod
    def parse_csv(file_name):
        temps = []

        fmt = "%m/%d/%y %I:%M %p"

        with open(file_name, newline="") as f:
            line_reader = csv.reader(f, delimiter=",", quotechar="|")

            for row in line_reader:
                if "reported" in row[1]:  # marks a temperature change
                    dt = datetime.datetime.strptime(row[0], fmt)

                    dt_now = datetime.datetime.now()

                    five_days_ago = (
                        dt_now
                        - datetime.timedelta(days=5)
                        - datetime.timedelta(hours=dt_now.hour)
                        - datetime.timedelta(minutes=dt_now.minute)
                        - datetime.timedelta(seconds=dt_now.second)
                        - datetime.timedelta(microseconds=dt_now.microsecond)
                    )

                    if dt >= five_days_ago:  # between five days ago and now
                        rounded_dt = dt.replace(
                            second=0, microsecond=0, minute=0, hour=dt.hour
                        ) + datetime.timedelta(
                            hours=dt.minute // 30
                        )  # rounds to the nearest hour

                        dt_and_temp = {
                            "dt": rounded_dt,
                            "temp": float(row[-3]),
                        }
                        temps.append(dt_and_temp)

            temps.reverse()

            final_temps = [temps[0]]
            previous_hour = temps[0]["dt"].hour
            # remove duplicates
            for i in range(len(temps[1:])):
                current_dt = temps[i]["dt"]
                current_hour = current_dt.hour
                if previous_hour != current_hour:
                    final_temps.append(temps[i])
                    previous_hour = current_hour

            return final_temps

    def get_inside_past_week_temp(self):
        driver = self.login()

        driver.implicitly_wait(2)

        driver.get(self.csv_path)
        try:
            csv_button = driver.find_element_by_xpath('//*[@id="csv_icon"]/canvas')
        except seleniumexceptions.NoSuchElementException as e:
            print("The CSV button could not be found.")
            raise e
        else:
            csv_button.click()

            time.sleep(5)

            os.chdir(DOWNLOADS_PATH)
            csv_file_name = sorted(os.listdir(os.getcwd()), key=os.path.getmtime)[-1]

            return self.parse_csv(csv_file_name)

    @staticmethod
    def fill_in_hours(data, start, end):
        """
        Returns a list of datetimes and temps that begin at the start datetime and end at the end datetime. Any gaps
        are filled by the average of the temperatures of the two nearest datetimes.
        """
        new_list = []

        # fill in beginning
        for i in range(len(data)):
            if i == 0:
                first = data[i]["dt"]

                if first > start:  # need to close the gap
                    difference = int(
                        (first - start).total_seconds() // 3600
                    )  # hours difference

                    for j in range(0, difference):
                        dt_and_temp = {
                            "dt": start + datetime.timedelta(hours=j),
                            "temp": data[i]["temp"],
                        }
                        new_list.append(dt_and_temp)
                new_list.append(data[i])

            else:
                prev_dt = new_list[-1]["dt"]
                current_dt = data[i]["dt"]

                # 1) datetime i is a duplicate to the last one in the new_list
                if current_dt == prev_dt:
                    continue

                # 2) datetime i is one beyond the last one in the new_list - just add it
                elif current_dt == prev_dt + datetime.timedelta(hours=1):
                    new_list.append(data[i])

                # 3) datetime i is two or more beyond the last one in the new_list - fill in at least one
                elif current_dt >= prev_dt + datetime.timedelta(hours=2):
                    avg_temp = 0.5 * (data[i]["temp"] + new_list[-1]["temp"])

                    while current_dt > prev_dt:
                        dt_and_temp = {
                            "dt": prev_dt + datetime.timedelta(hours=1),
                            "temp": avg_temp,
                        }
                        new_list.append(dt_and_temp)

                        prev_dt += datetime.timedelta(hours=1)

        # fill in at the end
        while new_list[-1]["dt"] < end:
            dt_and_temp = {
                "dt": new_list[-1]["dt"] + datetime.timedelta(hours=1),
                "temp": new_list[-1]["temp"],
            }
            new_list.append(dt_and_temp)

        duplicate_ix = []

        # final check for duplicates
        prev_dt = None
        for i in range(len(new_list)):
            if i == 0:
                prev_dt = new_list[i]["dt"]
            else:
                current_dt = new_list[i]["dt"]

                if prev_dt == current_dt:  # duplicate
                    duplicate_ix.append(i)

        final_list = [
            new_list[i] for i in range(len(new_list)) if i not in duplicate_ix
        ]  # eliminates duplicates

        return final_list

    def match_inside_and_outside_temps(self, inside, outside):
        # check every

        if inside[0]["dt"] < outside[0]["dt"]:
            start = inside[0]["dt"]
        else:
            start = outside[0]["dt"]

        if inside[-1]["dt"] > outside[-1]["dt"]:
            end = inside[-1]["dt"]
        else:
            end = outside[-1]["dt"]

        inside = self.fill_in_hours(inside, start, end)
        outside = self.fill_in_hours(outside, start, end)

        print("Inside")
        print(inside)
        print("Outside")
        print(outside)

        return inside, outside, start

    def plot_temps(self, initial_inside, initial_outside):
        inside, outside, start = self.match_inside_and_outside_temps(
            initial_inside, initial_outside
        )

        times_x = [i for i in range(len(initial_outside))]  # x-axis

        inside_temps_y = [
            datum["temp"] for datum in inside if datum["dt"] >= initial_outside[0]["dt"]
        ]
        outside_temps_y = [
            datum["temp"]
            for datum in outside
            if datum["dt"] >= initial_outside[0]["dt"]
        ]

        plt.plot(times_x, inside_temps_y, color="r")
        plt.plot(times_x, outside_temps_y, color="b")

        plt.xlabel(
            f"Hours After {initial_outside[0]['dt'].strftime(format='%m/%d/%y %I:%M %p')}"
        )
        plt.ylabel("Temperature (F)")
        plt.title("Inside and Outside Temperatures")

        red_icon = mpatches.Patch(color="r", label="Inside Temps")
        blue_icon = mpatches.Patch(color="b", label="Outside Temps")

        plt.legend(handles=[red_icon, blue_icon])

        inside_diff = numpy.diff(numpy.sign(numpy.diff(inside_temps_y)))
        outside_diff = numpy.diff(numpy.sign(numpy.diff(outside_temps_y)))

        xnew = numpy.linspace(numpy.array().min(), numpy.array().max(), 300)
        power_smooth = scipy.interpolate.spline(T, power, xnew)

        for i in range(len(inside_diff)):
            if abs(inside_diff[i]) != 0:
                plt.plot(i, inside_temps_y[i], "ro", color="orange")

        for i in range(len(outside_diff)):
            if abs(outside_diff[i]) != 0:
                plt.plot(i, outside_temps_y[i], "ro", color="purple")

        plt.show()

        self.analyze_temps(inside_temps_y, outside_temps_y, times_x)

    def analyze_temps(self, inside, outside, hours):
        pass
