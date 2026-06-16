from telethon.sync import TelegramClient
from telethon.sessions import StringSession

# Get these from https://my.telegram.org under 'API Development Tools'
print("--- TELEGRAM SESSION GENERATOR ---")
APP_ID_RAW = input("Enter API ID: ").strip().replace("'", "").replace('"', "")
APP_ID = int(APP_ID_RAW)
APP_HASH = input("Enter API HASH: ").strip().replace("'", "").replace('"', "")

with TelegramClient(StringSession(), APP_ID, APP_HASH) as client:
    print("\n--- YOUR NEW SESSION STRING IS BELOW ---")
    print(client.session.save())
    print("--- COPY EVERYTHING ABOVE THIS LINE ---\n")
