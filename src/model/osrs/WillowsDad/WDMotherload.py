import random
import time
from model.osrs.WillowsDad.WillowsDad_bot import WillowsDadBot
import utilities.api.item_ids as ids
import utilities.api.animation_ids as animation
import utilities.color as clr
import utilities.random_util as rd
import utilities.imagesearch as imsearch
import pyautogui as pag
from utilities.geometry import RuneLiteObject
import utilities.game_launcher as launcher
from pathlib import Path
import utilities.ocr as ocr


class OSRSWDMotherload(WillowsDadBot):
    def __init__(self):
        bot_title = "WDMotherload"
        description = "Motherload Mine. Bank is yellow, Mining spots are pink, and tiles are cyan."
        super().__init__(bot_title=bot_title, description=description)
        # Set option variables below (initial value is only used during UI-less testing)
        self.running_time = 200
        self.take_breaks = True
        self.afk_train = True
        self.delay_min =0.37
        self.delay_max = .67
        self.ores = ids.PAYDIRT
        self.Mining_tools = ids.pickaxes
        self.dragon_special = True


    def create_options(self):
        """
        Use the OptionsBuilder to define the options for the bot. For each function call below,
        we define the type of option we want to create, its key, a label for the option that the user will
        see, and the possible values the user can select. The key is used in the save_options function to
        unpack the dictionary of options after the user has selected them.
        """
        super().create_options()
        self.options_builder.add_checkbox_option("dragon_special", "Use Dragon Pickaxe Special?", [" "])


    def save_options(self, options: dict):
        """
        For each option in the dictionary, if it is an expected option, save the value as a property of the bot.
        If any unexpected options are found, log a warning. If an option is missing, set the options_set flag to
        False.
        """
        super().save_options(options)
        for option in options:
            if option == "dragon_special":
                self.dragon_special = options[option] != []
            else:
                self.log_msg(f"Unexpected option: {option}")

        self.log_msg(f"Running time: {self.running_time} minutes.")
        self.log_msg(f"Bot will{'' if self.take_breaks else ' not'} take breaks.")
        self.log_msg(f"Bot will{'' if self.afk_train else ' not'} train like you're afk on another tab.")
        self.log_msg(f"Bot will wait between {self.delay_min} and {self.delay_max} seconds between actions.")
        self.log_msg("Options set successfully.")
        self.options_set = True


    def launch_game(self):
    
        # If playing RSPS, change `RuneLite` to the name of your game
        if launcher.is_program_running("RuneLite"):
            self.log_msg("RuneLite is already running. Please close it and try again.")
            return
        
        settings = Path(__file__).parent.joinpath("WDMiner.properties")
        launcher.launch_runelite(
            properties_path=settings, 
            game_title=self.game_title, 
            use_profile_manager=True, 
            profile_name="WDMiner", 
            callback=self.log_msg)


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

            try:
                while not self.is_inv_full() and self.check_deposits() > 0:
                    self.check_run()
                    self.walk_to_mine()
                    if Mining_spot := self.get_mining_spot():
                        self.go_mining()

                if self.check_deposits() <= 1:
                    self.walk_vertical(color=clr.GREEN, direction=1)
                    self.check_wheel()
                    if not self.is_last_inv_slot_empty():
                        self.load_dirt()
                    self.empty_sack()

                self.walk_vertical(color=clr.GREEN, direction=1)
                self.load_dirt()
                self.walk_to_mine()

            except Exception as e:
                self.log_msg(f"Exception: {e}")
                self.loop_count += 1
                if self.loop_count > 5:
                    self.log_msg("Too many exceptions, stopping.")
                    self.log_msg(f"Last exception: {e}")
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


    def walk_to_bank(self):

        self.walk_vertical(color=clr.YELLOW, direction=1)


    def walk_to_mine(self):
        
        self.walk_vertical(color=clr.PINK, direction=-1)
    
    
    def setup(self):
        """Sets up loop variables, checks for required items, and checks location.
            This will ideally stop the bot from running if it's not setup correctly.
            * To-do: Add functions to check for required items, bank setup and locaiton.
            Args:
                None
            Returns:
                None"""
        super().setup()
        self.idle_time = 0
        self.deposit_ids = [self.ores]
        self.deposit_ids.extend([ids.UNCUT_DIAMOND, ids.UNCUT_DRAGONSTONE, ids.UNCUT_EMERALD, ids.UNCUT_RUBY, ids.UNCUT_SAPPHIRE, ids.UNIDENTIFIED_MINERALS])


        # Setup Checks for pickaxes and tagged objects
        self.check_equipment()

        self.face_north()

        if not self.get_nearest_tag(clr.YELLOW) and not self.get_nearest_tag(clr.PINK) and not self.power_Mining and not self.get_nearest_tag(clr.CYAN):
            self.log_msg("Did not see a bank(YELLOW) or a Mining spot (PINK) on screen, or a tile (CYAN) make sure they are tagged.")
            self.adjust_camera(clr.YELLOW)
            self.stop()
        if not self.get_nearest_tag(clr.CYAN) and not self.power_Mining:
            self.log_msg("Did not see any tiles tagged CYAN, make sure they are tagged so I can find my way to the bank.")
            self.stop()
        
        self.check_bank_settings()


    def face_north(self):
        """Faces the player north.
            Args:
                None
            Returns:
                None"""
        self.mouse.move_to(self.win.compass_orb.random_point(), mouseSpeed = "fastest")
        self.mouse.click()


    def check_bank_settings(self):
        """Checks if the bank booth is set to deposit all items.
            Args:
                None
            Returns:
                None"""
        # self.open_bank()
        # self.close_bank()
        

    def check_special(self, required_energy: int = 100):
        if self.get_special_energy() >= required_energy:
            self.activate_special()
            self.log_msg("Dragon Pickaxe Special Activated")


    def go_mining(self):
        """
        Mines ore veins
        Keeps of track of the last location, and checks if the vein is depleted spot moves.
        Returns: boolean
        Args: None
        """
        self.idle_time = time.time()
        afk_time = 0
        afk_start_time = time.time()
        if self.dragon_special:
             self.check_special() 

        if ore_vein := self.get_nearest_tag(clr.PINK):
                self.mouse.move_to(ore_vein.random_point())
                while not self.mouse.click(check_red_click=True):
                    # If the click was unsuccessful, get the mining spot again and move the mouse to it
                    ore_vein = self.get_nearest_tag(clr.PINK)
                    if ore_vein:
                        self.mouse.move_to(ore_vein.random_point())
                last_distance = ore_vein.distance_from_rect_center()
        else: 
            self.wait_until_color(clr.PINK, 40)
            return
        
        if self.wait_for_xp_drop(self.get_total_xp(), 15) == False:
            return

        while True:  # Start an indefinite loop
                    afk_time = int(time.time() - afk_start_time)
                    ore_vein = self.get_nearest_tag(clr.PINK)
                    current_distance = ore_vein.distance_from_rect_center()

                    if current_distance > 34:
                        self.log_msg(f"Distance is greater than 34 ({current_distance})")
                        break  # This will exit the loop if the current distance is greater than 30

                    if current_distance > last_distance:
                        self.log_msg("Current distance is greater than last distance, moving to next spot.")
                        break  # This will exit the loop if the current distance is greater than the last distance

                    if self.is_inv_full():
                        self.log_msg("Inventory is full, moving to bank.")
                        break  # This will exit the loop if the last inventory slot is not empty

                    last_distance = current_distance
                    time.sleep(self.random_sleep_length() / 2)  # Or whatever sleep time is appropriate

        self.breaks_skipped = afk_time // 6 # increasing break chance

        if self.breaks_skipped > 0:
            self.roll_chance_passed = True
            self.multiplier += self.breaks_skipped * .25
            self.log_msg(f"Skipped {self.breaks_skipped} break rolls while fishing.")


    def get_mining_spot(self):
        if mining_spot := self.get_nearest_tag(clr.PINK):
            return mining_spot
        return None


    def no_ore(self):
        return bool(ocr.find_text("is", self.win.chat.scale(scale_height=0.37, scale_width=1, anchor_y=1, anchor_x=0), ocr.PLAIN_12, clr.BLACK))
    

    def handle_no_mining_spot(self):
        # Define constants at the top of your script
        IDLE_TIME_LIMIT_1 = 10
        IDLE_TIME_LIMIT_2 = 32
        IDLE_TIME_LIMIT_3 = 60
        
        idle_time_elapsed = int(time.time() - self.idle_time)
        if idle_time_elapsed > IDLE_TIME_LIMIT_1:
            if self.get_nearest_tag(clr.CYAN):
                self.mouse.move_to(self.get_nearest_tag(clr.CYAN).random_point())
                self.mouse.click()
            time.sleep(self.random_sleep_length())
        if idle_time_elapsed > IDLE_TIME_LIMIT_2:
            self.adjust_camera(clr.BLUE, 1)
        if idle_time_elapsed > IDLE_TIME_LIMIT_3:
            self.log_msg("No Mining spot found in 60 seconds, quitting bot.")
            self.stop()


    def bank_or_drop(self, deposit_slots):
        """
        This will either bank or drop items depending on the power_Mining setting.
        Returns: void
        Args: None"""
        self.open_bank()
        time.sleep(self.random_sleep_length()/2)
        self.check_deposit_all()
        self.click_deposit_all()
        self.close_bank()


    def check_equipment(self):
        """
        Stops script if no axe is equipped.
        Returns: none
        Args: None
        """
        if not self.api_m.get_if_item_in_inv(self.Mining_tools) and not self.api_m.get_is_item_equipped(self.Mining_tools):
            self.log_msg("No Mining tool or in inventory, please fix that...")
            self.stop()


    def walk_horizontal(self, direction: int, color: clr = None, timeout: int = 60, img: Path = None):
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
                shapes_sorted = sorted(shapes, key=RuneLiteObject.distance_from_rect_left , reverse=reverse)
                self.mouse.move_to(shapes_sorted[int(rd.fancy_normal_sample(0,1))].scale(3,3).random_point(), mouseSpeed = "fastest")
            else:
                self.mouse.move_to(shapes[0].scale(3,3).random_point(), mouseSpeed = "fastest")

            # Click on the selected tile and wait for a random duration between 0.35 and 0.67 seconds
            self.mouse.click()
            time.sleep(self.random_sleep_length(.67, 1.24))

        return
    

    def walk_diagonal(self, direction: int, color: clr = None, timeout: int = 60, img: Path = None):
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
                    break

            # Get all cyan tiles in the game view
            shapes = self.get_all_tagged_in_rect(self.win.game_view, clr.CYAN)

            # Stop if no cyan tiles are found
            if shapes is []:
                self.log_msg("No cyan tiles found, stopping.")
                return

            # Sort the cyan tiles based on their distance from the top-center
            if len(shapes) > 1:
                shapes_sorted = sorted(shapes, key=RuneLiteObject.distance_from_rect_top)
                self.mouse.move_to(shapes_sorted[-1 if direction == -1 else random.randint(0,1)].scale(3,3).random_point(), mouseSpeed = "fastest")
            else:
                self.mouse.move_to(shapes_sorted[-1 if direction == -1 else 0].scale(3,3).random_point(), mouseSpeed = "fastest")

            # Click on the selected tile and wait for a random duration between 0.35 and 0.67 seconds
            self.mouse.click()
            time.sleep(self.random_sleep_length(.67, 1.24))

        return
        

    def walk_vertical(self, direction: int, color: clr = None, timeout: int = 60, img: Path = None):
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
                self.mouse.move_to(shapes_sorted[int(rd.fancy_normal_sample(0,1))].scale(3,3).random_point(), mouseSpeed = "fastest")
            else:
                self.mouse.move_to(shapes[0].scale(3,3).random_point(), mouseSpeed = "fastest")

            # Click on the selected tile and wait for a random duration between 0.35 and 0.67 seconds
            self.mouse.click()
            time.sleep(self.random_sleep_length(.67, 1.24))

        return
    
    def check_deposits(self):
        """
        uses ocr on top left corner of gamview to check deposits left"""
        if deposits := ocr.extract_text(self.win.game_view.scale(scale_height=0.37, scale_width=.3, anchor_y=0, anchor_x=0), ocr.PLAIN_12, clr.RED):
            # return any only numbers found after the word left
            if "left" in deposits:
                deposits_left = int(deposits.split("left:")[1].strip("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ\'\"!@#$%^&*()_+=-`~:;<>?,./\\|[]{}").strip())
                return deposits_left
            else:
                deposits = ocr.extract_text(self.win.game_view.scale(scale_height=0.37, scale_width=.3, anchor_y=0, anchor_x=0), ocr.PLAIN_12, clr.WHITE)
                deposits_left = int(deposits.split("left:")[1].strip("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ\'\"!@#$%^&*()_+=-`~:;<>?,./\\|[]{}").strip())
                return deposits_left
        elif deposits := ocr.extract_text(self.win.game_view.scale(scale_height=0.37, scale_width=.3, anchor_y=0, anchor_x=0), ocr.PLAIN_12, clr.WHITE):
            # return any only numbers found after the word left
            deposits_left = 1
            if "left" in deposits:
                deposits_left = int(deposits.split("left:")[1].strip("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ\'\"!@#$%^&*()_+=-`~:;<>?,./\\|[]{}").strip())
            else:
                pay_dirt = int(deposits.split("sack:")[1].strip("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ\'\"!@#$%^&*()_+=-`~:;<>?,./\\|[]{}").strip())
                if pay_dirt >= 79:
                    deposits_left = 1
            return deposits_left
        return 1 # if no deposits are found, return 1, default to emptying sack
    
    def check_wheel(self):
        """
        checks if the wheel is ready to be used or needs to be repaired
        """
        while wheel := self.get_nearest_tag(clr.RED):
            self.mouse.move_to(wheel.random_point())
            while not self.mouse.click(check_red_click=True):
                wheel = self.get_nearest_tag(clr.RED)
                if wheel:
                    self.mouse.move_to(wheel.random_point())
            self.wait_for_xp_drop(self.get_total_xp(), 8)
        return
    
    def load_dirt(self):
        """
        loads dirt into the hopper
        """
        while self.api_m.get_if_item_in_inv(self.ores):
            self.mouse.move_to(self.get_nearest_tag(clr.GREEN).random_point())
            while not self.mouse.click(check_red_click=True):
                dirt = self.get_nearest_tag(clr.GREEN)
                if dirt:
                    self.mouse.move_to(dirt.random_point())
            while self.api_m.get_if_item_in_inv(self.ores):
                time.sleep(self.random_sleep_length())
        return
    
    def empty_sack(self):
        """
        empties the sack
        """
        while self.check_sack() > 0:
            while self.is_inv_slot_empty(1):
                self.mouse.move_to(self.get_nearest_tag(clr.BLUE).random_point())
                while not self.mouse.click(check_red_click=True):
                    sack = self.get_nearest_tag(clr.BLUE)
                    if sack:
                        self.mouse.move_to(sack.random_point())
                while self.is_inv_slot_empty(1):
                    time.sleep(self.random_sleep_length())

            self.bank_or_drop(self.api_m.get_first_occurrence(self.deposit_ids))
        return
        
    def check_sack(self):
        """
        Uses ocr on the top left corner of the game view to check the sack
        """
        if sack := ocr.extract_text(self.win.game_view.scale(scale_height=0.37, scale_width=.3, anchor_y=0, anchor_x=0), ocr.PLAIN_12, clr.WHITE):
            # return any only numbers found after the word left
            if "left" in sack:
                sack_left = int(sack.split("left:")[0].strip("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ\'\"!@#$%^&*()_+=-`~:;<>?,./\\|[]{}").strip())
                return sack_left
            else:
                sack_left = int(sack.split("sack:")[1].strip("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ\'\"!@#$%^&*()_+=-`~:;<>?,./\\|[]{}").strip())
                return sack_left
        return None
    