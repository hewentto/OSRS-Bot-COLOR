import datetime
import time
from tkinter import *
import cv2
from model.osrs.osrs_bot import OSRSBot
import utilities.color as clr
from utilities.geometry import Rectangle, RuneLiteObject, Point
import utilities.random_util as rd
from utilities.api.morg_http_client import MorgHTTPSocket
from utilities.api.status_socket import StatusSocket
import utilities.imagesearch as imsearch
import random
import pyautogui as pag
import threading
from abc import ABCMeta, abstractmethod
from pathlib import Path
import utilities.game_launcher as launcher
from typing import Union, List
import utilities.ocr as ocr
from .Users import User


# New class WillowsDad_bot
class WillowsDadBot(OSRSBot, launcher.Launchable, metaclass=ABCMeta):
    """Willows Dad Bot class."""

    # Update the BOT_IMAGES path
    WILLOWSDAD_IMAGES = Path(__file__).parent.joinpath("WillowsDad_images")

    def __init__(self, bot_title, description) -> None:
        super().__init__(bot_title, description)
        self.take_birdhouse_breaks = False
        self.birdhouse = None


    def create_options(self):
        self.options_builder.add_slider_option("running_time", "How long to run (minutes)?", 1, 360)
        self.options_builder.add_checkbox_option("afk_train", "Train like you're afk on another tab?", [" "])
        self.options_builder.add_checkbox_option("take_breaks", "Take breaks?", [" "])
        self.options_builder.add_slider_option("delay_min", "How long to take between actions (min) (MiliSeconds)?", 300,1200)
        self.options_builder.add_slider_option("delay_max", "How long to take between actions (max) (MiliSeconds)?", 350,1200)


    def save_options(self, options: dict):
        for option in options:
            if option == "running_time":
                self.running_time = options[option]
            elif option == "take_breaks":
                self.take_breaks = options[option] != []
            elif option == "afk_train":
                self.afk_train = options[option] != []
            elif option == "delay_min":
                self.delay_min = options[option]/1000
            elif option == "delay_max":
                self.delay_max = options[option]/1000


    def launch_game(self):
    
        # If playing RSPS, change `RuneLite` to the name of your game
        if launcher.is_program_running("RuneLite"):
            self.log_msg("RuneLite is already running. Please close it and try again.")
            return
        
        settings = Path(__file__).parent.joinpath("WillowsDad.properties")
        launcher.launch_runelite(
            properties_path=settings, 
            game_title=self.game_title, 
            use_profile_manager=True, 
            profile_name="WillowsDad", 
            callback=self.log_msg)


    def setup(self):
        """Sets up loop variables, checks for required items, and checks location.
        This will ideally stop the bot from running if it's not setup correctly.
        * To-do: Add functions to check for required items, bank setup and locaiton.
        Args:
            None
        Returns:
            None"""
        self.start_time = time.time()
        self.end_time = self.running_time * 60
        self.is_focused = self.is_runelite_focused()
        self.roll_chance_passed = False
        self.last_progress = 0
        self.breaks_skipped = 0
        self.last_break = time.time()
        self.multiplier = 1
        self.loop_count = 0
        self.api_m = MorgHTTPSocket()
        self.api_s = StatusSocket()
        self.spec_energy = self.get_special_energy()
        self.last_runtime = 0
        self.safety_squares = self.get_all_tagged_in_rect(self.win.game_view ,clr.CYAN)
        self.deposit_all_red_button = None
        self.exit_btn = None

        if self.take_birdhouse_breaks:
            self.user = User()
            self.next_birdhouse_break = time.time()



    def is_runelite_focused(self):
        """
        This will check if the runelite window is focused.
        Returns: boolean
        Args: None
        """
        # Get the currently focused window
        current_window = pag.getActiveWindow()

        # Check if the window title contains a certain keyword (e.g. "Google Chrome")
        if current_window is None:
            return False
        if "runelite" in current_window.title.lower():
            self.is_focused = True
            return True
        else:
            self.is_focused = False
            return False


    def activate_special(self):
        """Activates the special attack of the equipped weapon.
            Args:
                None
            Returns:
                None"""
        self.mouse.move_to(self.win.spec_orb.random_point())
        self.mouse.click()
        time.sleep(self.random_sleep_length())



    def sleep(self, percentage):
        """Sleeps for a random amount of time between the min and max delay. While player is doing an action.
            Args:
                None
            Returns:
                None"""
        self.breaks_skipped = 0
        afk_time = 0
        afk__start_time = time.time() 

        while not self.api_m.get_is_player_idle():
            time.sleep(self.random_sleep_length(.35, .85))
            afk_time = int(time.time() - afk__start_time)
            self.is_runelite_focused()
            self.breaks_skipped = afk_time // 15

        if self.breaks_skipped > 0:
            self.roll_chance_passed = True
            self.multiplier += self.breaks_skipped * .25
            self.log_msg(f"Skipped {self.breaks_skipped} break rolls while afk, percentage chance is now {round((self.multiplier * .01) * 100)}%")


    def random_sleep_length(self, delay_min=0, delay_max=0):
        """Returns a random float between min and max"""
        if delay_min == 0:
            delay_min = self.delay_min
        if delay_max == 0:
            delay_max = self.delay_max
        return rd.fancy_normal_sample(delay_min, delay_max)
    
    def switch_window(self):
        """
        This will switch the window to runelite.
        Returns: void
        Args: None
        """
        # Get the currently focused window
        old_window = pag.getActiveWindow()

        pag.hotkey("alt", "tab")
        new_window = pag.getActiveWindow()

        self.log_msg(f"Switched to window: {new_window.title}.")

        self.is_focused = "RuneLite" in new_window.title
        if old_window.title == new_window.title:
            self.log_msg("Window not switched, something is wrong, quitting bot.")
            self.stop()

        time.sleep(self.random_sleep_length())


    def check_for_level_up(self, img: Path):
        """Checks if the player has leveled up. By looking for image in chat
            Args:
                img: Path
            Returns:
                boolean"""
        return bool(found := imsearch.search_img_in_rect(img, self.win.chat))


    def check_break(self, runtime, percentage, minutes_since_last_break, seconds):
        """
        This will roll the chance of a break.
        Returns: void
        Args:
            runtime: int
            percentage: float
            minutes_since_last_break: int
            seconds: int
            deposit_slots: list
            self.roll_chance_passed: boolean"""
        if runtime % 15 == 0 and runtime != self.last_runtime:
            if runtime % 60 == 0:   # every minute log the chance of a break
                self.log_msg(f"Chance of random break is {round(percentage * 100)}%")

            self.roll_break(
                percentage, minutes_since_last_break, seconds
            )

        elif self.roll_chance_passed:
            self.log_msg(f"Chance of random break is {round(percentage * 100)}%")

            self.roll_break(
                percentage, minutes_since_last_break, seconds
            )
        self.last_runtime = runtime



    def roll_break(self, percentage, minutes_since_last_break, seconds):
        if (
            rd.random_chance(probability=percentage / (1 if self.afk_train else 4))   # when afk theres weird timing issues so we divide by 4 if not afk
            and self.take_breaks
        ):
            self.reset_timer(
                minutes_since_last_break, seconds, percentage
            )
        self.multiplier += .25  # increase multiplier for chance of random break, we want + 1% every minute 
        self.roll_chance_passed = False


    def check_deposit_all(self):
        """
        This will check if deposit all png is found, and select all if not.
        """
        # if we've already searched and found, return
        if self.deposit_all_red_button:
            return
        # get the path of deposit_all_grey.png and red
        deposit_all_grey = self.WILLOWSDAD_IMAGES.joinpath("deposit_all_grey.png")
        deposit_all_red = self.WILLOWSDAD_IMAGES.joinpath("deposit_all_red.png")

        # if we find deposit all red in game view, return, else, find grey and click
        time_searching = time.time()
        while True:
            self.deposit_all_red_button = imsearch.search_img_in_rect(
                deposit_all_red, self.win.game_view.scale(scale_height=.2, anchor_y=.8)
            )
            if self.deposit_all_red_button:
                return   # We found deposit all is already selected, return.
            # We now check several times within 1 second for deposit all grey, if we find it, click it and return.
            elif deposit_all_grey_button := imsearch.search_img_in_rect(
                deposit_all_grey, self.win.game_view.scale(scale_height=.2, anchor_y=.8)
            ):
                self.mouse.move_to(deposit_all_grey_button.random_point())
                self.mouse.click()
                return
            if time.time() - time_searching > 1:
                self.log_msg("Could not verifty deposit all settings, double check those.")
                return
            time.sleep(.2)


    def check_deposit_5(self):
        """
        This will check if deposit 5 png is found, and select all if not.
        """

        # get the path of deposit_all_grey.png and red
        deposit_5_grey = self.WILLOWSDAD_IMAGES.joinpath("deposit_5_grey.png")
        deposit_5_red = self.WILLOWSDAD_IMAGES.joinpath("deposit_5_red.png")

        # if we find deposit 5 red in game view, return, else, find grey and click
        time_searching = time.time()
        while True:
            self.deposit_all_red_button = imsearch.search_img_in_rect(
                deposit_5_red, self.win.game_view.scale(scale_height=.2, anchor_y=.8)
            )
            if self.deposit_all_red_button:
                return   # We found deposit all is already selected, return.
            # We now check several times within 1 second for deposit all grey, if we find it, click it and return.
            elif deposit_all_grey_button := imsearch.search_img_in_rect(
                deposit_5_grey, self.win.game_view.scale(scale_height=.2, anchor_y=.8)
            ):
                self.mouse.move_to(deposit_all_grey_button.random_point())
                self.mouse.click()
                return
            if time.time() - time_searching > 1:
                self.log_msg("Could not verifty deposit all settings, double check those.")
                return
            time.sleep(.2)

        
    def reset_timer(self, minutes_since_last_break, seconds, percentage):
        self.log_msg(f"Break time, last break was {minutes_since_last_break} minutes and {seconds} seconds ago. \n Chance of random break was {round(percentage * 100)}%")

        self.last_break = time.time()   # reset last break time
        self.multiplier = 1    # reset multiplier

        self.take_random_break(minutes_since_last_break)


    def take_menu_break(self):
        """
        This will take a random menu break [Skills, Combat].]
        Returns: void
        Args: None
        """
        # random amount of seconds to teak a break
        break_time = random.uniform(1, 15)

        if rd.random_chance(.7):
            self.log_msg("Taking a tab break...")
            self.mouse.move_to(self.win.cp_tabs[int(rd.fancy_normal_sample(0, 6))].random_point())
            time.sleep(self.random_sleep_length())
            self.mouse.click()
            self.mouse.move_to(self.win.control_panel.random_point())
            time.sleep(break_time)

            # go back to inventory
            self.mouse.move_to(self.win.cp_tabs[3].random_point())
            time.sleep(self.random_sleep_length())
            self.mouse.click()
        return
    

    def take_random_break(self, minutes_since_last_break):
        """This will randomly choose a break type and take it. The shorter time since last break, the more likely it is to be a menu break.
        Returns: void
        Args: minutes_since_last_break (int) - the number of minutes passed since the last break."""
        # break type is a random choice from list
        break_type = random.choice(["menu", "menu","menu" "break"])

        if break_type == "menu":
            self.take_menu_break()

        if break_type == "break":
            self.log_msg("Taking a break...")

            if minutes_since_last_break > 25:
                self.take_break(15, 120)
            else:
                self.take_break(3,8)


    def switch_account(self):
        """
        Logs out and signs back in with a new account.
        Returns: void
        Args: None
        """
        new_user = self.user2 if self.current_user == self.user1 else self.user1
        self.logout()

        # if its after 10pm, sleep for 5-7 hours
        if datetime.datetime.now().hour >= 23:
            self.log_msg("Sleeping for 5-7 hours...")
            time.sleep(random.uniform(18000, 25200))

        # 20% chance to sleep for 20seconds to 10 minutes
        if rd.random_chance(.187):
            self.log_msg("Sleeping for a while...")
            time.sleep(random.uniform(20, 600))

        else: 
            time.sleep(self.random_sleep_length() * 3)

        if existing_user := imsearch.search_img_in_rect(
            self.WILLOWSDAD_IMAGES.joinpath("existing_user.png"),
            self.win.game_view,
        ):
            self.mouse.move_to(existing_user.random_point())
            self.mouse.click()
            time.sleep(self.random_sleep_length() / 2)

        # press tab to go to username field
        pag.press('tab')

        # hold backspace to delete current username
        for _ in range(len(self.current_user[0])):  # adjust the range as needed
            pag.press('backspace')
            time.sleep(self.random_sleep_length() / 3)

        # type in new username
        pag.write(new_user[0], interval=self.random_sleep_length() / 3)

        # press tab to go to password field
        pag.press('tab')

        # type in new password
        pag.write(new_user[1], interval=self.random_sleep_length() / 3)

        # press enter to login
        pag.press('enter')

        # wait for login
        time.sleep(self.random_sleep_length(8,12))
        if click_to_play := imsearch.search_img_in_rect(self.WILLOWSDAD_IMAGES.joinpath("click_to_play.png"), self.win.rectangle()):
            self.mouse.move_to(click_to_play.random_point())
            self.mouse.click()
        else:
            self.log_msg("Could not find click to play button, double check login.")
            self.stop()
        self.current_user = new_user
        time.sleep(self.random_sleep_length(1.5,2.5))
        return


    def sign_in(self):
        """Will sign in to the game form the "existing user or new user" screen. It is up to you to 
        wait for the login to complete."""

        existing_user = self.wait_until_img(self.WILLOWSDAD_IMAGES.joinpath("existing_user2.png"), self.win.rectangle())

        self.mouse.move_to(existing_user.random_point())
        self.mouse.click()

        time.sleep(self.random_sleep_length())
        # type in password
        pag.write(self.password, interval=self.random_sleep_length() / 3)

        # press enter to login
        pag.press('enter')

        # get the current time as the start time
        start_time = time.time()

        click_to_play = self.wait_until_img(self.WILLOWSDAD_IMAGES.joinpath("click_to_play.png"), self.win.rectangle())
        self.mouse.move_to(click_to_play.random_point())
        self.mouse.click()

        return


    def is_inv_empty(self):
        """
        Checks if inventory is empty.
        Returns: bool
        """
        for i in range(len(self.win.inventory_slots)):
            slot_location = self.win.inventory_slots[i].scale(.5,.5)
            slot_img = imsearch.BOT_IMAGES.joinpath(self.WILLOWSDAD_IMAGES, "emptyslot.png")
            if slot := imsearch.search_img_in_rect(slot_img, slot_location):
                continue
            return False
        return True
    

    def get_first_occurence(self, img_path:Path):
        """Returns the first occurence of an image in the inventory."""
        for slot in self.win.inventory_slots:
            if found := imsearch.search_img_in_rect(img_path, slot, confidence=.9):
                return slot
        return None


    def is_inv_full(self):
        """
        Checks if inventory is full.
        Returns: bool
        """
        for i in range(len(self.win.inventory_slots)):
            slot_location = self.win.inventory_slots[i].scale(.5,.5)
            slot_img = imsearch.BOT_IMAGES.joinpath(self.WILLOWSDAD_IMAGES, "emptyslot.png")
            if slot := imsearch.search_img_in_rect(slot_img, slot_location):
                return False
        return True
    
    def is_last_inv_slot_empty(self):
        """
        Checks if last inventory slot is empty.
        Returns: bool
        """
        slot_location = self.win.inventory_slots[-1].scale(.5,.5)
        slot_img = imsearch.BOT_IMAGES.joinpath(self.WILLOWSDAD_IMAGES, "emptyslot.png")
        return bool(slot := imsearch.search_img_in_rect(slot_img, slot_location))


    def open_bank(self):
        """
        This will bank all logs in the inventory.
        Returns: 
            void
        Args: 
            deposit_slots (int) - Inventory position of each different item to deposit.
        """
        # move mouse to bank and click while not red click
        bank = self.choose_bank()
        self.mouse.move_to(bank.random_point())
        while not self.mouse.click(check_red_click=True):
            bank = self.choose_bank()
            self.mouse.move_to(bank.random_point())

        wait_time = time.time()
        retried = False
        while not self.is_bank_open():
            if time.time() - wait_time > 20 and not retried:
                self.mouse.move_to(bank.random_point())
                while not self.mouse.click(check_red_click=True):
                    bank = self.choose_bank()
                    self.mouse.move_to(bank.random_point())
                retried = True
            # if we waited for 17 seconds, break out of loop
            if time.time() - wait_time > 60:
                self.log_msg("We clicked on the bank but bank is not open after 60 seconds, bot is quiting...")
                self.stop()
            time.sleep(self.random_sleep_length())
        return
    

    def check_text(self, object: RuneLiteObject, text, color : clr = None):
        """
        calls mouseover text in a loop
        Returns: void
        Args: None
        """
        if not isinstance(text, list):
            text = [text]

        time_searching = time.time()
        search_tries = 1

        while all(txt not in self.mouseover_text() for txt in text):
            time.sleep(self.random_sleep_length(.1, .2))

            if time.time() - time_searching > 1:
                self.mouse.move_to(object.random_point())

            if time.time() - time_searching > 4:
                msg = f"Did not see any of {text} in mouseover text after {search_tries} searches, quitting bot so you can fix it..."
                self.log_msg(msg)
                self.stop()

            search_tries += 1


    def choose_bank(self):
        """
        Has a small chance to choose the second closest bank to the player.
            Returns: bank rectangle or none if no banks are found
            Args: None

        """
        bank = self.get_nearest_tag(clr.YELLOW)

        time_searching = time.time()
        while not bank:
            bank = self.get_nearest_tag(clr.YELLOW)
            time.sleep(.2)
            if time.time() - time_searching > 2:
                self.log_msg("No banks found, quitting bot...")
                self.stop()
                return (self.choose_bank())
        return bank
    

    def adjust_camera(self, color, timeout=4):
        """
        Adjusts the camera to look for a specific color. Times out after searching 4 seconds
        Args:
            color: color to look for
        Returns:
            None/Void"""
        random_x = random.randint(90, 180) 
        start_time = time.time() # lets make sure we don't wait too long

        # chance for x to be negative
        if random.randint(0, 1) == 1:
            random_x *= -1
        random_xy = (random_x, 0)  # tuple of random x and y

        # call the camera function on a new thread
        camera_thread = self.StoppableThread(target=self.move_camera, args=(random_xy))
        camera_thread.start()   

        while not self.get_nearest_tag(color):
            time_searching = time.time() - start_time

            if time_searching > timeout:
                self.log_msg(f"Could not find highlighted color in {timeout} seconds...")
                camera_thread.stop()    
                return False
            time.sleep(self.random_sleep_length(.1, .2))
        camera_thread.stop()
        time.sleep(self.random_sleep_length())
        return True


    class StoppableThread(threading.Thread):
        """Thread class with a stop() method. The thread itself has to check.
            Useful for looking for a tag while main thread is doing something else."""
        def __init__(self, target=None, args=()):
            super().__init__(target=target, args=args)
            self._stop_event = threading.Event()

        def stop(self):
            self._stop_event.set()

        def stopped(self):
            return self._stop_event.is_set()


    def click_in_bank(self, item, amount=1):
        """
        Clicks on an item in the bank x times.
        Args:
            item (RuneLiteObject) - Item to click on
            amount (int) - Number of times to click on item
        Returns:
            void"""
        for _ in range(amount):
            self.mouse.move_to(item.random_point())
            if self.mouseover_text("Release", clr.OFF_WHITE):
                return False
            self.mouse.click()
            time.sleep(self.random_sleep_length())
            return True


    def withdraw_items2(self, items: Union[RuneLiteObject, List[RuneLiteObject]], count=1) -> bool:
        """
        Given a list of runelite items, clicks on them from their saved locations.
        Returns True if all items are found and clicked, False otherwise.
        Args:
            items: A RuneLiteObject or list of RuneLiteObjects representing the item images to search for in the bank.
            count: An integer representing the amount of items to withdraw. Default is 1.
        """
        if not isinstance(items, list):
            items = [items]
        for item in items:
            success = self.click_in_bank(item, count)
            if not success:
                self.log_msg(f"Could not find {item} in bank, mouseover check may have failed, or out of supplies")
                self.stop()
        return True


    def is_idle(self):
        return self.check_last_message("You", clr.Color([239, 16, 32]))


    def check_last_message(self, text:str, color:clr):
        return bool(ocr.find_text(text, self.win.chat.scale(scale_height=0.37, scale_width=1, anchor_y=1, anchor_x=0), ocr.PLAIN_12, color))


    def withdraw_items(self, items: Union[Path, List[Path]], count=1, first_found = False) -> bool:
        """
        Withdraws the correct amount of ingredients from the bank.
        Returns True if all items are found and clicked, False otherwise.
        Args:
            items: A Path object or list of Path objects representing the item images to search for in the bank.
            count: An integer representing the amount of items to withdraw. Default is 1.
        """
        def find_and_click(item_img: Path) -> bool:
            """Searches for an item image in the bank and clicks on it."""
            item_found = None
            time_looking_for_item = time.time() + 5
            while time.time() < time_looking_for_item and not item_found:
                # Try several times to find the item
                item_found = imsearch.search_img_in_rect(item_img, self.win.game_view.scale(scale_width=.5))
                if item_found:
                    break
            if not item_found:
                # If the item is not found, log an error message and return False
                self.log_msg(f"Could not find {item_img.stem} in bank, out of supplies...")
                return False
            else:
                # If the item is found, click on it and return True
                self.click_in_bank(item_found, count)
                return True

        # Convert the input to a list if it's a single Path object
        if isinstance(items, Path):
            items = [items]

        # Loop through each item and find/click it in the bank
        all_items_found = True
        for item_path in items:
            item_found = find_and_click(item_path)
            time.sleep(self.random_sleep_length())
            if not item_found:
                all_items_found = False
            if first_found and item_found:
                return True

        # Return True if all items were found and clicked, False otherwise
        return all_items_found


    def deposit_items(self, slot_list, clicks=1, speed = "fastest"):
        """
        Clicks once on each unique item to deposit all matching items in the inventory to the bank.
        Bank must be open already.
        Deposit "All" must be selected.
        Args:
            slot_list: list of inventory slots to deposit items from
        Returns:
            None/Void
        """
        if slot_list == -1:
            # If there are no items to deposit, log a message and return early
            self.log_msg("No items to deposit, continuing...")
            return
        if slot_list == 0:
            # If there's only one item, it is the first slot
            slot_list = [0]
        # Move the mouse to each slot in the inventory and click to deposit all matching items
        for slot in slot_list:
            self.mouse.move_to(self.win.inventory_slots[slot].random_point(), mouseSpeed = speed)
            self.mouse.click()
            time.sleep(self.random_sleep_length())

        self.log_msg("Finished depositing items")
        return


    def face_north(self):
        """Faces the player north.
            Args:
                None
            Returns:
                None"""
        # Move the mouse to the compass orb and click it to face north
        self.mouse.move_to(self.win.compass_orb.random_point(), mouseSpeed = "fastest")
        self.mouse.click()


    def close_bank(self):
        """Exits the bank by clicking on the exit button, or pressing the esc key if the button is not found"""
        # Search for the exit button in the bank interface
        # if not self.exit_btn:
        #     self.exit_btn = imsearch.search_img_in_rect(self.WILLOWSDAD_IMAGES.joinpath("bank_exit.png"), self.win.game_view.scale(scale_height=.2, scale_width=.5, anchor_y=0))

        # # If the exit button is not found, press the esc key and check if the bank is closed
        # time_searching = time.time()
        # while not self.exit_btn:
        #     self.exit_btn = imsearch.search_img_in_rect(self.WILLOWSDAD_IMAGES.joinpath("bank_exit.png"), self.win.game_view.scale(scale_height=.2, scale_width=.5, anchor_y=1), confidence=.1)
        #     if time.time() - time_searching > 2:
        #         # If the exit button is still not found after 2 second, log an error message and stop the bot
        #         self.log_msg("Could not find bank exit button, pressing esc.")
        #         pag.press("esc")
        #         time.sleep(self.random_sleep_length())
        #         if not self.is_bank_open():
        #             return
        #         self.log_msg("Closing bank failed, quitting bot...")
        #         self.stop()
        #     time.sleep(.2)

        # # Click on the exit button to close the bank
        # self.mouse.move_to(self.exit_btn.random_point())
        # self.mouse.click()

        # send esc key to close bank
        pag.press("esc")

        return


    def check_run(self):
        run_energy = self.get_run_energy()
        if run_energy < 50:
            return
        elif rd.random_chance(probability=run_energy/100):
            run = imsearch.search_img_in_rect(self.WILLOWSDAD_IMAGES.joinpath("run_enabled.png"), self.win.run_orb.scale(3,3))
            if run is None:
                self.mouse.move_to(self.win.run_orb.random_point())
                self.mouse.click()
                time.sleep(self.random_sleep_length())
        return


    def is_bank_open(self):
        """Checks if the bank is open, if not, opens it
        Returns:
            True if the bank is open, False if not
        Args:
            None"""
        # Define the image to search for in the bank interface
        deposit_all_img = self.WILLOWSDAD_IMAGES.joinpath("bank_all.png")

        # Set a time limit for searching for the image
        end_time = time.time() + 2

        # Loop until the time limit is reached
        while (time.time() < end_time):
            # Check if the image is found in the game view
            if deposit_btn := imsearch.search_img_in_rect(deposit_all_img, self.win.game_view.scale(scale_height=.2, anchor_y=.8)):
                return True

            # Sleep for a short time to avoid excessive CPU usage
            time.sleep(.2)

        # If the image was not found within the time limit, return False
        return False
    

    def bank_all(self):
        """Searches and clicks on the "Deposit All" button in the bank interface
        Args:
            None"""
        # Define the image to search for in the bank interface
        deposit_all_img = self.WILLOWSDAD_IMAGES.joinpath("bank_all.png")

        # Set a time limit for searching for the image
        end_time = time.time() + 1

        # Loop until the time limit is reached
        while (time.time() < end_time):
            # Check if the image is found in the game view, and move mouse and click if it is
            if deposit_btn := imsearch.search_img_in_rect(deposit_all_img, self.win.game_view.scale(scale_height=.2, anchor_y=.8)):
                self.mouse.move_to(deposit_btn.random_point())
                self.mouse.click()
                return

            # Sleep for a short time to avoid excessive CPU usage
            time.sleep(.2)

        self.log_msg("Could not find deposit all button, quitting bot...")
        self.stop()
        return

    
    def check_withdraw_x(self, amount):
        if withdraw_grey := imsearch.search_img_in_rect(self.WILLOWSDAD_IMAGES.joinpath("deposit_x_grey.png"), self.win.game_view.scale(1, .5, anchor_y=.75), confidence=.1):
            self.mouse.move_to(withdraw_grey.scale(.5,.5).random_point())
            self.sleep(self.random_sleep_length())
            if self.mouseover_text(f"{amount}", color=clr.OFF_WHITE):
                self.mouse.click()
            else:
                self.log_msg(f"Set withdraw amount to {amount}.")
                self.stop()
        elif withdraw_red := imsearch.search_img_in_rect(self.WILLOWSDAD_IMAGES.joinpath("deposit_x_red.png"), self.win.game_view.scale(1,.5, anchor_y=.75)):
            self.mouse.move_to(withdraw_red.scale(.3,.3).random_point())
            self.sleep(self.random_sleep_length())
            if self.mouseover_text(f"{amount}", color=clr.OFF_WHITE):
                return
            self.log_msg(f"Set withdraw amount to {amount}.")
            self.stop()
        else:
            self.log_msg("Could not find withdraw x button using image search, please check code, report to developer.")
            self.stop()


    def right_click_select(self, text:str, color:clr):
        """Right clicks on the screen and selects the option with the given text"""
        self.mouse.right_click()
        time.sleep(self.random_sleep_length(.2, .46))

        # Get the current mouse position and create a Point from it
        mouse_pos = Point(*pag.position())

        # Get monitor dimensions
        max_x, max_y = pag.size()

        # Define the dimensions of the rectangle as percentages of the screen size
        rect_width = int(max_x * 0.2)  # 20% of the screen width
        rect_height = int(max_y * 0.3)  # 30% of the screen height

        # Create points for the rectangle
        p1 = Point(max(mouse_pos.x - rect_width // 2, 0), mouse_pos.y)  # top-left point
        p2 = Point(min(mouse_pos.x + rect_width // 2, max_x), min(mouse_pos.y + rect_height, max_y))  # bottom-right point

        # Create the rectangle
        rect = Rectangle.from_points(p1, p2)

        found = ocr.find_text(text, rect, ocr.BOLD_12, color)

        # if text was not found, lets quit
        if not found:
            self.log_msg(f"Could not find text {text} in right click menu, quitting bot...")
            self.stop()

        self.mouse.move_to(found[0].scale(.7,.7).random_point())
        time.sleep(self.random_sleep_length(.22,.42))

        self.mouse.click()


    def check_if_worn(self, img_path:Path):
        """This will check if the given image is worn"""

        # open worn equipment
        self.mouse.move_to(self.win.cp_tabs[4].random_point())
        self.mouse.click()

        # find image in worn equipment
        item = imsearch.search_img_in_rect(img_path, self.win.control_panel)

        self.mouse.move_to(self.win.cp_tabs[3].random_point())
        self.mouse.click()

        if item is None:
            return False
        return True


    def get_UandP(self):
        top = Tk()
        top.title("User Login")  # Setting the window title

        explain_label = Label(top, text="Please enter your username and password for the bot to use: ")
        explain_label.grid(row=0, column=0, columnspan=2)

        L1 = Label(top, text="Username")
        L1.grid(row=1, column=0)
        E1 = Entry(top, bd=5)
        E1.grid(row=1, column=1)
        E1.focus_set()

        L2 = Label(top, text="Password")
        L2.grid(row=2, column=0)
        E2 = Entry(top, bd=5, show="*")
        E2.grid(row=2, column=1)

        B = Button(top, text ="Submit", command = lambda: self.save_credentials(E1, E2, top))
        B.grid(row=3, column=1)

        top.bind('<Return>', lambda event: self.save_credentials(E1, E2, top))

        top.lift()
        top.focus_force()
        top.attributes('-topmost', True)
        top.after(100, lambda: top.attributes('-topmost', False)) 
        
        top.mainloop()

    def save_credentials(self, E1, E2, top):
        self.username = E1.get()
        self.password = E2.get()
        top.destroy()


    def take_birdhouse_break(self):
        """This will complete a birdhouse run
        Args:
            None
            Returns:"""
        # setup
        birdhouse_seeds = [self.WILLOWSDAD_IMAGES.joinpath("Hammerstone_seeds.png")]
        birdhouse_items = [self.birdhouse]
        digsite_pendant = self.WILLOWSDAD_IMAGES.joinpath("Digsite_pendant.png")
        self.need_to_equip = False       

        # birdhosues, seeds, digsite pendant
        self.face_north()

        # check if digsite pendant is worn
        if not self.check_if_worn(digsite_pendant):
            self.need_to_equip = True

        # banking
        self.open_bank()
        self.check_deposit_5()
        if not self.is_inv_empty():
            self.bank_all()
        if self.withdraw_all(birdhouse_seeds) is False:
            self.log_msg("Could not find birdhouse seeds in bank, quitting bot...")
            self.stop()
        if self.withdraw_items(birdhouse_items, first_found=True) is False:
            self.log_msg("Could not find birdhouse in bank, quitting bot...")
            self.stop()

        # equip digsite pendant
        self.__check_and_withdraw_pendant(digsite_pendant)

        self.close_bank()
        time.sleep(self.random_sleep_length())

        # if we need to equip, find it in inventory and click it
        if self.need_to_equip:
            # find and click digspite pendant
            found = imsearch.search_img_in_rect(self.WILLOWSDAD_IMAGES.joinpath("Digsite_pendant.png"), self.win.control_panel)
            if found is None:
                self.log_msg("Could not find digsite pendant in controlpanel, please check code, report to developer.")
                self.stop()
            self.mouse.move_to(found.random_point())
            self.mouse.click()
        time.sleep(self.random_sleep_length())

        # Incase of misclick, lets make sure last message is correct
        self.__teleport_to_digsite()

        start_time = time.time()
        while not self.check_last_message("rub", clr.BLACK):
            time.sleep(self.random_sleep_length(.4, .6))
            if time.time() - start_time > 10:
                self.__teleport_to_digsite()
                break

        # This waits for the black screen before walking
        time.sleep(self.random_sleep_length(1.5, 1.9))

        # run to magic mushtree
        self.walk_vertical(color=clr.PINK, direction=1)

        # teleport to verdant valley
        self.__teleport_to_verdant_valley()
        self.wait_until_color(color=clr.YELLOW)

        self.__do_verdant_valley_run()

        # teleport to meadows
        self.__teleport_to_meadows()
        self.wait_until_color(color=clr.GREEN)

        self.__do_meadows_run()

        self.__walk_to_birdhouse_bank()
        self.open_bank()
        self.bank_all()
        time.sleep(self.random_sleep_length())
        self.close_bank()


    def __check_and_withdraw_pendant(self, digsite_pendant):
        if self.need_to_equip:
            found = imsearch.search_img_in_rect(digsite_pendant, self.win.game_view)
            if found is None:
                self.log_msg("Could not find digsite pendant in bank, quitting bot...")
                self.stop()
            self.mouse.move_to(found.random_point())
            self.right_click_select("Withdraw-1", clr.WHITE)
            time.sleep(self.random_sleep_length())


    def __walk_to_birdhouse_bank(self):
        # walk vertical to bank
        self.walk_horizontal(color=clr.YELLOW, direction=-1, wait_till_stop=True)


    def __do_meadows_run(self):
        # run to first birdhouse
        self.__run_to_birdhouse(clr.PINK, "vertical", 1)

        # load seeds
        self.__load_seeds(clr.PINK)

        # run to second birdhouse
        self.__run_to_birdhouse(clr.BLUE, "vertical", -1)

        # load seeds
        self.__load_seeds(clr.BLUE)


    def __teleport_to_meadows(self):
        """runs to tree from verdant valley and teleports to meadows"""
        # run to tree
        self.walk_vertical(color=clr.YELLOW, direction=-1)

        tree = self.get_nearest_tag(clr.YELLOW)
        self.mouse.move_to(tree.random_point())
        while not self.mouse.click(check_red_click=True):
            tree = self.get_nearest_tag(clr.YELLOW)
            self.mouse.move_to(tree.random_point())
        time.sleep(self.random_sleep_length() * 2)
        
        btn_found = imsearch.search_img_in_rect(self.WILLOWSDAD_IMAGES.joinpath("mushtree_title.png"), self.win.game_view)
        while btn_found is None:
            btn_found = imsearch.search_img_in_rect(self.WILLOWSDAD_IMAGES.joinpath("mushtree_title.png"), self.win.game_view)
            time.sleep(self.random_sleep_length())
        
        # send key press "2"
        pag.press("4")


    def __do_verdant_valley_run(self):
        # run to first birdhouse
        self.__run_to_birdhouse(clr.PINK, "horizontal", 1)

        # load seeds
        self.__load_seeds(clr.PINK)

        # run to second birdhouse
        self.__run_to_birdhouse(clr.BLUE, "horizontal", 1)

        # load seeds
        self.__load_seeds(clr.BLUE)

    def __run_to_birdhouse(self, color, direction, dir_value):
        if direction == "horizontal":
            self.walk_horizontal(color=color, direction=dir_value)
        elif direction == "vertical":
            self.walk_vertical(color=color, direction=dir_value, wait_till_stop=True)
        else:
            raise ValueError("Direction must be horizontal or vertical")
        current_xp = self.get_total_xp()
        birdhouse = self.get_nearest_tag(color)
        self.mouse.move_to(birdhouse.random_point())
        while not self.mouse.click(check_red_click=True):
            birdhouse = self.get_nearest_tag(color)
            self.mouse.move_to(birdhouse.random_point())

        # wait till xp is gained
        while not current_xp < self.get_total_xp():
            time.sleep(self.random_sleep_length())

        time.sleep(self.random_sleep_length(.8, 1.2))
        self.mouse.move_to(self.get_nearest_tag(color).random_point())
        while not self.mouse.click(check_red_click=True):
            self.wait_until_color(color=color)
            self.mouse.move_to(self.get_nearest_tag(color).random_point())

        time.sleep(self.random_sleep_length())


    def __load_seeds(self, color):
        seeds = imsearch.search_img_in_rect(self.WILLOWSDAD_IMAGES.joinpath("Hammerstone_seeds.png"), self.win.control_panel)
        if seeds is None:
            self.log_msg("Could not find seeds, quitting bot...")
            self.stop()
        self.mouse.move_to(seeds.random_point())
        time.sleep(self.random_sleep_length())

        self.mouse.click()
        time.sleep(self.random_sleep_length())

        self.mouse.move_to(self.get_nearest_tag(color).random_point())
        time.sleep(self.random_sleep_length())

        while not self.mouse.click(check_red_click=True):
            seeds = imsearch.search_img_in_rect(self.WILLOWSDAD_IMAGES.joinpath("Hammerstone_seeds.png"), self.win.control_panel)
            if seeds is None:
                self.log_msg("Could not find seeds, quitting bot...")
                self.stop()
            self.mouse.move_to(seeds.random_point())
            self.mouse.click()
            time.sleep(self.random_sleep_length())
            self.mouse.move_to(self.get_nearest_tag(color).random_point())

        time.sleep(self.random_sleep_length())

        

    def __teleport_to_verdant_valley(self):
        """This will click the mushtree and teleport to verdant valley"""

        # click on the tree
        tree = self.get_nearest_tag(clr.PINK)
        self.mouse.move_to(tree.random_point())
        while not self.mouse.click(check_red_click=True):
            tree = self.get_nearest_tag(clr.PINK)
            self.mouse.move_to(tree.random_point())
        time.sleep(self.random_sleep_length() * 2)
        
        btn_found = imsearch.search_img_in_rect(self.WILLOWSDAD_IMAGES.joinpath("mushtree_title.png"), self.win.game_view)
        while btn_found is None:
            btn_found = imsearch.search_img_in_rect(self.WILLOWSDAD_IMAGES.joinpath("mushtree_title.png"), self.win.game_view)
            time.sleep(self.random_sleep_length())
        
        # send key press "2"
        pag.press("2")

    def __teleport_to_digsite(self):
        """This will right click teleport to digsite"""

        # open worn equipment
        self.mouse.move_to(self.win.cp_tabs[4].random_point())
        time.sleep(self.random_sleep_length(.25, .42))
        self.mouse.click()

        # find and click digspite pendant
        digsite_pendant = imsearch.search_img_in_rect(self.WILLOWSDAD_IMAGES.joinpath("Digsite_pendant.png"), self.win.control_panel)
        if digsite_pendant is None:
            self.log_msg("Could not find digsite pendant in controlpanel, please check code, report to developer.")
            self.stop()
        self.mouse.move_to(digsite_pendant.random_point())
        time.sleep(self.random_sleep_length(.25, .42))

        self.right_click_select("Fossil Island", clr.WHITE)
        time.sleep(self.random_sleep_length(.25, .42))
        self.mouse.move_to(self.win.cp_tabs[3].random_point())
        time.sleep(self.random_sleep_length(.25, .42))
        self.mouse.click()


    def withdraw_all(self, items: Union[Path, List[Path]]):
        """This will shift+click to withdraw all items from a bank"""
        def find_and_click(item_img: Path) -> bool:
            """Searches for an item image in the bank and clicks on it."""
            item_found = None
            time_looking_for_item = time.time() + 5
            while time.time() < time_looking_for_item and not item_found:
                # Try several times to find the item
                item_found = imsearch.search_img_in_rect(item_img, self.win.game_view)
                if item_found:
                    break
            if not item_found:
                # If the item is not found, log an error message and return False
                self.log_msg(f"Could not find {item_img.stem} in bank, out of supplies...")
                return False
            else:
                # If the item is found, move mouse to item, and shift+click to withdraw all
                self.mouse.move_to(item_found.random_point())
                pag.keyDown("shift")
                self.mouse.click()
                pag.keyUp("shift")
                return True

        # Convert the input to a list if it's a single Path object
        if isinstance(items, Path):
            items = [items]

        # Loop through each item and find/click it in the bank
        all_items_found = True
        for item_path in items:
            item_found = find_and_click(item_path)
            time.sleep(self.random_sleep_length())
            if not item_found:
                all_items_found = False

        # Return True if all items were found and clicked, False otherwise
        return all_items_found


    def walk_vertical(self, direction: int, color: clr = None, timeout: int = 60, img: Path = None, wait_till_stop: bool = False):
        """
        Walks towards or away from a specific color tile in game or image.
        Returns: void
        Args: 
            color: color of the tile to walk to
            direction: direction to walk to (towards 1, away -1)
            timeout: time to wait before stopping"""
        
        if color is None and img is None:
            self.log_msg("No stop condition. Add color or img path to stop walking.")
            self.stop()

        time_start = time.time()
        while True:
            # Check if the player needs to switch direction for a smoother walk when walking to the bank
            if img != None:
                if change_direction_img := imsearch.search_img_in_rect(img, self.win.minimap):
                    return

            # Stop walking if timeout is exceeded
            if time.time() - time_start > timeout:
                self.log_msg(f"We've been walking for {timeout} seconds, something is wrong...stopping.")
                self.stop()

            if color is not None:
                # Stop walking if the target color tile is found
                if found := self.get_nearest_tag(color):
                    if wait_till_stop:
                        last_distance = found.distance_from_rect_center()
                        current_distance = None
                        while last_distance != current_distance:
                            time.sleep(self.random_sleep_length())
                            last_distance = current_distance
                            current_distance = self.get_nearest_tag(color).distance_from_rect_center()
                    break

            # Get all cyan tiles in the game view
            shapes = self.get_all_tagged_in_rect(self.win.game_view, clr.CYAN)

            # Stop if no cyan tiles are found
            if shapes is []:
                self.log_msg("No cyan tiles found, stopping.")
                return
            
            reverse = direction != 1

            # Sort the cyan tiles based on their distance from the top-center
            if len(shapes) > 1:
                shapes_sorted = sorted(shapes, key=RuneLiteObject.distance_from_rect_top , reverse=reverse)
                self.mouse.move_to(shapes_sorted[0].scale(3,3).random_point(), mouseSpeed = "fastest")
            else:
                self.mouse.move_to(shapes[0].scale(3,3).random_point(), mouseSpeed = "fastest")

            # Click on the selected tile and wait for a random duration between 0.35 and 0.67 seconds
            self.mouse.click()
            time.sleep(self.random_sleep_length(1, 1.7))

        return
    

    def walk_horizontal(self, direction: int, color: clr = None, timeout: int = 60, img: Path = None, wait_till_stop: bool = False):
        """
        Walks towards or away from a specific color tile in game or image.
        Returns: void
        Args: 
            color: color of the tile to walk to
            direction: direction to walk to (towards 1, away -1)
            timeout: time to wait before stopping"""
        
        if color is None and img is None:
            self.log_msg("No stop condition. Add color or img path to stop walking.")
            self.stop()

        time_start = time.time()
        while True:
            # Check if the player needs to switch direction for a smoother walk when walking to the bank
            if img != None:
                if change_direction_img := imsearch.search_img_in_rect(img, self.win.minimap):
                    return

            # Stop walking if timeout is exceeded
            if time.time() - time_start > timeout:
                self.log_msg(f"We've been walking for {timeout} seconds, something is wrong...stopping.")
                self.stop()

            if color is not None:
                # Stop walking if the target color tile is found
                if found := self.get_nearest_tag(color):
                    if wait_till_stop:
                        last_distance = found.distance_from_rect_center()
                        current_distance = None
                        while last_distance != current_distance:
                            time.sleep(self.random_sleep_length())
                            last_distance = current_distance
                            current_distance = self.get_nearest_tag(color).distance_from_rect_center()
                    break

            # Get all cyan tiles in the game view
            shapes = self.get_all_tagged_in_rect(self.win.game_view, clr.CYAN)

            # Stop if no cyan tiles are found
            if shapes is []:
                self.log_msg("No cyan tiles found, stopping.")
                return
            
            reverse = direction != 1

            # Sort the cyan tiles based on their distance from the left-center
            if len(shapes) > 1:
                shapes_sorted = sorted(shapes, key=RuneLiteObject.distance_from_rect_left , reverse=reverse)
                self.mouse.move_to(shapes_sorted[0].scale(3,3).random_point(), mouseSpeed = "fastest")
            else:
                self.mouse.move_to(shapes[0].scale(3,3).random_point(), mouseSpeed = "fastest")

            # Click on the selected tile and wait for a random duration between 0.35 and 0.67 seconds
            self.mouse.click()
            time.sleep(self.random_sleep_length(.67, 1.24))

        return
    
    def wait_until_color(self, color: clr, timeout: int = 10):
        """this will wait till nearest tag is not none"""
        time_start = time.time()
        while True:
            if time.time() - time_start > timeout:
                self.log_msg(f"We've been waiting for {timeout} seconds for color: {color}, something is wrong...stopping.")
                self.stop()
            if found := self.get_nearest_tag(color):
                break
            time.sleep(self.random_sleep_length())
        return
    

    def wait_until_img(self, img: Path, screen: Rectangle, timeout: int = 10):
        """this will wait till img shows up in screen"""
        time_start = time.time()
        while True:
            time.sleep(self.random_sleep_length())
            if found := imsearch.search_img_in_rect(img, screen):
                break
            if time.time() - time_start > timeout:  # Check if we've been waiting longer than the specified timeout
                self.log_msg(f"We've been waiting for {timeout} seconds, something is wrong...stopping.")
                self.stop()
        return found
    

    def is_idle2(self):
        idle_threshold = 0.3  # Adjust the threshold as needed
        previous_screenshot = self.win.game_view.scale(.02, .04, 0.505, 0.495).screenshot()
        consecutive_idle_count = 0

        for _ in range(2):
            current_screenshot = self.win.game_view.scale(.02, .04, 0.505, 0.495).screenshot()

            if previous_screenshot is not None:
                difference = self.is_animating(previous_screenshot, current_screenshot)
                if difference < idle_threshold:
                    consecutive_idle_count += 1
                if consecutive_idle_count == 2:
                    self.log_msg("Idle", overwrite=True)
                    return True

            previous_screenshot = current_screenshot
            time.sleep(0.3)

        self.log_msg("Not Idle", overwrite=True)
        return False


    def wait_until_idle(self):
        idle_threshold = 0.6  # Adjust the threshold as needed
        consecutive_idle_frames = 3  # Number of consecutive frames with a small difference to consider as idle

        previous_screenshot = None
        consecutive_idle_count = 0

        while consecutive_idle_count < consecutive_idle_frames:
            current_screenshot = self.win.game_view.scale(.02, .04, 0.505, 0.495).screenshot()

            if previous_screenshot is not None:
                difference = self.is_animating(previous_screenshot, current_screenshot)
                if difference < idle_threshold:
                    consecutive_idle_count += 1
                else:
                    consecutive_idle_count = 0

            previous_screenshot = current_screenshot
            time.sleep(0.3)


    def is_animating(self, previous_screenshot, current_screenshot):
          """Created by @Gang on the OSBC discord server"""

          gray_img1 = cv2.cvtColor(previous_screenshot, cv2.COLOR_BGR2GRAY)
          gray_img2 = cv2.cvtColor(current_screenshot, cv2.COLOR_BGR2GRAY)

          diff = cv2.absdiff(gray_img1, gray_img2)

          _, threshold = cv2.threshold(diff, 30, 255, cv2.THRESH_BINARY)

          contours, _ = cv2.findContours(threshold, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

          total_area = 0
          for contour in contours:
              total_area += cv2.contourArea(contour)

          percentage_diff = (total_area / previous_screenshot.size) * 100

          return percentage_diff

    def wait_for_xp_drop(self, last_xp: int, timeout: int = 5):
        """This will wait for the xp drop to appear"""
        time_start = time.time()
        current_xp = self.get_total_xp()
        while current_xp == last_xp:
            if time.time() - time_start > timeout:
                self.log_msg(f"We've been waiting for {timeout} seconds for xp drop.")
                return False
            current_xp = self.get_total_xp()
            time.sleep(self.random_sleep_length() / 2)
        return True

    def wait_till_npc_dead(self, timeout: int = 70):
        """This will wait till npc is dead"""
        time_start = time.time()
        while True:
            text = ocr.extract_text(self.win.game_view.scale(.3,.3,0,0), font=ocr.PLAIN_12 , color=clr.WHITE, exclude_chars="abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ'\"`")
            # while text does not contain "0/" or anything before the 0 (like 20/)
            if text.startswith("0/"):
                return
            if time.time() - time_start > timeout:
                self.log_msg(f"We've been waiting for {timeout} seconds for npc to die.")
                return
            if not self.api_m.get_is_in_combat():
                return
            time.sleep(self.random_sleep_length())