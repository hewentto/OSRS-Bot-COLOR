import time

import utilities.api.item_ids as ids
import utilities.color as clr
from utilities.geometry import RuneLiteObject
import utilities.random_util as rd
from model.osrs.osrs_bot import OSRSBot
from utilities.api.morg_http_client import MorgHTTPSocket
from utilities.api.status_socket import StatusSocket
import pyautogui as pag
import utilities.imagesearch as imsearch



class OSRSUltraCompostMaker(OSRSBot):
    def __init__(self):
        bot_title = "WillowsDad Ultra Compost Maker"
        description = "Place this near a bank with ingredients and it will make ultra compost for you."
        super().__init__(bot_title=bot_title, description=description)
        # Set option variables below (initial value is only used during UI-less testing)
        self.take_breaks = True
        self.afk_train = True
        self.delay_min =0.37
        self.delay_max = .67
        self.running_time = 1

    def create_options(self):
        """
        Use the OptionsBuilder to define the options for the bot. For each function call below,
        we define the type of option we want to create, its key, a label for the option that the user will
        see, and the possible values the user can select. The key is used in the save_options function to
        unpack the dictionary of options after the user has selected them.
        """
        self.options_builder.add_slider_option("running_time", "How long to run (minutes)?", 1, 500)
        self.options_builder.add_checkbox_option("afk_train", "Train like you're afk on another tab?", [" "])
        self.options_builder.add_checkbox_option("take_breaks", "Take breaks?", [" "])
        self.options_builder.add_slider_option("delay_min", "How long to take between actions (min) (MiliSeconds)?", 300,3000)
        self.options_builder.add_slider_option("delay_max", "How long to take between actions (max) (MiliSeconds)?", 650,3000)

    def save_options(self, options: dict):
        """
        For each option in the dictionary, if it is an expected option, save the value as a property of the bot.
        If any unexpected options are found, log a warning. If an option is missing, set the options_set flag to
        False.
        """
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
            else:
                self.log_msg(f"Unknown option: {option}")
                print("Developer: ensure that the option keys are correct, and that options are being unpacked correctly.")
                self.options_set = False
                return
        self.log_msg(f"Running time: {self.running_time} minutes.")
        self.log_msg("Options set successfully.")
        self.options_set = True

    def main_loop(self):
        """
        When implementing this function, you have the following responsibilities:
        1. If you need to halt the bot from within this function, call `self.stop()`. You'll want to do this
           when the bot has made a mistake, gets stuck, or a condition is met that requires the bot to stop.
        2. Frequently call self.update_progress() and self.log_msg() to send information to the UI.
        3. At the end of the main loop, make sure to call `self.stop()`.

        Additional notes:
        - Make use of Bot/RuneLiteBot member functions. There are many functions to simplify various actions.
          Visit the Wiki for more.
        - Using the available APIs is highly recommended. Some of all of the API tools may be unavailable for
          select private servers. To see what the APIs can offer you, see here: https://github.com/kelltom/OSRS-Bot-COLOR/tree/main/src/utilities/api.
          For usage, uncomment the `api_m` and/or `api_s` lines below, and use the `.` operator to access their
          functions.
        """
        # Setup APIs
        # api_m = MorgHTTPSocket()
        # api_s = StatusSocket()
        self.setup()
        # Main loop
        while time.time() - self.start_time < self.end_time:

            runtime = int(time.time() - self.start_time)
            minutes_since_last_break = int((time.time() - self.last_break) / 60)
            seconds = int(time.time() - self.last_break) % 60
            percentage = (self.multiplier * .01)  # this is the percentage chance of a break
            deposit_slots = self.api_m.get_inv_item_index(self.deposit_ids)
            self.roll_chance_passed = False

            if len(self.api_m.get_inv_item_indices(ids.SUPERCOMPOST)) == 0:
                self.bank(deposit_slots)

                time.sleep(self.random_sleep_length() * 1.2)

            # Check if idle
            if self.api_m.get_is_player_idle():
                self.make_compost()
                while len(self.api_m.get_inv_item_indices(ids.ULTRACOMPOST)) != 27:
                    time.sleep(self.random_sleep_length(1.1, 1.4))


            # -- End bot actions --
            # self.check_break(runtime, percentage, minutes_since_last_break, seconds, deposit_slots)
            current_progress = round((time.time() - self.start_time) / self.end_time, 2)
            if current_progress != round(self.last_progress, 2):
                self.update_progress((time.time() - self.start_time) / self.end_time)
                self.last_progress = round(self.progress, 2)

        self.update_progress(1)
        self.log_msg("Finished.")
        self.stop()

    def setup(self):
        """Sets up loop variables, checks for required items, and checks location.
            Args:
                None
            Returns:
                None"""
        self.start_time = time.time()
        self.end_time = self.running_time * 60
        self.is_focused = self.is_runelite_focused()
        self.roll_chance_passed = False
        self.force_count = 0
        self.last_progress = 0
        self.idle_time = 0
        self.breaks_skipped = 0
        self.withdraw_ids = [ids.SUPERCOMPOST, ids.VOLCANIC_ASH]
        self.deposit_ids = [ids.ULTRACOMPOST]
        self.last_break = time.time()
        self.multiplier = 1
        self.loop_count = 0
        self.api_m = MorgHTTPSocket()
        self.last_runtime = 0
    
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

    def bank(self, deposit_slots):
        end_time = time.time() + 5
        while time.time() < end_time:
            if not self.is_runelite_focused():   
                self.log_msg("Inventory is full but runelight is not in focus, lets wait...")
                time.sleep(self.random_sleep_length(.8, 1.2))
                self.win.focus()
                break
            self.find_bank(deposit_slots)
    
    
    def random_sleep_length(self, delay_min=0, delay_max=0):
        """Returns a random float between min and max"""
        if delay_min == 0:
            delay_min = self.delay_min
        if delay_max == 0:
            delay_max = self.delay_max
        return rd.fancy_normal_sample(delay_min, delay_max)
    

    def find_bank(self, deposit_slots):
        """
        This will bank all compost in the inventory.
        Returns: 
            void
        Args: 
            deposit_slots (int) - Inventory position of each different item to deposit.
        """
        search_tries = 1

         # Time to bank
        self.log_msg("Banking...")
        # move mouse one of the closes 2 banks

        bank = self.choose_bank()

        # move mouse to bank and click
        self.mouse.move_to(bank.random_point())
        time.sleep(self.random_sleep_length(.8, 1.2))

        # search up to 5 times for mouseover text "bank"
        while not self.mouseover_text(contains="Bank"):
            self.log_msg(f"Bank not found, trying again. Try #{search_tries}.")
            self.mouse.move_to(bank.random_point())
            time.sleep(self.random_sleep_length())

            if search_tries > 5:
                self.log_msg(f"Did not see 'Bank' in mouseover text after {search_tries} searches, quitting bot so you can fix it...")
                self.stop()
            search_tries += 1

        self.mouse.click()
        time.sleep(self.random_sleep_length())

        wait_time = time.time()
        while not self.api_m.get_is_player_idle():
            # if we waited for 10 seconds, break out of loop
            if time.time() - wait_time > 15:
                self.log_msg("We clicked on the bank but player is not idle after 10 seconds, something is wrong, quitting bot.")
                self.stop()
            time.sleep(self.random_sleep_length(.8, 1.3))
            
        # if bank is open, deposit all 
        self.bank_each_item(deposit_slots)

        return
    

    def choose_bank(self):
        """
        Has a small chance to choose the second closest bank to the player.
            Returns: bank rectangle or none if no banks are found
            Args: None

        """
        if banks := self.get_all_tagged_in_rect(self.win.game_view, clr.YELLOW):
            banks = sorted(banks, key=RuneLiteObject.distance_from_rect_center)

            if len(banks) == 1:
                return banks[0]
            if (len(banks) > 1):
                return banks[0] if rd.random_chance(.74) else banks[1]
        else:
            self.log_msg("No banks found, make sure they are marked yellow and visiible in the game window.")
            self.stop()
    

    def bank_each_item(self, slot_list):
        """
        Clicks once on each unique item. 
        Bank must be open already.
        Deposit "All" must be selected.

        Args:
            slot_list: list of inventory slots to deposit items from
        Returns:
            None/Void
        """
        try_count = 0

        # Make sure bank is open
        if not self.is_bank_open():
            self.log_msg("Bank is not open, cannot deposit items. Quitting bot...")
            self.stop()

        # move mouse each slot and click to deposit all
        if slot_list != -1:
            for slot in slot_list:
                self.mouse.move_to(self.win.inventory_slots[slot].random_point())
                time.sleep(self.random_sleep_length(.8, 1.3))
                if not self.mouseover_text(contains=["All"]):
                    self.log_msg("Bank deposit settings are not set to 'Deposit All', or something is wrong, trying again")
                    try_count += 1
                else:
                    self.mouse.click()
                    time.sleep(self.random_sleep_length())
                if try_count > 5:
                    self.log_msg(f"Tried to deposit {try_count} times, quitting bot so you can fix it...")
                    self.stop()

        # we now exit bank by sending the escape key

        self.withdraw_ingredients()

        pag.press("esc")
        self.random_sleep_length()
        
        return
    

    def is_bank_open(self):
        """Makes sure bank is open, if not, opens it
        Returns:
            True if bank is open, False if not
        Args:
            None"""
        Desposit_all_img = imsearch.BOT_IMAGES.joinpath("bank", "bank_all.png")
        end_time = time.time() + self.random_sleep_length()

        while (time.time() < end_time):
            if deposit_btn := imsearch.search_img_in_rect(Desposit_all_img, self.win.game_view):
                return True
            time.sleep(.1)
        return False
    

    def withdraw_ingredients(self):
        """
        Withdraws the correct amount of ingredients from the bank.
        """
        ash_img = imsearch.BOT_IMAGES.joinpath("bank", "Volcanic_ash_bank.png")
        Supercompost_img = imsearch.BOT_IMAGES.joinpath("bank", "Supercompost_bank.png")


        time_looking_for_supercompost = time.time() + 5        
        while time.time() < time_looking_for_supercompost:
        # try several times to find it
            supercompost = imsearch.search_img_in_rect(Supercompost_img, self.win.game_view)
            if supercompost:
                break
        if not supercompost:
            self.log_msg("Could not find supercompost in bank, quitting bot...")
            self.stop()

        time.sleep(self.random_sleep_length())
        self.click_in_bank(supercompost)

    # TODO Rename this here and in `withdraw_ingredients`
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
            self.mouse.click()
            time.sleep(self.random_sleep_length())
    

    def make_compost(self):
        """
        Makes compost by click on each item and hitting space
        Returns:
            void
        Args:
            None
        """
        # get unique items in inventory
        unique_items = self.api_m.get_inv_item_index(self.withdraw_ids)

        # move mouse to each item and click
        for item in unique_items:
            self.mouse.move_to(self.win.inventory_slots[item].random_point())
            time.sleep(self.random_sleep_length())
            self.mouse.click()
            time.sleep(self.random_sleep_length())
        
        # hit space to make compost
        time.sleep(self.random_sleep_length())
        pag.press("space")