"""
Resource path helper for PyInstaller compatibility.
This module provides a function to get the correct path to resources
whether running as a script or as a PyInstaller executable.
"""

import os
import sys

def resource_path(relative_path):
    """
    Get absolute path to resource, works for dev and for PyInstaller.

    Args:
        relative_path: Path relative to the project root (e.g., 'ui/index.html')

    Returns:
        Absolute path to the resource
    """
    try:
        # PyInstaller creates a temp folder and stores its path in sys._MEIPASS
        base_path = sys._MEIPASS
    except AttributeError:
        # Not frozen: fall back to this file's directory
        base_path = os.path.dirname(os.path.abspath(__file__))

    return os.path.join(base_path, relative_path)

def get_base_dir():
    """
    Get the base directory of the application.
    In PyInstaller, this returns the temp extraction directory.
    In normal execution, this returns the project root.
    """
    try:
        return sys._MEIPASS
    except AttributeError:
        return os.path.dirname(os.path.abspath(__file__))

def get_user_data_dir():
    """
    Get the directory where user data (cache, config, etc.) should be stored.
    This is always in the same directory as the executable, not in the temp folder.
    """
    if getattr(sys, 'frozen', False):
        # Frozen: store next to the .exe, in an "mk5" subfolder
        runtime_dir = os.path.join(os.path.dirname(sys.executable), 'mk5')
        os.makedirs(runtime_dir, exist_ok=True)
        return runtime_dir
    else:
        return os.path.dirname(os.path.abspath(__file__))
