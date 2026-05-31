# PDF-DarkMod - Offline Desktop Converter

A standalone desktop application that converts your PDF files into beautiful, eye-friendly dark mode themes. 
Built entirely with Python and Tkinter, ensuring 100% privacy with complete offline processing—no Node.js, Electron, or cloud uploads required.

*Credit to the original author of the web-based PDF Dark Mode tool, [Chizkiyahu](https://github.com/chizkiyahu).*

## Features
- **Standalone Desktop App:** Pure native feel, lightweight, and works fully offline.
- **Privacy First:** Your files never leave your device.
- **Beautiful Dark Themes:** Includes custom tailored themes like Classic Inversion, Claude Warm, ChatGPT Cool, Sepia Dark, Midnight Blue, and Forest Green.
- **Real-Time Preview:** Instantly see how your PDF will look in different themes with the built-in fast preview panel.
- **Customizable Quality:** Choose between fast conversions or high-quality (up to 300 DPI) rendering using NumPy optimizations.
- **Bookmarks Preserved:** Keeps your original PDF's table of contents and bookmarks intact.

## Requirements
- Python 3.10+
- `pip install pymupdf`
- `pip install numpy` (Optional, but highly recommended for 15-20x faster processing speed)

## Running the App
1. Clone or download this repository.
2. Install the required dependencies: `pip install -r requirements.txt` (or just install `pymupdf`).
3. Run the application:
   ```bash
   python main.py
   ```

## Building as an Executable (Optional)
If you want to create a single standalone `.exe` file without needing Python installed on the target machine:
```bash
pip install pyinstaller
pyinstaller --onefile --windowed --name "PDF-DarkMod" main.py
```

## License
This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for more details.
