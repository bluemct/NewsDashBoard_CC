"""
ICM CreateIncident - 精确复刻 C# IcmDll.CreateIncident 类
"""
import json
from datetime import datetime, timezone


def utc_now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


class CreateIncident:
    """精确复刻 C# IcmDll.CreateIncident，字段名和默认值与 C# 一致"""

    def __init__(self):
        self._Id = 0
        self._Description = "Incident Created"
        self._CreatedDate = utc_now_iso()
        self._LastModifiedDate = utc_now_iso()
        self._OccuringLocation = {"Environment": "PROD", "Datacenter": None, "Role": None, "Instance": None, "Slice": None}
        self._IsSecurityRisk = False
        self._IsCustomerImpacting = False
        self._IsNoise = False
        self._State = "ACTIVE"
        self._Severity = 3
        self._Attachments = []
        self._CloudInstanceId = 3
        self._Type = "LiveSite"
        self._OwningServiceId = 20284
        self._OwningTeamId = 37883
        self._IsAcknowledged = False
        self._Keywords = ""
        self._SubscriptionId = ""
        self._SupportTicketId = ""
        self._CustomerName = ""
        self._LinkedIncidentCount = 0
        self._ExternalLinksCount = 0
        self._SourceCreateTime = utc_now_iso()
        self._HitCount = 0
        self._ChildCount = 0
        self._ImpactedServices = []
        self._ImpactedTeams = []
        self._ImpactedComponents = []
        self._CustomFields = []
        # Public properties
        self.Title = None
        self.Summary = None

    # --- Properties ---
    @property
    def Id(self): return self._Id

    @property
    def Description(self): return self._Description
    @Description.setter
    def Description(self, v): self._Description = v

    @property
    def CreatedDate(self): return self._CreatedDate
    @CreatedDate.setter
    def CreatedDate(self, v): self._CreatedDate = v

    @property
    def LastModifiedDate(self): return self._LastModifiedDate
    @LastModifiedDate.setter
    def LastModifiedDate(self, v): self._LastModifiedDate = v

    @property
    def OccuringLocation(self):
        loc = self._OccuringLocation
        if loc.get("Datacenter") == "All Production":
            loc["Datacenter"] = "China North"
        return loc
    @OccuringLocation.setter
    def OccuringLocation(self, v): self._OccuringLocation = v

    @property
    def IsSecurityRisk(self): return self._IsSecurityRisk
    @IsSecurityRisk.setter
    def IsSecurityRisk(self, v): self._IsSecurityRisk = v

    @property
    def IsCustomerImpacting(self): return self._IsCustomerImpacting
    @IsCustomerImpacting.setter
    def IsCustomerImpacting(self, v): self._IsCustomerImpacting = v

    @property
    def IsNoise(self): return self._IsNoise
    @IsNoise.setter
    def IsNoise(self, v): self._IsNoise = v

    @property
    def State(self): return self._State

    @property
    def Severity(self): return self._Severity
    @Severity.setter
    def Severity(self, v): self._Severity = v

    @property
    def Attachments(self): return self._Attachments
    @Attachments.setter
    def Attachments(self, v): self._Attachments = v

    @property
    def CloudInstanceId(self): return self._CloudInstanceId
    @CloudInstanceId.setter
    def CloudInstanceId(self, v): self._CloudInstanceId = v

    @property
    def Type(self): return self._Type
    @Type.setter
    def Type(self, v): self._Type = v

    @property
    def OwningServiceId(self): return self._OwningServiceId
    @OwningServiceId.setter
    def OwningServiceId(self, v): self._OwningServiceId = v

    @property
    def OwningTeamId(self): return self._OwningTeamId
    @OwningTeamId.setter
    def OwningTeamId(self, v): self._OwningTeamId = v

    @property
    def IsAcknowledged(self): return self._IsAcknowledged
    @IsAcknowledged.setter
    def IsAcknowledged(self, v): self._IsAcknowledged = v

    @property
    def Keywords(self): return self._Keywords
    @Keywords.setter
    def Keywords(self, v): self._Keywords = v

    @property
    def SubscriptionId(self): return self._SubscriptionId
    @SubscriptionId.setter
    def SubscriptionId(self, v): self._SubscriptionId = v

    @property
    def SupportTicketId(self): return self._SupportTicketId
    @SupportTicketId.setter
    def SupportTicketId(self, v): self._SupportTicketId = v

    @property
    def CustomerName(self): return self._CustomerName
    @CustomerName.setter
    def CustomerName(self, v): self._CustomerName = v

    @property
    def LinkedIncidentCount(self): return self._LinkedIncidentCount
    @LinkedIncidentCount.setter
    def LinkedIncidentCount(self, v): self._LinkedIncidentCount = v

    @property
    def ExternalLinksCount(self): return self._ExternalLinksCount
    @ExternalLinksCount.setter
    def ExternalLinksCount(self, v): self._ExternalLinksCount = v

    @property
    def SourceCreateTime(self): return self._SourceCreateTime

    @property
    def HitCount(self): return self._HitCount
    @HitCount.setter
    def HitCount(self, v): self._HitCount = v

    @property
    def ChildCount(self): return self._ChildCount
    @ChildCount.setter
    def ChildCount(self, v): self._ChildCount = v

    @property
    def ImpactedServices(self): return self._ImpactedServices
    @ImpactedServices.setter
    def ImpactedServices(self, v): self._ImpactedServices = v

    @property
    def ImpactedTeams(self): return self._ImpactedTeams
    @ImpactedTeams.setter
    def ImpactedTeams(self, v): self._ImpactedTeams = v

    @property
    def ImpactedComponents(self): return self._ImpactedComponents
    @ImpactedComponents.setter
    def ImpactedComponents(self, v): self._ImpactedComponents = v

    @property
    def CustomFields(self): return self._CustomFields
    @CustomFields.setter
    def CustomFields(self, v): self._CustomFields = v

    # --- Serialize ---
    def to_dict(self):
        """字段名与 C# Newtonsoft.Json 输出一致（PascalCase）"""
        return {
            "Id": self.Id,
            "Title": self.Title,
            "Description": self.Description,
            "Summary": self.Summary,
            "CreatedDate": self.CreatedDate,
            "LastModifiedDate": self.LastModifiedDate,
            "OccuringLocation": self.OccuringLocation,
            "IsSecurityRisk": self.IsSecurityRisk,
            "IsCustomerImpacting": self.IsCustomerImpacting,
            "IsNoise": self.IsNoise,
            "State": self.State,
            "Severity": self.Severity,
            "Attachments": self.Attachments,
            "CloudInstanceId": self.CloudInstanceId,
            "Type": self.Type,
            "OwningServiceId": self.OwningServiceId,
            "OwningTeamId": self.OwningTeamId,
            "IsAcknowledged": self.IsAcknowledged,
            "Keywords": self.Keywords,
            "SubscriptionId": self.SubscriptionId,
            "SupportTicketId": self.SupportTicketId,
            "CustomerName": self.CustomerName,
            "LinkedIncidentCount": self.LinkedIncidentCount,
            "ExternalLinksCount": self.ExternalLinksCount,
            "SourceCreateTime": self.SourceCreateTime,
            "HitCount": self.HitCount,
            "ChildCount": self.ChildCount,
            "ImpactedServices": self.ImpactedServices,
            "ImpactedTeams": self.ImpactedTeams,
            "ImpactedComponents": self.ImpactedComponents,
            "CustomFields": self.CustomFields,
        }

    def to_json(self, indent=2):
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)


# ===================== 使用示例 =====================
if __name__ == "__main__":
    inc = CreateIncident()
    inc.Title = "Python Test - ICM Ticket"
    inc.Description = "Test incident from Python"
    inc.Summary = "Python API test"
    inc.Severity = 3
    inc.OwningTeamId = 37883

    print("=== CreateIncident JSON ===")
    print(inc.to_json())
