from tkinterdnd2 import TkinterDnD
import sv_ttk
from gui import ImageProcessorApp

if __name__ == "__main__":
    root = TkinterDnD.Tk()
    sv_ttk.set_theme("light")
    app = ImageProcessorApp(root)
    root.mainloop()
