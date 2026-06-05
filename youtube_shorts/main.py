import sys
import os

# Add the current directory to sys.path so we can import the youtube_shorts package
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from youtube_shorts.gui import main

if __name__ == "__main__":
    main()
