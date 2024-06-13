# Mobile status for discord.py (and other libraries for Discord bots)
## Using modified bot instance (only for `discord.py`):
1. Copy directory `modified_bot_instance` to directory with your bot.
2. Optionally, you can rename this directory to something like 'custom_bot'.
3. Use the bot instance from `custom_bot.CustomBot` instead of `discord.ext.commands.Bot`.
4. Code example:
```py
...

from custom_bot import CustomBot

bot = CustomBot(
    # your parameters...
    ...,
    ws_identify_properties={
        "$os": platform,
        "$browser": "Discord Android",
        "$device": "Discord Android",
        # you can use "Discord iOS" instead
        "$referrer": "",
        "$referring_domain": "",
    },
)

# your other code...
```
This method is better because it does not require patching classes of `discord.py` library.
## Patching `discord.gateway.DiscordWebSocket` `identify` function (for `discord.py` and forks of it):
1. Copy `patch_discordpy.py` file from `patching` directory to the directory with your bot.
2. Insert the following code:
```py
from patch_discordpy import patch_discordpy
patch_discordpy()
```
That's all.
### How to patch other Discord bot library (must be fork of discord.py):
For example, we use the disnake library.
1. Open `patch_discordpy.py`.
2. Replace `from discord import ...` to `from disnake import ...`.
3. Optionally, you can rename the function and file.
