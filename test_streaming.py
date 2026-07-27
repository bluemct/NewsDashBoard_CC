"""Test EWS Streaming Notifications using EWS Managed API DLL with pythonnet."""
import clr
import json
import os
import sys
import time
import threading

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

with open(os.path.join(BASE_DIR, ".edm_agent_config.json")) as f:
    config = json.load(f)
ews_config = config["ews"]

# Load EWS Managed API DLL
EWS_DLL = os.path.join(
    BASE_DIR, "EWS", "extracted", "lib", "net35", "Microsoft.Exchange.WebServices.dll"
)
clr.AddReference(EWS_DLL)

from Microsoft.Exchange.WebServices.Data import (
    ExchangeService,
    WellKnownFolderName,
    Folder,
    SearchFilter,
    FolderView,
    EventType,
    WebCredentials,
)
from System import Uri, Net

# ---- Step 1: Connect ----
print("1. Connecting to EWS...")
service = ExchangeService()
service.Credentials = WebCredentials(
    "", ews_config["password"], "21vianet.com"
)
service.Url = Uri(ews_config["url"])
print("   OK")

# ---- Step 2: Find EDM folder ----
print("2. Finding EDM folder...")
view = FolderView(1)
search_filter = SearchFilter.IsEqualTo(Folder.DisplayName, "EDM")
folders = service.FindFolders(
    WellKnownFolderName.MsgFolderRoot, search_filter, view
)
edm_folder = None
for f in folders.Folders:
    if f.DisplayName == "EDM":
        edm_folder = f
        break
print(f"   OK: {edm_folder.Id}")

# ---- Step 3: Create Streaming Subscription ----
print("3. Creating streaming subscription...")
from System.Collections.Generic import List as GenericList
from Microsoft.Exchange.WebServices.Data import FolderId

# Create List<FolderId> properly
folder_id_list = GenericList[object]()
folder_id_list.Add(edm_folder.Id)

# Create List<EventType> for events
event_list = GenericList[object]()
event_list.Add(EventType.NewMail)

subscription = service.SubscribeToStreamingNotifications(
    folder_id_list,
    event_list,
)
print(f"   OK: subscription={subscription.Id}")

# ---- Step 4: Create Streaming Connection ----
print("4. Creating streaming connection...")
from Microsoft.Exchange.WebServices.Data import StreamingSubscriptionConnection

conn = StreamingSubscriptionConnection(service, 30)
conn.AddSubscription(subscription)
print("   OK: connection created")

# ---- Step 5: Register event handler ----
print("5. Registering event handler...")


def on_notification_event(sender, event_args):
    print("\n>>> NOTIFICATION EVENT <<<")
    for event in event_args.Events:
        print(f"    EventType: {event.EventType}")
        if event.ItemId:
            print(f"    ItemId: {event.ItemId}")


conn.OnNotificationEvent += on_notification_event
print("   OK: handler registered")

# ---- Step 6: Open connection (blocking) ----
print("6. Opening streaming connection...")
print("   Waiting for events (Ctrl+C to stop)...\n")


def open_connection():
    try:
        conn.Open()
    except Exception as e:
        print(f"   Connection closed/error: {e}")


thread = threading.Thread(target=open_connection, daemon=True)
thread.start()

try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    print("\nStopping...")
    conn.Close()
    print("Done")
