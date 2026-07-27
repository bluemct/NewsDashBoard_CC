"""Test EWS Streaming Notifications on 21Vianet."""
import json, os, sys, warnings
warnings.filterwarnings("ignore", category=UserWarning)
sys.stdout.reconfigure(encoding="utf-8")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

with open(os.path.join(BASE_DIR, ".edm_agent_config.json")) as f:
    config = json.load(f)

from edm_agent import EWSClient

client = EWSClient(
    url=config["ews"]["url"],
    domain_user=config["ews"]["domain_user"],
    password=config["ews"]["password"],
    mailbox=config["ews"]["mailbox"],
)
folder_id = client.find_folder("EDM")

# Try CreateStreamingSubscription
body_stream = f"""<m:CreateStreamingSubscription>
  <m:SubscribeToNotifications>
    <t:Notifications>
      <t:EventType>NewMail</t:EventType>
    </t:Notifications>
    <t:FolderIds>
      <t:FolderId Id="{folder_id}"/>
    </t:FolderIds>
  </m:SubscribeToNotifications>
  <m:ConnectionSettings>
    <t:SubscriptionId>edm_agent</t:SubscriptionId>
    <t:CallerName>test</t:CallerName>
    <t:RequestedStreamingNotificationDuration>600</t:RequestedStreamingNotificationDuration>
  </m:ConnectionSettings>
</m:CreateStreamingSubscription>"""

try:
    root = client._soap(body_stream)
    from lxml import etree
    print(f"Response XML:\n{etree.tostring(root, pretty_print=True).decode('utf-8')[:1000]}")
except Exception as e:
    print(f"Streaming NOT supported: {e}")

# Also try the legacy Watermark approach (Pull Notifications)
print("\n\nTrying CreateSubscription (Pull/Watermark)...")
body_pull = f"""<m:CreateSubscription>
  <m:Notifications>
    <t:EventType>NewMail</t:EventType>
  </m:Notifications>
  <m:FolderIds>
    <t:FolderId Id="{folder_id}"/>
  </m:FolderIds>
  <m:StatusFrequency>1</m:StatusFrequency>
</m:CreateSubscription>"""

try:
    root2 = client._soap(body_pull)
    from lxml import etree
    print(f"Response XML:\n{etree.tostring(root2, pretty_print=True).decode('utf-8')[:1000]}")
except Exception as e:
    print(f"Pull NOT supported: {e}")
