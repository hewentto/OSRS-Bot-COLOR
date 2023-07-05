from tkinter import *

class User:
    def __init__(self):
        """
        Args:
            username: The username.
            password: The password.
        """
        self.get_UandP()

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
        print("Username: ", self.username)
        print("Password: ", self.password)
        top.destroy()