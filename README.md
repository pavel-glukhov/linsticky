# LinSticky

Modern sticky notes application built with Python, GTK4, and Libadwaita for Linux.

### **Version**: 2.0.2
_______________

> [!IMPORTANT]
> **This is the new GTK4/Libadwaita version.**  
>  
> ⚠️ **Backward compatibility notice:**  
> This version is **NOT compatible with stickers created in previous versions** (PyQt6 v1.x).  
> Existing stickers **will not be migrated automatically**, so please **save or export any important text in advance** before installing this version.  
>  
> If you are looking for a **legacy version**, please use the original **PyQt6 version (v1.4.1)** available in the  
> 👉 [legacy branch](https://github.com/pavel-glukhov/linsticky/tree/legacy).

_______________

![example of app](https://github.com/pavel-glukhov/linsticky/blob/gtk/pic/example_2.0.0.png)

## 📑 Table of Contents
- [Features](#-features)
- [Installation](#installation)
  - [Snap Store (Recommended)](#snap-store-recommended)
  - [DEB Package](#deb-package)
- [Troubleshooting Localization](#troubleshooting-localization)
- [Credits](#credits)


## ✨ Features

- 📝 Smart Sticky Notes
Create, edit, and organize your notes in a clean, distraction-free interface designed for daily use.
- 🎨 Custom Color Palette
Personalize your notes by choosing colors that match your workflow and mood.
- ✍️ Rich Text Preservation
All text formatting is reliably saved, so your notes always look exactly as intended.
- 🌍 Multilingual Support
Use the app in multiple languages, including:
  - English
  - Русский
  - Español
  - Deutsch
  - Français
  - 简体中文
  - Português (Brasil)
  - Türkçe
  - Қазақша
- 🖥️ Modern GNOME Experience
A refreshed interface that follows current GNOME / Adwaita design guidelines for a native look and feel.
- Support of dark theme.

## Installation

### Snap Store (Recommended)

The easiest way to install LinSticky is via the Snap Store:

[![Get it from the Snap Store](https://snapcraft.io/static/images/badges/en/snap-store-black.svg)](https://snapcraft.io/linsticky)

```bash
sudo snap install linsticky
```

### DEB Package

You can download the latest .deb package from the [Releases page](https://github.com/pavel-glukhov/linsticky/releases).

```bash
# 1. Download the package
curl -O -L https://github.com/pavel-glukhov/linsticky/releases/download/v2.0.2/io.linsticky.app_2.0.2_all.deb

# 2. Install dependencies
sudo apt update
sudo apt install -y python3-gi gir1.2-gtk-4.0 gir1.2-adw-1 gir1.2-gtk-3.0 gir1.2-ayatanaappindicator3-0.1 gettext

# 3. Install the package
sudo dpkg -i io.linsticky.app_2.0.2_all.deb
```

## Troubleshooting Localization

If the app's language doesn't change after selection:
1.  **Install Language Pack:**
    ```sh
    sudo apt install language-pack-[lang_code] 
    ```
2.  **Generate Locale:**
    ```sh
    sudo locale-gen [lang_code].UTF-8 
    ```
3.  **Restart:** Restart the application.

Check available locales: `locale -a`

## Credits

- Author: Pavel Glukhov
- Email: glukhov.p@gmail.com
- License: MIT License
