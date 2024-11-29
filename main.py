from tkinterdnd2 import TkinterDnD
from gui import ImageProcessorApp

if __name__ == "__main__":
    root = TkinterDnD.Tk()
    app = ImageProcessorApp(root)
    root.mainloop()
