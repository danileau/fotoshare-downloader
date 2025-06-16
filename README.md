🖼️ fotoshare_album_downloader

Download full-resolution images from a public or private album hosted on fotoshare.co. Works even if the album disables downloads or only shows previews. Just provide the album URL and optionally login credentials.

✨ Features

🔍 Scans the album page and extracts all original full-quality image URLs.

🔐 Supports private albums with email + password login.

⏳ Resumable downloads — skips files already saved.

📂 Saves images into a specified output folder.

⚖️ Parallel downloads using thread pool.

❌ Strips low-res ?width=... image modifiers.

⚡ Requirements

pip install requests beautifulsoup4 lxml tqdm

Python 3.7 or later is recommended.

▶️ Usage

# Download a public album
python fotoshare_album_downloader.py https://fotoshare.co/i/ABC123

# Download a private album
python fotoshare_album_downloader.py https://fotoshare.co/i/XYZ789 \
    --email you@example.com --password "SuperSecret"

# Custom output directory and more workers
python fotoshare_album_downloader.py https://fotoshare.co/i/ABC123 \
    --output ./my_album --workers 8

🚧 Limitations

Only works with albums hosted on fotoshare.co.

May require updates if fotoshare's page structure changes.

Ensure you have permission to download images from the album.

✉️ License & Attribution

This script is released under the MIT License. Created out of necessity and shared in the hope it helps others archive their memories reliably.

Contributions welcome!

Happy downloading! 🚀


