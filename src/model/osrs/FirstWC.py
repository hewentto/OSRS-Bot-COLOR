import time

import utilities.api.item_ids as ids
import utilities.color as clr
import utilities.random_util as rd
from model.osrs.osrs_bot import OSRSBot
from utilities.api.morg_http_client import MorgHTTPSocket
from utilities.api.status_socket import StatusSocket
import utilities.imagesearch as imsearch
import random
import pyautogui as pag


class OSRSFirstWc(OSRSBot):
    def __init__(self):
        bot_title = "Low Level Woodcutting"
        description = "<Bot description here.>"
        super().__init__(bot_title=bot_title, description=description)
        # Set option variables below (initial value is only used during UI-less testing)
        self.running_time = 1
        self.take_breaks = True

    def create_options(self):
        """
        Use the OptionsBuilder to define the options for the bot. For each function call below,
        we define the type of option we want to create, its key, a label for the option that the user will
        see, and the possible values the user can select. The key is used in the save_options function to
        unpack the dictionary of options after the user has selected them.
        """
        self.options_builder.add_slider_option("running_time", "How long to run (minutes)?", 1, 500)
        self.options_builder.add_dropdown_option("take_breaks", "Take breaks?", ["Yes", "No"])

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
                self.take_breaks = options[option] == "Yes"
            else:
                self.log_msg(f"Unknown option: {option}")
                print("Developer: ensure that the option keys are correct, and that options are being unpacked correctly.")
                self.options_set = False
                return
        self.log_msg(f"Running time: {self.running_time} minutes.")
        self.log_msg(f"Bot will{' not' if not self.take_breaks else ''} take breaks.")
        self.log_msg("Options set successfully.")
        self.options_set = True

    def bank_all(self, slot_list):
        # move mouse to first inventory slot
        self.mouse.move_to(self.win.inventory_slots[slot_list[0]].random_point())
        if not self.mouseover_text(contains=["All"]):
            self.log_msg("Bank deposit settings are not set to 'Deposit All', or bank is not open...")
        else:
            self.mouse.click()
        time.sleep(1)
        # we now exit bank by sending the escape key
        pag.press("esc", use_inject_input=False)
        # sleep for a random amount between .4 seconds and 1.2 seconds
        time.sleep(random.uniform(.8, 1.2))
                    
        # make sure inventory is now empty
        if MorgHTTPSocket().get_is_inv_full():
            self.log_msg("Depositing an item didnt work, quitting bot so you can fix it...")
            self.stop()

    def main_loop(self):
        """
        When implementing this function, you have the following responsibilities:
        1. If you need to halt the bot from within this function, call `self.stop()`. You'll want to do this
           when the bot has made a mistake, gets stuck, or a condition is met that requires the bot to stop.
        2. Frequently call self.update_progress() and self.log_msg() to send information to the UI.
        3. At the end of the main loop, make sure to set the status to STOPPED.

        Additional notes:
        Make use of Bot/RuneLiteBot member functions. There are many functions to simplify various actions.
        Visit the Wiki for more.
        """
        # Setup APIs
        end_time = self.running_time * 60
        while time.time() - start_time < end_time:
            # -- Perform bot actions here --

            # 1% chance to take breaks
            if rd.random_chance(probability=0.01) and self.take_breaks:
                self.log_msg("Taking a break...")
                self.take_break(max_seconds=14)
            
            log_slots = api_m.get_inv_item_indices([ids.logs, ids.OAK_LOGS])

            # check if inventory is full and we have expected slots filled with logs
            if api_m.get_is_inv_full() and log_slots:
                # self.log_msg("Inventory is full, dropping items...")
                # self.drop(log_slots)
                self.log_msg("Banking...")
                if bank := self.get_nearest_tag(clr.YELLOW):
                    self.mouse.move_to(bank.random_point())
                    if not self.mouseover_text(contains="Bank"):
                        continue
                    self.mouse.click()
                    while not api_m.get_is_player_idle():
                        self.log_msg("Waiting for player to be idle to bank...")
                        time.sleep(1)
                    # move mouse to first inventory slot
                    self.mouse.move_to(self.win.inventory_slots[log_slots[0]].random_point())
                    if self.mouseover_text(contains=["All"]):
                        self.bank_all(log_slots)
                    time.sleep(1)
                else:
                    self.log_msg("Bank not found, quitting bot so you can fix it...")
                    self.stop()
            elif api_m.get_is_inv_full() and not log_slots:
                self.log_msg("Inventory is full, but no logs found, quitting bot so you can fix it...")
                self.stop()

            # Find all tree
            if api_m.get_is_player_idle():
                if tree := self.get_nearest_tag(clr.PINK):
                    self.mouse.move_to(tree.random_point())
                    if not self.mouseover_text(contains="Chop"):
                        continue
                    self.mouse.click()
            time.sleep(1)
                
            # -- End bot actions --
            self.update_progress((time.time() - start_time) / end_time)

        self.update_progress(1)
        self.log_msg("Finished.")
        self.logout()
        self.stop()