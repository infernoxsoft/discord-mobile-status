## Mobile status for discord.py (and other libraries for Discord bots)
### How to use:
1. Copy `patch_discordpy.py` file to the directory with your bot.
2. Insert the following code:
```py
from patch_discordpy import patch_discordpy
patch_discordpy()
```
That's all.
### How to patch other Discord bot library (must be fork of discord.py)
For example, we use the disnake library.
1. Open `patch_discordpy.py`.
2. Replace `from discord import ...` to `from disnake import ...`.
3. Optionally, you can rename the function and file.
