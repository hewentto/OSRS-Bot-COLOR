import time
import traceback
from model.osrs.WillowsDad.WillowsDad_bot import WillowsDadBot
import utilities.api.item_ids as ids
import utilities.api.animation_ids as animation
from utilities.api.status_socket import StatusSocket
import utilities.color as clr
import utilities.random_util as rd
import utilities.imagesearch as imsearch
import pyautogui as pag
from utilities.geometry import Point, Rectangle, RuneLiteObject
from utilities import ocr



class OSRSWDAnimatedArmour(WillowsDadBot):
    def __init__(self):
        bot_title = "WDAnimatedarmour"
        description = """This bot fights animated armour in the Warriors' Guild.Highlight npc pink, door green, bank yellow,and pathing cyan"""
        super().__init__(bot_title=bot_title, description=description)
        # Set option variables below (initial value is only used during UI-less testing)
        self.running_time = 200
        self.take_breaks = True
        self.afk_train = True
        self.delay_min =0.37
        self.delay_max = .67
        self.hp_threshold: int = 40
        self.armour_type = "adamant"
        self.use_special_attack = True
        self.loot_items = "Adamant platebody, Adamant full helm, Adamant platelegs, Warrior guild token(30)"
        self.use_special_attack = True
        self.spec_energy_required = 25

    def create_options(self):
        """
        Use the OptionsBuilder to define the options for the bot. For each function call below,
        we define the type of option we want to create, its key, a label for the option that the user will
        see, and the possible values the user can select. The key is used in the save_options function to
        unpack the dictionary of options after the user has selected them.
        """
        self.options_builder.add_slider_option("hp_threshold", "Low HP threshold (0-100)?", 0, 100)
        self.options_builder.add_text_edit_option("armour_type", "Armour type (adamant, rune, black):", "adamant")
        self.options_builder.add_checkbox_option("use_special_attack", "Use special attack?", [" "])
        self.options_builder.add_checkbox_option("Use special attack?", "Use special attack?", [" "])
        self.options_builder.add_slider_option("spec_energy_required", "Special attack energy required (0-100)?", 0, 100)
        super().create_options()

    def save_options(self, options: dict):  # sourcery skip: for-index-underscore
        """
        For each option in the dictionary, if it is an expected option, save the value as a property of the bot.
        If any unexpected options are found, log a warning. If an option is missing, set the options_set flag to
        False.
        """
        super().save_options(options)
        for option in options:
            if option == "hp_threshold":
                self.hp_threshold = options[option]
            elif option == "armour_type":
                self.armour_type = options[option]
            elif option == "use_special_attack":
                self.use_special_attack = options[option] != []
            elif option == "spec_energy_required":
                self.spec_energy_required = options[option]
            elif option == "Use special attack?":
                self.use_special_attack = options[option] != []
            return # check options and assign to variables

        self.log_msg(f"Running time: {self.running_time} minutes.")
        self.log_msg(f"Bot will{'' if self.take_breaks else ' not'} take breaks.")
        self.log_msg(f"Bot will{'' if self.afk_train else ' not'} train like you're afk on another tab.")
        self.log_msg(f"Bot will wait between {self.delay_min} and {self.delay_max} seconds between actions.")
        self.log_msg("Options set successfully.")
        self.options_set = True


    def main_loop(self):
        """
        Main bot loop. We call setup() to set up the bot, then loop until the end time is reached.
        """
        # Setup variables
        self.setup()
        # Main loop
        while time.time() - self.start_time < self.end_time:

            runtime = int(time.time() - self.start_time)
            minutes_since_last_break = int((time.time() - self.last_break) / 60)
            seconds = int(time.time() - self.last_break) % 60
            percentage = (self.multiplier * .01)  # this is the percentage chance of a break
            self.roll_chance_passed = False

            # I wrap the whole bot in a try catch so that if there is an exception, it will be caught and the bot will retry, or stop and print exception if it fails too many times
            try:
                print("Starting bot actions") # bot actions go here

                if not self.api_m.get_if_item_in_inv(self.food_id):
                    self.bank()

                self.summon_animated_armour()

                self.fight_animated_armour()
                time.sleep(self.random_sleep_length(2,4))

                # Loot all highlighted items on the ground
                if self.loot_items:
                    self.loot()


            except Exception as e: # catch exceptions, no changes needed unless you don't want a try catch
                self.log_msg(f"Exception: {e}")
                self.loop_count += 1
                if self.loop_count > 5:
                    self.log_msg("Too many exceptions, stopping.")
                    self.log_msg(f"Last exception: {e}")
                    # print out stack trace
                    stack_trace = traceback.format_exc()
                    self.log_msg(stack_trace)
                    self.stop()
                continue
     
                
            # -- End bot actions --
            self.loop_count = 0
            if self.take_breaks:
                self.check_break(runtime, percentage, minutes_since_last_break, seconds)
            current_progress = round((time.time() - self.start_time) / self.end_time, 2)
            if current_progress != round(self.last_progress, 2):
                self.update_progress((time.time() - self.start_time) / self.end_time)
                self.last_progress = round(self.progress, 2)

        self.update_progress(1)
        self.log_msg("Finished.")
        self.logout()
        self.stop()
    
    def setup(self):
        """Sets up loop variables, checks for required items, and checks location.
            This will ideally stop the bot from running if it's not setup correctly.
            * To-do: Add functions to check for required items, bank setup and locaiton.
            Args:
                None
            Returns:
                None"""
        
        super().setup()
        self.check_for_armour()
        self.check_for_food()
        self.last_position = None
    
    def check_for_armour(self):
        """Checks for the required armour pieces in the inventory. If they are not found, the bot will stop.
            Args:
                None
            Returns:
                None"""
        if self.armour_type == "adamant":
            if not self.api_m.get_inv_item_indices([ids.ADAMANT_PLATEBODY, ids.ADAMANT_PLATELEGS, ids.ADAMANT_FULL_HELM]):
                self.log_msg("Missing armour pieces. Stopping.")
                self.stop()
        elif self.armour_type == "rune":
            if not self.api_m.get_inv_item_indices([ids.RUNE_PLATEBODY, ids.RUNE_PLATELEGS, ids.RUNE_FULL_HELM]):
                self.log_msg("Missing armour pieces. Stopping.")
                self.stop()
        elif self.armour_type == "black":
            if not self.api_m.get_inv_item_indices([ids.BLACK_FULL_HELM, ids.BLACK_PLATEBODY, ids.BLACK_PLATELEGS]):
                self.log_msg("Missing armour pieces. Stopping.")
    
    def check_for_food(self):
        """Checks for the required food in the inventory. If it is not found, the bot will stop.
            Args:
                None
            Returns:
                None"""
        # assign food_id to the correct food id based on the first one found in the inventory
        for food_id in ids.all_food:
            if self.api_m.get_inv_item_indices([food_id]):
                self.food_id = food_id
                break
    
    def summon_animated_armour(self):
        """clicks on the blue animate armour marker, waits for color pink"""
        self.mouse.move_to(self.get_nearest_tag(color=clr.BLUE).random_point())

        while not self.mouse.click(check_red_click=True):
            self.mouse.move_to(self.get_nearest_tag(color=clr.BLUE).random_point())
        
        self.wait_until_color(color=clr.PINK)

    def fight_animated_armour(self):
        """Fights the animated armour, tagged pink. Eats food when hp is low."""

        try:
            self.mouse.move_to(self.get_nearest_tag(color=clr.PINK).random_point())
        except Exception as e:
            self.log_msg(f"Exception: {e}")

        while not self.mouse.click(check_red_click=True):
            self.mouse.move_to(self.get_nearest_tag(color=clr.PINK).random_point())

        self.wait_for_xp_drop(self.get_total_xp(), 10)
        self.wait_till_npc_dead(180)
        
    def wait_till_npc_dead(self, timeout: int = 30):
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
            if self.get_hp() < self.hp_threshold:
                self.eat(self.food_id, self.get_hp())
            if self.use_special_attack and self.get_special_energy() >= self.spec_energy_required:
                self.activate_special()

            self.update_last_position(self.get_nearest_tag(clr.PINK))

            time.sleep(self.random_sleep_length())

    def update_last_position(self, tag: RuneLiteObject):
        if not tag is None:
            self.last_position = tag
    
    def eat(self, food_id: int, last_hp: int):
        """Eats food from the inventory"""
        food_indice = self.api_m.get_first_occurrence(food_id)
        if food_indice == -1:
            return
        
        while self.get_hp() <= self.hp_threshold:
            self.mouse.move_to(self.win.inventory_slots[self.api_m.get_first_occurrence(food_id)].random_point())
            self.mouse.click()
            time.sleep(self.random_sleep_length())
    
    def bank(self):
        """Walks to bank, withdraws more food, and walks back"""
        self.walk_to_bank()
        self.withdraw_food()
        self.walk_back()
    
    def walk_to_bank(self):
        """Walks to the bank"""
        self.walk_vertical(1, clr.GREEN)
        
        # click on green door, wait till idle
        self.mouse.move_to(self.get_nearest_tag(color=clr.GREEN).random_point())

        while not self.mouse.click(check_red_click=True):
            self.mouse.move_to(self.get_nearest_tag(color=clr.GREEN).random_point())
        
        self.wait_until_idle()

        self.walk_horizontal(1, clr.YELLOW)
        return
    
    def withdraw_food(self):
        """Withdraws food from the bank"""
        self.open_bank()
        self.check_deposit_all()
        self.withdraw_items(self.WILLOWSDAD_IMAGES.joinpath("Potato_with_cheese_bank.png"))
        self.close_bank()
        return
    
    def walk_back(self):
        """Walks back to the animated armour"""
        self.walk_horizontal(-1, clr.GREEN)

        # click on green door, wait till idle
        self.mouse.move_to(self.get_nearest_tag(color=clr.GREEN).random_point())

        while not self.mouse.click(check_red_click=True):
            self.mouse.move_to(self.get_nearest_tag(color=clr.GREEN).random_point())
        
        self.wait_until_idle()

        self.walk_vertical(-1, clr.BLUE)
        return
    
    def loot(self):
        """Picks up loot while there is loot on the ground"""
        # clicks on purple tag until it is gone
        self.mouse.move_to(self.last_position.random_point())
        self.mouse.click()
        time.sleep(self.random_sleep_length(1,2.2))

        self.mouse.move_to(self.win.game_view.get_center())

        while self.mouse.click(check_red_click=True):
            self.mouse.click()
            time.sleep(self.random_sleep_length())

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
            return False

        self.mouse.move_to(found[0].scale(.7,.7).random_point())
        time.sleep(self.random_sleep_length(.22,.42))

        self.mouse.click()
        return True