import sys

from PySide6.QtWidgets import QApplication

from gui import create_window


def main():
    app = QApplication(sys.argv)
    window = create_window()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
